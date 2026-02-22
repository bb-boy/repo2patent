#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from typing import Any, Dict, List, Tuple

from scripts.utils.chunking import clip_line_range, merge_ranges
from scripts.utils.io import read_json, read_lines, write_json
from scripts.utils.md_outline import extract_sections_by_headings

DEFAULT_MAX_CHUNK_CHARS = 8000

def die(msg: str) -> None:
    raise SystemExit(f"[evidence_builder] {msg}")

def validate_plan(index: Dict[str, Any], plan: Dict[str, Any]) -> None:
    for k in ["plan_version", "goals", "limits", "selections"]:
        if k not in plan:
            die(f"reading_plan missing key: {k}")
    if not isinstance(plan["selections"], list) or len(plan["selections"]) == 0:
        die("reading_plan.selections must be non-empty list")

    limits = plan.get("limits", {})
    if not isinstance(limits, dict):
        die("reading_plan.limits must be object")
    max_files = limits.get("max_files")
    max_total_chars = limits.get("max_total_chars")
    if not isinstance(max_files, int) or max_files <= 0:
        die("reading_plan.limits.max_files must be positive int")
    if not isinstance(max_total_chars, int) or max_total_chars <= 0:
        die("reading_plan.limits.max_total_chars must be positive int")

    selections = plan["selections"]
    if len(selections) > max_files:
        die(f"selections exceed max_files: {len(selections)} > {max_files}")

    indexed_paths = set()
    size_map = {}
    for f in index.get("files", []):
        p = f.get("path")
        if isinstance(p, str):
            indexed_paths.add(p)
            size_map[p] = int(f.get("size", 0))

    has_readme = any(isinstance(s.get("path"), str) and "readme" in s["path"].lower() for s in selections)
    if not has_readme:
        die("reading_plan must include README (or equivalent overview doc)")

    entrypoints = index.get("entrypoints", [])
    if isinstance(entrypoints, list) and entrypoints:
        has_entry = any(s.get("path") in entrypoints for s in selections)
        if not has_entry:
            die("reading_plan must include at least one entrypoint from repo_index.entrypoints")

    est_total = 0
    for sel in selections:
        path = sel.get("path")
        if not isinstance(path, str) or not path:
            die("each selection.path must be string")
        if path not in indexed_paths:
            die(f"selection.path not found in repo_index: {path}")
        read_type = sel.get("read_type")
        if read_type not in {"full","head","sections","symbols","grep_context"}:
            die(f"invalid read_type: {read_type}")
        fsize = size_map.get(path, 0)
        if read_type == "full":
            est = fsize
        elif read_type == "head":
            est = int(fsize * 0.2)
        else:
            est = int(fsize * 0.4)
        est_total += est

    if est_total > max_total_chars:
        die(f"estimated chars exceed max_total_chars: {est_total} > {max_total_chars}")

def slice_lines(lines: List[str], start: int, end: int) -> str:
    start, end = clip_line_range(start, end, len(lines))
    return "\n".join(lines[start-1:end])

def build_item(eid: str, path: str, start: int, end: int, excerpt: str, tags: List[str], why: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    item = {
        "id": eid,
        "path": path.replace("\\\\", "/"),
        "line_range": [start, end],
        "excerpt": excerpt,
        "tags": tags,
        "why_selected": why,
        "source": "repo",
    }
    item.update(extra)
    return item

def grep_context_ranges(lines: List[str], keywords: List[str], context: int = 30, max_hits: int = 15) -> List[Tuple[int,int]]:
    ranges: List[Tuple[int,int]] = []
    lower_lines = [ln.lower() for ln in lines]
    kw = [k.lower() for k in keywords if isinstance(k, str) and k.strip()]
    if not kw:
        return []
    hits = 0
    for i, ln in enumerate(lower_lines, start=1):
        if any(k in ln for k in kw):
            ranges.append((i-context, i+context))
            hits += 1
            if hits >= max_hits:
                break
    clipped = [clip_line_range(s, e, len(lines)) for s, e in ranges]
    return merge_ranges(clipped, gap=3)

def main() -> int:
    p = argparse.ArgumentParser(description="Build evidence.json from reading_plan.json (with integrated validation).")
    p.add_argument("--repo", required=True, help="Path to local repo checkout")
    p.add_argument("--index", required=True, help="repo_index.json")
    p.add_argument("--plan", required=True, help="reading_plan.json")
    p.add_argument("--out", required=True, help="Output evidence.json")
    p.add_argument("--max_chunk_chars", type=int, default=DEFAULT_MAX_CHUNK_CHARS)
    args = p.parse_args()

    repo = os.path.abspath(args.repo)
    index = read_json(args.index)
    plan = read_json(args.plan)

    validate_plan(index, plan)

    symbol_index: Dict[str, List[Dict[str, Any]]] = index.get("symbol_index", {}) if isinstance(index.get("symbol_index"), dict) else {}

    evidence: List[Dict[str, Any]] = []
    eid_counter = 1
    total_chars = 0
    max_total_chars = int(plan.get("limits", {}).get("max_total_chars", 200000))

    def next_id() -> str:
        nonlocal eid_counter
        eid = f"E{eid_counter:04d}"
        eid_counter += 1
        return eid

    selections: List[Dict[str, Any]] = plan.get("selections", [])
    selections = sorted(selections, key=lambda s: int(s.get("priority", 1)), reverse=True)

    for sel in selections:
        if total_chars >= max_total_chars:
            break

        path = sel.get("path")
        read_type = sel.get("read_type", "full")
        reason = str(sel.get("reason", ""))
        selectors = sel.get("selectors", {}) if isinstance(sel.get("selectors"), dict) else {}
        tags = sel.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t) for t in tags if str(t).strip()]

        abs_path = os.path.join(repo, path)
        lines = read_lines(abs_path)

        extracted: List[Tuple[int,int,str]] = []

        if read_type == "full":
            extracted.append((1, len(lines), slice_lines(lines, 1, len(lines))))

        elif read_type == "head":
            n = int(selectors.get("lines", 200))
            extracted.append((1, min(len(lines), max(1, n)), slice_lines(lines, 1, min(len(lines), max(1, n)))))

        elif read_type == "sections":
            headings = selectors.get("headings", [])
            if not isinstance(headings, list):
                headings = []
            headings = [str(h) for h in headings if str(h).strip()]
            if headings:
                for s, e, chunk in extract_sections_by_headings(lines, headings):
                    extracted.append((s, e, chunk))
            else:
                extracted.append((1, min(len(lines), 200), slice_lines(lines, 1, min(len(lines), 200))))

        elif read_type == "symbols":
            names = selectors.get("names", [])
            if not isinstance(names, list):
                names = []
            names = [str(n) for n in names if str(n).strip()]
            spans = symbol_index.get(path, [])
            for name in names:
                found = None
                for sp in spans:
                    if sp.get("name") == name:
                        found = sp
                        break
                if found and isinstance(found.get("start_line"), int) and isinstance(found.get("end_line"), int):
                    s, e = int(found["start_line"]), int(found["end_line"])
                    extracted.append((s, e, slice_lines(lines, s, e)))
                else:
                    for s, e in grep_context_ranges(lines, [name], context=25, max_hits=3):
                        extracted.append((s, e, slice_lines(lines, s, e)))

        elif read_type == "grep_context":
            keywords = selectors.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            keywords = [str(k) for k in keywords if str(k).strip()]
            context = int(selectors.get("context_lines", 30))
            for s, e in grep_context_ranges(lines, keywords, context=context, max_hits=15):
                extracted.append((s, e, slice_lines(lines, s, e)))

        for s, e, chunk in extracted:
            if total_chars >= max_total_chars:
                break
            chunk = chunk.strip("\\n")
            if not chunk:
                continue
            if len(chunk) > args.max_chunk_chars:
                chunk = chunk[:args.max_chunk_chars] + "\\n...[truncated]..."
            total_chars += len(chunk)
            evidence.append(build_item(
                eid=next_id(),
                path=path,
                start=s,
                end=e,
                excerpt=chunk,
                tags=tags,
                why=reason,
                extra={"read_type": read_type, "selectors": selectors},
            ))

    write_json(args.out, evidence)
    print(f"[ok] evidence items: {len(evidence)}")
    print(f"[ok] total_chars: {total_chars}")
    print(f"[ok] out: {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
