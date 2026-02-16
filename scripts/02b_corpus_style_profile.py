#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build corpus style profile from CN*.txt / CN*.pdf files.

This script scans a corpus directory and generates a concise markdown report:
- corpus files and readability
- frequency of key patent-writing phrases
- representative opening lines for abstract / claim 1 / dependent claim
"""

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple


KEY_PATTERNS = [
    "本发明提供",
    "本发明公开",
    "其特征在于",
    "根据权利要求",
    "包括：",
    "步骤",
    "S101",
    "技术领域",
    "背景技术",
    "发明内容",
    "附图说明",
    "具体实施方式",
]


def read_text_file(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=enc, errors="ignore")
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def read_text_pdf(path: Path) -> str:
    # 1) pypdf
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        chunks = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).strip()
        if text:
            return text
    except Exception:
        pass

    # 2) PyPDF2
    try:
        from PyPDF2 import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        chunks = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        text = "\n".join(chunks).strip()
        if text:
            return text
    except Exception:
        pass

    # 3) pdftotext CLI (if available)
    cmd = shutil.which("pdftotext")
    if cmd:
        try:
            proc = subprocess.run(
                [cmd, "-layout", "-q", str(path), "-"],
                capture_output=True,
                check=False,
            )
            out = proc.stdout.decode("utf-8", errors="ignore").strip()
            if out:
                return out
        except Exception:
            pass

    return ""


def read_corpus_text(path: Path) -> str:
    if path.suffix.lower() == ".txt":
        return read_text_file(path)
    if path.suffix.lower() == ".pdf":
        return read_text_pdf(path)
    return ""


def collect_corpus_files(corpus_dir: Path) -> List[Path]:
    files = []
    files.extend(corpus_dir.glob("CN*.txt"))
    files.extend(corpus_dir.glob("CN*.pdf"))
    return sorted(files)


def first_line_contains(lines: List[str], needles: List[str]) -> str:
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if any(n in s for n in needles):
            return s
    return ""


def first_claim_line(lines: List[str]) -> str:
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("1.") or s.startswith("1 .") or s.startswith("1．"):
            return s
    return ""


def count_hit(text: str, pattern: str) -> int:
    return text.count(pattern)


def summarize_text(text: str) -> Tuple[str, str, str]:
    lines = text.splitlines()
    abstract_lead = first_line_contains(lines, ["本发明提供", "本发明公开"])
    claim1 = first_claim_line(lines)
    dependent = first_line_contains(lines, ["根据权利要求1所述"])
    return abstract_lead, claim1, dependent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", required=True, help="Directory containing CN*.txt/CN*.pdf files")
    ap.add_argument("--out", required=True, help="Output markdown path")
    args = ap.parse_args()

    corpus_dir = Path(args.corpus_dir).resolve()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    files = collect_corpus_files(corpus_dir)
    if not files:
        out.write_text(
            "# 工作目录专利语料风格笔记（自动生成）\n\n- 未发现 `CN*.txt` 或 `CN*.pdf` 语料文件。\n",
            encoding="utf-8",
        )
        print(f"Wrote {out}")
        return

    texts = {f: read_corpus_text(f) for f in files}

    lines: List[str] = []
    lines.append("# 工作目录专利语料风格笔记（自动生成）")
    lines.append("")
    lines.append("## 1. 语料文件")
    for f in files:
        readable = "yes" if len((texts.get(f) or "").strip()) >= 20 else "no"
        lines.append(f"- `{f.name}` ({f.stat().st_size} bytes, readable={readable})")
    lines.append("")

    lines.append("## 2. 高频结构信号")
    for p in KEY_PATTERNS:
        c = sum(count_hit(t, p) for t in texts.values())
        lines.append(f"- `{p}`：{c}")
    lines.append("")

    lines.append("## 3. 代表性句式样本")
    for f in files:
        abstract_lead, claim1, dependent = summarize_text(texts.get(f, ""))
        lines.append(f"### {f.name}")
        if abstract_lead:
            lines.append(f"- 摘要起句样本：`{abstract_lead}`")
        else:
            lines.append("- 摘要起句样本：未识别")
        if claim1:
            lines.append(f"- 权1起句样本：`{claim1}`")
        else:
            lines.append("- 权1起句样本：未识别")
        if dependent:
            lines.append(f"- 从属起句样本：`{dependent}`")
        else:
            lines.append("- 从属起句样本：未识别")
        lines.append("")

    lines.append("## 4. 写作迁移建议")
    lines.append("- 采用“摘要单段 + 权利要求分层编号 + 说明书五段结构”的统一骨架。")
    lines.append("- 独立权利要求优先使用“其特征在于，包括：”句式；从属项使用“根据权利要求X所述...”句式。")
    lines.append("- 术语保持单一命名，效果表达以可验证结果为限。")
    lines.append("- 若语料与项目领域差异大，仅迁移句法结构，不迁移领域名词。")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
