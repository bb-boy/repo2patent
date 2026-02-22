#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any, Dict, List, Tuple

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,8}")
MOJIBAKE_MARKERS = set("锛銆鍙鏃鏈鍥鍚鎴鍙闂涓鸿澶勭悊")

def dedup(seq: List[str]) -> List[str]:
    seen = set()
    out = []
    for s in seq:
        s = str(s).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out

def normalize_kw(k: str) -> str:
    return re.sub(r"[\[\]（）()\"“”]", "", k).strip()

def is_garbled_text(text: str) -> bool:
    s = str(text).strip()
    if not s:
        return True
    q_count = s.count("?")
    bad_count = s.count("\ufffd")
    if bad_count > 0:
        return True
    if q_count >= 2 and q_count / max(1, len(s)) >= 0.2:
        return True
    if len(s) >= 4:
        marker_hits = sum(1 for ch in s if ch in MOJIBAKE_MARKERS)
        if marker_hits / len(s) >= 0.25:
            return True
    return False

def split_terms(raw_terms: List[Any]) -> Tuple[List[str], List[str]]:
    kept: List[str] = []
    dropped: List[str] = []
    for item in raw_terms:
        term = normalize_kw(str(item))
        if not term:
            continue
        if is_garbled_text(term):
            dropped.append(term)
            continue
        kept.append(term)
    return dedup(kept), dedup(dropped)

def tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall(text) if len(t) >= 2 and not is_garbled_text(t)]

def is_query_valid(query: str, min_query_tokens: int) -> bool:
    q = str(query).strip()
    if not q:
        return False
    if is_garbled_text(q):
        return False
    return len(tokenize(q)) >= max(1, min_query_tokens)

def load_agent_queries(path: str) -> Tuple[List[str], str]:
    if not path:
        return [], "agent query file path is empty"
    if not os.path.exists(path):
        return [], f"agent query file not found: {path}"
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            obj = json.load(f)
    except Exception as e:
        return [], f"failed to load agent queries from {path}: {e}"

    if isinstance(obj, dict) and isinstance(obj.get("queries"), list):
        return [str(q) for q in obj["queries"] if str(q).strip()], ""
    if isinstance(obj, list):
        return [str(q) for q in obj if str(q).strip()], ""
    return [], f"invalid agent query file format: {path}"

def sanitize_agent_queries(raw_queries: List[str], min_query_tokens: int) -> Tuple[List[str], List[Dict[str, str]]]:
    valid: List[str] = []
    dropped: List[Dict[str, str]] = []
    seen = set()
    for q in raw_queries:
        query = str(q).strip()
        if not query:
            continue
        reason = ""
        if is_garbled_text(query):
            reason = "garbled_query"
        elif len(tokenize(query)) < max(1, min_query_tokens):
            reason = "too_few_tokens"
        if reason:
            dropped.append({"query": query, "reason": reason})
            continue
        if query in seen:
            continue
        seen.add(query)
        valid.append(query)
    return valid, dropped

def build_queries_from_profile(
    profile: Dict[str, Any],
    max_queries: int = 8,
    min_query_tokens: int = 2,
) -> Dict[str, Any]:
    kws_cn = profile.get("keywords", {}).get("cn", [])
    kws_en = profile.get("keywords", {}).get("en", [])
    if not isinstance(kws_cn, list):
        kws_cn = []
    if not isinstance(kws_en, list):
        kws_en = []

    kws_cn_clean, dropped_cn = split_terms(kws_cn)
    kws_en_clean, dropped_en = split_terms(kws_en)
    kws = dedup(kws_cn_clean + kws_en_clean)

    feats = profile.get("key_features", [])
    feat_tokens: List[str] = []
    dropped_feature_fragments: List[str] = []
    if isinstance(feats, list):
        for f in feats:
            text = f.get("text") if isinstance(f, dict) else str(f)
            if not isinstance(text, str):
                continue
            toks = TOKEN_RE.findall(text)
            for t in toks:
                if is_garbled_text(t):
                    dropped_feature_fragments.append(t)
                    continue
                feat_tokens.append(t)
    feat_tokens = dedup([t.lower() for t in feat_tokens])[:16]

    # Query strategy: 2-3 "combo queries" + some singletons
    queries: List[str] = []
    if kws:
        queries.append(" ".join(kws[:3]))
        if len(kws) >= 6:
            queries.append(" ".join(kws[:6]))
        queries.append(" ".join(kws[:2]))
    if feat_tokens:
        queries.append(" ".join(feat_tokens[:5]))
        queries.append(" ".join(feat_tokens[:3]))

    for k in kws[:max_queries]:
        if len(queries) >= max_queries:
            break
        if k not in queries:
            queries.append(k)

    queries = dedup([q for q in queries if is_query_valid(q, min_query_tokens)])[:max_queries]
    warnings: List[str] = []
    dropped_total = len(dropped_cn) + len(dropped_en) + len(dropped_feature_fragments)
    if dropped_total > 0:
        warnings.append(
            f"dropped {dropped_total} garbled keyword/feature fragments (e.g., '?', replacement chars)"
        )
    if not queries:
        warnings.append("no valid queries generated")

    return {
        "keywords_cn": kws_cn_clean,
        "keywords_en": kws_en_clean,
        "dropped_keywords_cn": dropped_cn,
        "dropped_keywords_en": dropped_en,
        "feature_tokens": feat_tokens,
        "queries": queries,
        "warnings": warnings,
    }

def main() -> int:
    p = argparse.ArgumentParser(description="Build patent search queries from invention_profile.json (agent-first)")
    p.add_argument("--profile", required=True, help="invention_profile.json")
    p.add_argument(
        "--agent-queries",
        default="queries.agent.json",
        help="Agent-generated query file (list or {queries:[...]}). Default: queries.agent.json",
    )
    p.add_argument(
        "--query-source",
        choices=["auto", "agent", "profile"],
        default="auto",
        help="auto=agent-first with profile fallback, agent=agent queries only (optional profile merge), profile=profile only",
    )
    p.add_argument(
        "--min-agent-queries",
        type=int,
        default=4,
        help="When --query-source=auto, prefer agent as primary if valid agent queries >= this threshold",
    )
    p.add_argument(
        "--merge-profile",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If true, merge profile-generated queries to fill/expand final set",
    )
    p.add_argument("--out", required=True, help="Output queries.json")
    p.add_argument("--max-queries", type=int, default=8)
    p.add_argument("--min-query-tokens", type=int, default=2, help="Reject generated queries below this token count")
    p.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If true, fail when no valid queries can be generated",
    )
    args = p.parse_args()

    with open(args.profile, "r", encoding="utf-8-sig") as f:
        profile = json.load(f)
    if not isinstance(profile, dict):
        raise SystemExit("profile must be JSON object")

    profile_out = build_queries_from_profile(
        profile,
        max_queries=args.max_queries,
        min_query_tokens=args.min_query_tokens,
    )

    warnings: List[str] = list(profile_out.get("warnings", []))
    agent_raw, agent_load_warning = load_agent_queries(args.agent_queries)
    if agent_load_warning and args.query_source in {"auto", "agent"}:
        warnings.append(agent_load_warning)
    agent_valid, agent_dropped = sanitize_agent_queries(agent_raw, args.min_query_tokens)

    final_queries: List[str] = []
    query_source = "profile"

    if args.query_source == "profile":
        final_queries = list(profile_out["queries"])
        query_source = "profile"
    elif args.query_source == "agent":
        final_queries = list(agent_valid)
        if args.merge_profile and len(final_queries) < args.max_queries:
            final_queries = dedup(final_queries + list(profile_out["queries"]))
        if agent_valid:
            query_source = "agent_primary"
        else:
            query_source = "agent_missing_profile_fallback" if args.merge_profile else "agent_empty"
    else:
        # auto: agent-first, fallback to profile when missing/insufficient
        if len(agent_valid) >= max(1, args.min_agent_queries):
            final_queries = list(agent_valid)
            query_source = "agent_primary"
            if args.merge_profile and len(final_queries) < args.max_queries:
                final_queries = dedup(final_queries + list(profile_out["queries"]))
                query_source = "agent_primary_profile_fill"
        elif agent_valid:
            final_queries = list(agent_valid)
            if args.merge_profile:
                final_queries = dedup(final_queries + list(profile_out["queries"]))
                query_source = "agent_partial_profile_fill"
            else:
                query_source = "agent_partial"
            warnings.append(
                f"agent valid queries below min-agent-queries={args.min_agent_queries}, profile fallback merged"
            )
        else:
            final_queries = list(profile_out["queries"])
            query_source = "profile_fallback_no_agent"

    final_queries = dedup([q for q in final_queries if is_query_valid(q, args.min_query_tokens)])[: args.max_queries]
    if args.strict and not final_queries:
        raise SystemExit("No valid queries generated after agent/profile merge. Fix inputs then retry.")

    out = {
        **profile_out,
        "query_source": query_source,
        "agent_query_file": args.agent_queries,
        "agent_queries_raw_count": len(agent_raw),
        "agent_queries_valid_count": len(agent_valid),
        "dropped_agent_queries": agent_dropped,
        "queries": final_queries,
        "warnings": warnings,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[ok] queries: {len(out['queries'])}")
    for w in out.get("warnings", []):
        print(f"[warn] {w}")
    print(f"[ok] out: {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
