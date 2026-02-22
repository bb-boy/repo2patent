#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import time

from scripts.utils.git_utils import git_clone, git_checkout, git_rev_parse_head
from scripts.utils.io import write_json

def is_git_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://") or s.startswith("git@") or s.endswith(".git")

def main() -> int:
    p = argparse.ArgumentParser(description="Fetch (clone) a repo and record commit SHA (no code execution).")
    p.add_argument("--repo", required=True, help="Git repo URL or local path")
    p.add_argument("--ref", default=None, help="branch/tag/commit to checkout (optional)")
    p.add_argument("--workdir", default=".patent_assistant", help="Work directory for outputs")
    p.add_argument("--dest", default="repo", help="Destination folder name inside workdir (default: repo)")
    p.add_argument("--force", action="store_true", help="Overwrite existing dest directory")
    p.add_argument("--clone-retries", type=int, default=3, help="Retries per clone strategy for transient network failures")
    p.add_argument("--clone-backoff", type=float, default=2.0, help="Exponential backoff base for clone retries")
    args = p.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    dest_dir = os.path.join(args.workdir, args.dest)

    if args.force and os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    if os.path.exists(dest_dir):
        raise SystemExit(f"Destination exists: {dest_dir}. Use --force to overwrite.")

    repo_input = args.repo

    if is_git_url(repo_input):
        if args.ref and len(args.ref) < 80:
            git_clone(
                repo_input,
                dest_dir,
                depth=1,
                ref=args.ref,
                retries=args.clone_retries,
                retry_backoff=args.clone_backoff,
            )
        else:
            git_clone(
                repo_input,
                dest_dir,
                depth=1,
                ref=None,
                retries=args.clone_retries,
                retry_backoff=args.clone_backoff,
            )
            if args.ref:
                git_checkout(dest_dir, args.ref)
    else:
        if not os.path.isdir(repo_input):
            raise SystemExit(f"Local path not found: {repo_input}")
        shutil.copytree(repo_input, dest_dir)

    sha = "UNKNOWN"
    try:
        sha = git_rev_parse_head(dest_dir)
    except Exception:
        pass

    meta = {
        "repo_input": repo_input,
        "repo_path": os.path.abspath(dest_dir),
        "ref": args.ref,
        "commit_sha": sha,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(os.path.join(args.workdir, "repo_meta.json"), meta)
    print(f"[ok] repo at: {dest_dir}")
    print(f"[ok] commit: {sha}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
