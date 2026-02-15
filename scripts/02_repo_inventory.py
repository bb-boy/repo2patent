#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    "__pycache__",
    ".vendor",
    "vendor",
    "third_party",
}

DOC_EXTS = {
    ".md",
    ".rst",
    ".txt",
    ".adoc",
    ".pdf",
    ".doc",
    ".docx",
}


def main():
    ap = argparse.ArgumentParser(
        description="Repository inventory indexer for repo2patent. It only outputs directories and document files."
    )
    ap.add_argument("--repo", required=True, help="Repository root path")
    ap.add_argument("--out", required=True, help="Output context.json path")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    if not repo.exists() or not repo.is_dir():
        raise SystemExit(f"Invalid repo path: {repo}")

    directories = set()
    docs_files = []
    scanned_files = 0

    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_root = Path(root).resolve().relative_to(repo).as_posix()
        if rel_root != ".":
            directories.add(rel_root)
        for fn in files:
            scanned_files += 1
            p = Path(root) / fn
            rel_str = p.relative_to(repo).as_posix()
            if p.suffix.lower() in DOC_EXTS:
                docs_files.append(rel_str)

    ctx = {
        "repo_name": repo.name,
        "extraction_mode": "directory_and_docs_only",
        "directories": sorted(directories),
        "document_file_types": sorted(DOC_EXTS),
        "document_files": sorted(set(docs_files)),
        "scan_stats": {
            "scanned_files": scanned_files,
            "directory_count": len(directories),
            "document_file_count": len(set(docs_files)),
            "skip_dirs": sorted(SKIP_DIRS),
        },
        "assistant_workflow_note": "Use this inventory only as navigation context. Assistant decides subsequent code reading paths.",
    }

    out.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
