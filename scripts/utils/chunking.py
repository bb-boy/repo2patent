#!/usr/bin/env python3
from __future__ import annotations
from typing import List, Tuple

def clip_line_range(start: int, end: int, total_lines: int) -> Tuple[int, int]:
    start = max(1, min(start, total_lines))
    end = max(1, min(end, total_lines))
    if end < start:
        start, end = end, start
    return start, end

def merge_ranges(ranges: List[Tuple[int, int]], gap: int = 2) -> List[Tuple[int, int]]:
    if not ranges:
        return []
    ranges = sorted(ranges, key=lambda x: (x[0], x[1]))
    merged: List[Tuple[int, int]] = [ranges[0]]
    for s, e in ranges[1:]:
        ls, le = merged[-1]
        if s <= le + gap:
            merged[-1] = (ls, max(le, e))
        else:
            merged.append((s, e))
    return merged
