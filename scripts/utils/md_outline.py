#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Heading:
    level: int
    text: str
    line_no: int

def parse_headings(lines: List[str], max_headings: int = 80) -> List[Heading]:
    heads: List[Heading] = []
    for i, line in enumerate(lines, start=1):
        if line.startswith("#"):
            j = 0
            while j < len(line) and line[j] == "#":
                j += 1
            if j > 0 and j < len(line) and line[j] == " ":
                text = line[j+1:].strip()
                if text:
                    heads.append(Heading(level=j, text=text, line_no=i))
                    if len(heads) >= max_headings:
                        break
    return heads

def extract_sections_by_headings(lines: List[str], wanted_headings: List[str], max_section_lines: int = 400) -> List[Tuple[int, int, str]]:
    headings = parse_headings(lines, max_headings=500)
    wanted_set = set(wanted_headings)
    results: List[Tuple[int, int, str]] = []
    for idx, h in enumerate(headings):
        if h.text not in wanted_set:
            continue
        start = h.line_no
        end = len(lines)
        for h2 in headings[idx+1:]:
            if h2.level <= h.level:
                end = h2.line_no - 1
                break
        if end - start + 1 > max_section_lines:
            end = start + max_section_lines - 1
        chunk = "\n".join(lines[start-1:end])
        results.append((start, end, chunk))
    return results
