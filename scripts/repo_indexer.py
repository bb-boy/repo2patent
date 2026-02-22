#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from typing import Dict, List

from scripts.utils.io import read_lines, read_text, write_json
from scripts.utils.md_outline import parse_headings
from scripts.utils.path_filter import PathFilter
from scripts.utils.symbol_index import index_python_symbols

LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".java": "java",
    ".go": "go", ".rs": "rust", ".cpp": "cpp", ".c": "c", ".h": "c",
    ".md": "markdown", ".rst": "rst", ".txt": "text",
    ".yml": "yaml", ".yaml": "yaml", ".json": "json", ".toml": "toml",
}

DOC_NAMES = {"readme.md", "readme.zh.md", "readme.en.md"}

SIGNAL_KEYWORDS = [
    "scheduler", "pipeline", "index", "engine", "cache", "dedup", "optimizer", "retry",
    "ranking", "scoring", "token", "vector", "search", "planner", "agent", "workflow",
]

def guess_kind(path: str) -> str:
    lower = path.lower()
    base = os.path.basename(lower)
    if base in DOC_NAMES or lower.endswith("readme.md"):
        return "doc"
    if lower.startswith("docs/") or "/docs/" in lower:
        if lower.endswith((".md", ".rst", ".txt")):
            return "doc"
    if lower.endswith((".md", ".rst", ".txt")):
        return "doc"
    if lower.endswith((".yaml", ".yml", ".toml", ".ini", ".cfg", ".json")):
        return "config"
    return "code"

def guess_language(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return LANG_BY_EXT.get(ext, "unknown")

def find_entrypoints(repo: str, all_files: List[str]) -> List[str]:
    entry = []
    candidates = ["main.py","app.py","server.py","cli.py","src/main.py","src/app.py","src/server.py"]
    for c in candidates:
        if c in all_files:
            entry.append(c)
    if "package.json" in all_files:
        try:
            text = read_text(os.path.join(repo, "package.json"))
            pkg = json.loads(text)
            main_file = pkg.get("main")
            if isinstance(main_file, str) and main_file in all_files:
                entry.append(main_file)
        except Exception:
            pass
    go_files = [p for p in all_files if p.endswith(".go")]
    for gf in go_files[:200]:
        try:
            lines = read_lines(os.path.join(repo, gf))
            joined = "\\n".join(lines[:200])
            if "package main" in joined and "func main(" in joined:
                entry.append(gf)
        except Exception:
            continue
    seen = set()
    out = []
    for p in entry:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out

def score_file(path: str, kind: str, size: int, is_entry: bool) -> float:
    lower = path.lower()
    score = 0.0
    if kind == "doc":
        score += 4.0
        if "readme" in lower:
            score += 2.0
        if "arch" in lower or "design" in lower:
            score += 1.0
    if kind == "code":
        score += 2.0
        if lower.startswith("src/") or "/src/" in lower:
            score += 1.0
    if kind == "config":
        score += 1.0
    if is_entry:
        score += 3.0
    for kw in SIGNAL_KEYWORDS:
        if kw in lower:
            score += 0.5
    if size <= 50_000:
        score += 0.5
    elif size > 400_000:
        score -= 1.5
    return score

def main() -> int:
    p = argparse.ArgumentParser(description="Build repo_index.json for guided reading.")
    p.add_argument("--repo", required=True, help="Path to local repo checkout")
    p.add_argument("--out", required=True, help="Output repo_index.json path")
    p.add_argument("--max_files", type=int, default=5000, help="Max files to index")
    p.add_argument("--max_doc_headings", type=int, default=60, help="Max headings per doc to record")
    args = p.parse_args()

    repo = os.path.abspath(args.repo)
    pf = PathFilter()

    files: List[str] = []
    for root, dirnames, filenames in os.walk(repo):
        dirnames[:] = pf.iter_filtered_dirs(dirnames)
        rel_root = os.path.relpath(root, repo)
        if rel_root == ".":
            rel_root = ""
        for fn in filenames:
            rel = os.path.join(rel_root, fn).replace("\\\\", "/").lstrip("./")
            files.append(rel)
            if len(files) >= args.max_files:
                break
        if len(files) >= args.max_files:
            break

    entrypoints = find_entrypoints(repo, files)

    docs = []
    symbol_index: Dict[str, List[dict]] = {}
    file_meta = []
    for rel in files:
        abs_path = os.path.join(repo, rel)
        try:
            size = os.path.getsize(abs_path)
        except OSError:
            continue
        kind = guess_kind(rel)
        lang = guess_language(rel)
        is_entry = rel in entrypoints
        score_hint = score_file(rel, kind, size, is_entry)

        if kind == "doc" and rel.lower().endswith(".md") and size <= 300_000:
            try:
                lines = read_lines(abs_path)
                heads = parse_headings(lines, max_headings=args.max_doc_headings)
                docs.append({"path": rel, "headings": [h.text for h in heads], "size": size})
            except Exception:
                pass

        if lang == "python" and kind == "code" and size <= 300_000:
            try:
                src = read_text(abs_path)
                spans = index_python_symbols(src)
                if spans:
                    symbol_index[rel] = [asdict(s) for s in spans[:200]]
            except Exception:
                pass

        file_meta.append({
            "path": rel,
            "kind": kind,
            "lang": lang,
            "size": size,
            "is_entrypoint": is_entry,
            "score_hint": round(score_hint, 3),
        })

    top_recommended = [x["path"] for x in sorted(file_meta, key=lambda d: d["score_hint"], reverse=True)[:40]]

    out = {
        "repo": {"path": repo, "commit_sha": "UNKNOWN"},
        "entrypoints": entrypoints,
        "docs": docs,
        "files": file_meta,
        "symbol_index": symbol_index,
        "top_recommended": top_recommended,
        "ignore_dirs": sorted(list(pf.ignore_dirs)),
    }

    maybe_meta = os.path.join(os.path.dirname(args.out), "repo_meta.json")
    if os.path.exists(maybe_meta):
        try:
            meta = json.load(open(maybe_meta, "r", encoding="utf-8"))
            sha = meta.get("commit_sha")
            if isinstance(sha, str) and sha:
                out["repo"]["commit_sha"] = sha
            url = meta.get("repo_input")
            if isinstance(url, str):
                out["repo"]["url"] = url
        except Exception:
            pass

    write_json(args.out, out)
    print(f"[ok] indexed files: {len(file_meta)}")
    print(f"[ok] entrypoints: {entrypoints}")
    print(f"[ok] out: {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
