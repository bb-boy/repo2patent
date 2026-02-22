#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List, Tuple


def normalize_patent_number(pn: Any) -> str:
    return str(pn or "").strip().upper()


def claimability_score(item: Dict[str, Any]) -> Tuple[int, int, int]:
    pn = normalize_patent_number(item.get("patent_number", ""))
    url = str(item.get("url", "") or "").strip().lower()
    source = str(item.get("source", "") or "").strip().lower()
    has_pn = 1 if pn else 0
    has_google_patent_url = 1 if "patents.google.com/patent/" in url else 0
    is_google_source = 1 if source == "google patents" else 0
    return (has_pn, has_google_patent_url, is_google_source)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Create a manual claims extraction template from prior_art.json"
    )
    p.add_argument("--in", dest="input_path", required=True, help="prior_art.json")
    p.add_argument("--topk", type=int, default=10, help="Top K items for manual claims extraction")
    p.add_argument("--out", required=True, help="Output claims_manual_template.json")
    p.add_argument("--out-md", default=None, help="Optional markdown checklist output")
    args = p.parse_args()

    with open(args.input_path, "r", encoding="utf-8-sig") as f:
        prior = json.load(f)
    if not isinstance(prior, list):
        raise SystemExit("prior_art.json must be a JSON list")

    dedup: List[Dict[str, Any]] = []
    seen = set()
    for it in prior:
        if not isinstance(it, dict):
            continue
        pn = normalize_patent_number(it.get("patent_number", ""))
        url = str(it.get("url", "") or "").strip()
        key = pn or url
        if not key or key in seen:
            continue
        seen.add(key)
        dedup.append(it)

    dedup.sort(key=claimability_score, reverse=True)
    selected = dedup[: max(1, args.topk)]

    items: List[Dict[str, Any]] = []
    for idx, it in enumerate(selected, start=1):
        items.append(
            {
                "rank": idx,
                "patent_number": normalize_patent_number(it.get("patent_number", "")),
                "title": str(it.get("title", "") or "").strip(),
                "url": str(it.get("url", "") or "").strip(),
                "source": str(it.get("source", "") or "").strip(),
                "query": str(it.get("query", "") or "").strip(),
                "claims_text": "",
                "claims": [],
                "notes": "Fill at least independent claim(s). Use plain text.",
            }
        )

    out_obj = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input": args.input_path,
        "topk": args.topk,
        "items": items,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)
    print(f"[ok] template items: {len(items)}")
    print(f"[ok] out: {args.out}")

    if args.out_md:
        lines = [
            "# Manual Claims Extraction Checklist",
            "",
            f"- generated_at: {out_obj['generated_at']}",
            f"- input: {args.input_path}",
            f"- topk: {args.topk}",
            "",
        ]
        for it in items:
            lines.append(f"## {it['rank']}. {it['patent_number'] or '(no patent number)'}")
            lines.append(f"- source: {it['source']}")
            lines.append(f"- title: {it['title']}")
            lines.append(f"- url: {it['url']}")
            lines.append(f"- query: {it['query']}")
            lines.append("- status: TODO fill claims_text / claims[] in claims_manual.json")
            lines.append("")
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[ok] out-md: {args.out_md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

