#!/usr/bin/env python3
"""
prior_art_rerank.py - Step 7.5 semantic relevance reranking for prior_art.

Purpose:
- Use invention_profile + title/abstract text to compute relevance scores
- Optionally merge agent-provided relevance scores
- Output a reranked prior_art file for downstream claims fetching
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,10}")
MOJIBAKE_MARKERS = set("閿涢妴閸欓弮閺堥崶閸氶幋闂傛稉宕瑩閸掑Λ绱")
FORBIDDEN_SOURCE_MARKERS = ("manual", "fallback", "synthetic", "mock", "test")
ALLOWED_RESULT_SOURCES = {"Google Patents", "Lens.org", "Espacenet", "CNIPA"}


def normalize_text(s: Any) -> str:
    return str(s or "").strip()


def normalize_patent_number(pn: Any) -> str:
    return normalize_text(pn).upper()


def is_garbled_text(text: str) -> bool:
    s = normalize_text(text)
    if not s:
        return True
    if "\ufffd" in s:
        return True
    q_count = s.count("?")
    if q_count >= 2 and q_count / max(1, len(s)) >= 0.2:
        return True
    if len(s) >= 4:
        marker_hits = sum(1 for ch in s if ch in MOJIBAKE_MARKERS)
        if marker_hits / len(s) >= 0.25:
            return True
    return False


def dedup(seq: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in seq:
        v = normalize_text(x)
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


def tokenize(text: str) -> List[str]:
    raw = TOKEN_RE.findall(text or "")
    out: List[str] = []
    for t in raw:
        tt = normalize_text(t).lower()
        if not tt:
            continue
        if is_garbled_text(tt):
            continue
        out.append(tt)
    return out


def parse_score(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except Exception:
        return None
    if f > 1.0:
        # Allow 0~100 style scores from agent outputs.
        f = f / 100.0
    if f < 0:
        return 0.0
    if f > 1:
        return 1.0
    return f


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def validate_prior_art_items(items: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    for i, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            errors.append(f"item[{i}] is not object")
            continue
        source = normalize_text(it.get("source"))
        source_l = source.lower()
        if any(mark in source_l for mark in FORBIDDEN_SOURCE_MARKERS):
            errors.append(f"item[{i}] has forbidden source marker: {source}")
        if source and source not in ALLOWED_RESULT_SOURCES:
            errors.append(f"item[{i}] has unknown source: {source}")
        pn = normalize_patent_number(it.get("patent_number"))
        url = normalize_text(it.get("url"))
        if not (pn or url):
            errors.append(f"item[{i}] missing patent_number/url")
    return errors


def profile_keywords(profile: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    kw = profile.get("keywords", {}) if isinstance(profile.get("keywords"), dict) else {}
    kws_cn = kw.get("cn", []) if isinstance(kw.get("cn"), list) else []
    kws_en = kw.get("en", []) if isinstance(kw.get("en"), list) else []

    phrases: List[str] = []
    for k in list(kws_cn) + list(kws_en):
        s = normalize_text(k)
        if not s or is_garbled_text(s):
            continue
        phrases.append(s.lower())

    feats = profile.get("key_features", [])
    if isinstance(feats, list):
        for f in feats:
            txt = f.get("text") if isinstance(f, dict) else f
            s = normalize_text(txt)
            if not s or is_garbled_text(s):
                continue
            phrases.append(s.lower())

    phrases = dedup(phrases)
    tok: List[str] = []
    for p in phrases:
        tok.extend(tokenize(p))
    tokens = dedup(tok)
    return phrases, tokens


def score_item(
    item: Dict[str, Any],
    phrases: List[str],
    profile_tokens: List[str],
) -> Tuple[float, Dict[str, Any]]:
    title = normalize_text(item.get("title"))
    abstract = normalize_text(item.get("abstract"))
    query = normalize_text(item.get("query"))

    combined = f"{title}\n{abstract}".lower()
    title_l = title.lower()

    phrase_hits = 0
    title_phrase_hits = 0
    for p in phrases:
        if p and p in combined:
            phrase_hits += 1
            if p in title_l:
                title_phrase_hits += 1

    doc_tokens = dedup(tokenize(combined))
    pset = set(profile_tokens)
    dset = set(doc_tokens)
    token_hits = len(pset & dset) if pset else 0

    query_tokens = set(tokenize(query))
    query_hits = len(query_tokens & dset) if query_tokens else 0

    phrase_score = phrase_hits / max(1, len(phrases))
    title_phrase_score = title_phrase_hits / max(1, len(phrases))
    token_score = token_hits / max(1, len(profile_tokens))
    query_score = query_hits / max(1, len(query_tokens)) if query_tokens else 0.0

    # Favor phrase/title matches, keep token overlap as secondary signal.
    heuristic = (0.40 * phrase_score) + (0.25 * title_phrase_score) + (0.25 * token_score) + (0.10 * query_score)
    heuristic = max(0.0, min(1.0, heuristic))

    info = {
        "phrase_hits": phrase_hits,
        "title_phrase_hits": title_phrase_hits,
        "token_hits": token_hits,
        "query_hits": query_hits,
        "phrase_score": round(phrase_score, 4),
        "title_phrase_score": round(title_phrase_score, 4),
        "token_score": round(token_score, 4),
        "query_score": round(query_score, 4),
    }
    return heuristic, info


def normalize_agent_records(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, dict):
        records = obj.get("items", [])
    else:
        records = obj
    if not isinstance(records, list):
        return []
    return [r for r in records if isinstance(r, dict)]


def build_agent_score_map(agent_obj: Any) -> Dict[str, Tuple[float, str]]:
    records = normalize_agent_records(agent_obj)
    out: Dict[str, Tuple[float, str]] = {}
    for r in records:
        key = normalize_patent_number(r.get("patent_number")) or normalize_text(r.get("url"))
        if not key:
            continue
        score = (
            parse_score(r.get("score"))
            if parse_score(r.get("score")) is not None
            else parse_score(r.get("relevance_score"))
        )
        if score is None:
            score = parse_score(r.get("semantic_score"))
        if score is None:
            continue
        reason = normalize_text(r.get("reason") or r.get("note"))
        out[key] = (score, reason)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Rerank prior_art by semantic relevance (Step 7.5)")
    p.add_argument("--in", dest="input_path", required=True, help="prior_art.json")
    p.add_argument("--profile", required=True, help="invention_profile.json")
    p.add_argument("--out", required=True, help="output reranked prior_art.json")
    p.add_argument("--out-md", default=None, help="optional markdown summary output")
    p.add_argument("--agent-rerank", default=None, help="optional agent scores json ({items:[{patent_number,score,reason}]})")
    p.add_argument("--agent-weight", type=float, default=0.7, help="blend weight for agent score when present (0~1)")
    p.add_argument("--topk-for-gate", type=int, default=10, help="top-k used for relevance gate")
    p.add_argument("--min-topk-avg-score", type=float, default=0.0, help="minimum top-k average relevance score")
    p.add_argument(
        "--fail-on-low-relevance",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="exit non-zero when relevance gate fails",
    )
    p.add_argument(
        "--strict-source-integrity",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="validate prior_art source integrity before reranking",
    )
    args = p.parse_args()

    prior = load_json(args.input_path)
    if not isinstance(prior, list):
        raise SystemExit("prior_art.json must be a JSON list")

    profile = load_json(args.profile)
    if not isinstance(profile, dict):
        raise SystemExit("invention_profile.json must be JSON object")

    if args.strict_source_integrity:
        errors = validate_prior_art_items([x for x in prior if isinstance(x, dict)])
        if errors:
            raise SystemExit("prior_art strict validation failed:\n- " + "\n- ".join(errors[:20]))

    phrases, profile_tokens = profile_keywords(profile)
    if not phrases and not profile_tokens:
        raise SystemExit("profile has no usable keywords/features for reranking")

    agent_map: Dict[str, Tuple[float, str]] = {}
    if args.agent_rerank:
        agent_obj = load_json(args.agent_rerank)
        agent_map = build_agent_score_map(agent_obj)

    w = max(0.0, min(1.0, float(args.agent_weight)))
    out: List[Dict[str, Any]] = []
    for it in prior:
        if not isinstance(it, dict):
            continue
        heur, parts = score_item(it, phrases, profile_tokens)
        pn = normalize_patent_number(it.get("patent_number"))
        key = pn or normalize_text(it.get("url"))
        agent_score: Optional[float] = None
        agent_reason = ""
        if key in agent_map:
            agent_score, agent_reason = agent_map[key]
        if agent_score is None and pn and normalize_text(it.get("url")) in agent_map:
            agent_score, agent_reason = agent_map[normalize_text(it.get("url"))]

        if agent_score is None:
            final = heur
            mode = "heuristic_only"
        else:
            final = (w * agent_score) + ((1.0 - w) * heur)
            mode = "agent_blend"

        rec = dict(it)
        rec["relevance_score"] = round(max(0.0, min(1.0, final)), 4)
        rec["relevance_score_heuristic"] = round(heur, 4)
        rec["relevance_score_agent"] = round(agent_score, 4) if agent_score is not None else None
        rec["relevance_score_mode"] = mode
        rec["relevance_breakdown"] = parts
        if agent_reason:
            rec["relevance_reason"] = agent_reason
        out.append(rec)

    def sort_key(x: Dict[str, Any]) -> Tuple[float, float, float]:
        rel = parse_score(x.get("relevance_score")) or 0.0
        sim = parse_score(x.get("similarity_score")) or 0.0
        has_abs = 1.0 if normalize_text(x.get("abstract")) else 0.0
        return (rel, sim, has_abs)

    out = sorted(out, key=sort_key, reverse=True)
    for i, rec in enumerate(out, start=1):
        rec["relevance_rank"] = i

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    topk = out[: max(1, args.topk_for_gate)]
    topk_avg = sum(float(x.get("relevance_score") or 0.0) for x in topk) / max(1, len(topk))
    print(f"[ok] reranked items: {len(out)}")
    print(f"[ok] top{len(topk)} avg relevance: {topk_avg:.4f}")
    print(f"[ok] out: {args.out}")

    if args.out_md:
        lines: List[str] = [
            "# Prior Art Rerank Report",
            "",
            f"- input: {args.input_path}",
            f"- profile: {args.profile}",
            f"- total_items: {len(out)}",
            f"- top{len(topk)}_avg_relevance: {topk_avg:.4f}",
            "",
            "## Top 20",
            "",
        ]
        for i, rec in enumerate(out[:20], start=1):
            pn = normalize_patent_number(rec.get("patent_number"))
            title = normalize_text(rec.get("title"))
            score = rec.get("relevance_score")
            lines.append(f"{i}. `{pn or '(no-pn)'}` score={score} | {title}")
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[ok] out-md: {args.out_md}")

    if args.fail_on_low_relevance and topk_avg < max(0.0, float(args.min_topk_avg_score)):
        print(
            f"[error] top{len(topk)} avg relevance {topk_avg:.4f} < min_topk_avg_score {args.min_topk_avg_score:.4f}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
