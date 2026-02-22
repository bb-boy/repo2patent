#!/usr/bin/env python3
from __future__ import annotations
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

@dataclass
class CmdResult:
    returncode: int
    stdout: str
    stderr: str

def run(cmd: Sequence[str], cwd: Optional[str] = None, check: bool = True) -> CmdResult:
    p = subprocess.run(list(cmd), cwd=cwd, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr}")
    return CmdResult(p.returncode, p.stdout, p.stderr)

_RETRYABLE_PATTERNS: Tuple[str, ...] = (
    "rpc failed",
    "curl 18",
    "transferred a partial file",
    "early eof",
    "invalid index-pack output",
    "unexpected disconnect while reading sideband packet",
    "ssl_error_syscall",
    "failed to connect",
    "connection reset",
    "connection timed out",
    "timed out",
    "remote end hung up unexpectedly",
)

def _is_retryable_clone_error(msg: str) -> bool:
    lower = msg.lower()
    return any(p in lower for p in _RETRYABLE_PATTERNS)

def _cleanup_dest(dest_dir: str) -> None:
    if not os.path.exists(dest_dir):
        return
    shutil.rmtree(dest_dir, ignore_errors=True)

def _clone_commands(repo_url: str, dest_dir: str, depth: int, ref: Optional[str]) -> List[List[str]]:
    branch_args = ["--branch", ref] if ref else []
    return [
        # Strategy 1: regular shallow clone.
        ["git", "clone", "--depth", str(depth), *branch_args, repo_url, dest_dir],
        # Strategy 2: shallow + partial clone to reduce transfer size.
        ["git", "clone", "--depth", str(depth), "--filter=blob:none", "--single-branch", *branch_args, repo_url, dest_dir],
        # Strategy 3: try HTTP/1.1 to mitigate flaky HTTP2 transport issues.
        ["git", "-c", "http.version=HTTP/1.1", "clone", "--depth", str(depth), "--filter=blob:none", "--single-branch", *branch_args, repo_url, dest_dir],
    ]

def git_clone(
    repo_url: str,
    dest_dir: str,
    depth: int = 1,
    ref: Optional[str] = None,
    retries: int = 3,
    retry_backoff: float = 2.0,
) -> None:
    """
    Clone repository with retry + strategy fallback for unstable networks.
    """
    if retries < 1:
        retries = 1
    commands = _clone_commands(repo_url, dest_dir, depth, ref)
    errors: List[str] = []

    for strategy_idx, cmd in enumerate(commands, start=1):
        for attempt in range(1, retries + 1):
            _cleanup_dest(dest_dir)
            result = run(cmd, check=False)
            if result.returncode == 0:
                return

            err_msg = result.stderr.strip() or result.stdout.strip() or "unknown clone error"
            errors.append(
                f"[strategy {strategy_idx} attempt {attempt}/{retries}] {' '.join(cmd)} :: {err_msg}"
            )
            retryable = _is_retryable_clone_error(err_msg)
            is_last_attempt = attempt >= retries
            if (not retryable) or is_last_attempt:
                continue
            sleep_s = max(0.0, retry_backoff ** (attempt - 1))
            time.sleep(sleep_s)

    joined = "\n".join(errors[-12:])
    raise RuntimeError(
        f"git clone failed after retries/strategies. repo={repo_url} dest={dest_dir}\n{joined}"
    )

def git_checkout(repo_dir: str, ref: str) -> None:
    run(["git", "checkout", ref], cwd=repo_dir, check=True)

def git_rev_parse_head(repo_dir: str) -> str:
    r = run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True)
    return r.stdout.strip()
