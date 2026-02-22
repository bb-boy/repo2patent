#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re

def ensure_docx():
    try:
        from docx import Document  # type: ignore
        return Document
    except Exception as e:
        raise RuntimeError("python-docx not installed. Install with: pip install python-docx") from e

def render_from_markdown(md_text: str, output_path: str) -> None:
    Document = ensure_docx()
    doc = Document()

    lines = md_text.splitlines()
    in_code = False

    for line in lines:
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            doc.add_paragraph(line)
            continue
        if not line.strip():
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = min(len(m.group(1)), 6)
            text = m.group(2).strip()
            doc.add_heading(text, level=level)
            continue

        if line.startswith("> "):
            doc.add_paragraph(line[2:].strip())
            continue

        if re.match(r"^\s*[-*]\s+", line):
            text = re.sub(r"^\s*[-*]\s+", "", line).strip()
            doc.add_paragraph(text, style="List Bullet")
            continue

        if re.match(r"^\s*\d+\.\s+", line):
            text = re.sub(r"^\s*\d+\.\s+", "", line).strip()
            doc.add_paragraph(text, style="List Number")
            continue

        doc.add_paragraph(line.strip())

    doc.save(output_path)

def main() -> int:
    p = argparse.ArgumentParser(description="Render disclosure to .docx from Markdown or JSON")
    p.add_argument("--input", "-i", required=True, help="Input disclosure.md or JSON")
    p.add_argument("--output", "-o", required=True, help="Output .docx path")
    args = p.parse_args()

    with open(args.input, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    if args.input.lower().endswith(".json"):
        obj = json.loads(text)
        md = json.dumps(obj, ensure_ascii=False, indent=2)
        render_from_markdown(md, args.output)
    else:
        render_from_markdown(text, args.output)

    print(f"[ok] written: {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
