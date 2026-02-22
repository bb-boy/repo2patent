#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass

DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "dist", "build", "target", "vendor",
    "__pycache__", ".venv", "venv", ".idea", ".vscode",
}

@dataclass(frozen=True)
class PathFilter:
    ignore_dirs: frozenset[str] = frozenset(DEFAULT_IGNORE_DIRS)

    def should_skip_dir(self, dirname: str) -> bool:
        return dirname in self.ignore_dirs

    def iter_filtered_dirs(self, dirnames: list[str]) -> list[str]:
        return [d for d in dirnames if not self.should_skip_dir(d)]
