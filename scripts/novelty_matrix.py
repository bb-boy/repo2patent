#!/usr/bin/env python3
"""
novelty_matrix.py - Build feature x prior-art matrix (claims-first).

Inputs:
- invention_profile.json (key_features F1..Fn)
- prior_art_full.json (claims_text + title/abstract)

Outputs:
- novelty_matrix.json with:
  - matrix: per-doc per-feature label/score/snippets
  - novelty_candidates: per-feature NO ratio ranking
  - pair_candidates: low co-occurrence pairs for "novelty combination" candidates

Heuristic, not legal conclusion.
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Any, Dict, List, Tuple

GENERIC = set(["方法","系统","装置","模块","步骤","数据","信息","处理","实现","用于","包括","其中","一种","技术","特征",
               "method","system","device","module","step","data","information","process","processing","implement","including","wherein","a","an","the"])

# Minimal bilingual synonym expansion to reduce CN/EN mismatch (best-effort)
SYN = {
    "cache": ["缓存"],
    "缓存": ["cache"],
    "dedup": ["去重","去重复","重复消除"],
    "去重": ["dedup","deduplication"],
    "scheduler": ["调度","调度器"],
    "调度": ["scheduler","scheduling"],
    "pipeline": ["流水线","管线"],
    "流水线": ["pipeline"],
    "retry": ["重试"],
    "重试": ["retry"],
    "score": ["评分","打分"],
    "scoring": ["评分","打分"],
    "评分": ["score","scoring"],
    "ranking": ["排序"],
    "排序": ["ranking"],
    "vector": ["向量"],
    "向量": ["vector","embedding"],
    "embedding": ["向量","嵌入"],
}

def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,8}", text)
    out: List[str] = []
    for t in tokens:
        tl = t.lower()
        if tl in GENERIC or t in GENERIC:
            continue
        if len(t) < 2:
            continue
        out.append(tl)
        # synonym expansion
        for s in SYN.get(tl, []):
            out.append(str(s).lower())
    # dedup preserve
    seen = set()
    dedup: List[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup

def score_tokens_in_text(tokens: List[str], text: str) -> float:
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in text)
    return hits / len(tokens)

def label(score: float) -> str:
    if score >= 0.6: return "YES"
    if score >= 0.25: return "PARTIAL"
    return "NO"

def extract_snippets(text: str, tokens: List[str], max_snips: int = 3, window: int = 90) -> List[str]:
    """
    Extract short snippets around token matches (best-effort).
    """
    snippets: List[str] = []
    lower = text.lower()
    for tok in tokens:
        if tok not in lower:
            continue
        # find occurrences
        for m in re.finditer(re.escape(tok), lower):
            s = max(0, m.start() - window)
            e = min(len(text), m.end() + window)
            snip = text[s:e].replace("\n", " ").strip()
            snip = re.sub(r"\s{2,}", " ", snip)
            if snip and snip not in snippets:
                snippets.append(snip)
            if len(snippets) >= max_snips:
                return snippets
    return snippets

def load_profile(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise SystemExit("profile must be JSON object")
    return obj

def load_prior_art_full(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if not isinstance(obj, list):
        raise SystemExit("prior_art_full must be JSON list")
    return [d for d in obj if isinstance(d, dict)]

def main() -> int:
    p = argparse.ArgumentParser(description="Build novelty matrix (claims-first)")
    p.add_argument("--profile", required=True, help="invention_profile.json")
    p.add_argument("--prior-art-full", required=True, help="prior_art_full.json")
    p.add_argument("--out", required=True, help="novelty_matrix.json")
    p.add_argument("--max-docs", type=int, default=10)
    p.add_argument("--min-claims-ok-ratio", type=float, default=0.3, help="Minimum acceptable claims_status=ok ratio")
    p.add_argument(
        "--fail-on-low-claims",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If true, exit non-zero when claims quality gate fails",
    )
    args = p.parse_args()

    profile = load_profile(args.profile)
    feats = profile.get("key_features", [])
    if not isinstance(feats, list) or len(feats) < 3:
        raise SystemExit("profile.key_features must be list with >=3 items")

    feature_texts: List[str] = []
    feature_ids: List[str] = []
    feature_tokens: List[List[str]] = []

    for f in feats[:12]:
        if isinstance(f, dict):
            fid = str(f.get("id", "")).strip() or f"F{len(feature_texts)+1}"
            txt = str(f.get("text", "")).strip()
        else:
            fid = f"F{len(feature_texts)+1}"
            txt = str(f).strip()
        if not txt:
            continue
        feature_ids.append(fid)
        feature_texts.append(txt)
        feature_tokens.append(tokenize(txt))

    docs_raw = load_prior_art_full(args.prior_art_full)[: max(1, args.max_docs)]
    claims_status_counts: Dict[str, int] = {}
    for d in docs_raw:
        status = str(d.get("claims_status", "") or "unknown")
        claims_status_counts[status] = claims_status_counts.get(status, 0) + 1
    claims_ok = sum(1 for d in docs_raw if str(d.get("claims_status", "")).lower() in {"ok", "ok_fallback", "manual_ok"})
    claims_total = len(docs_raw)
    claims_ok_ratio = (claims_ok / claims_total) if claims_total else 0.0
    quality_gate = {
        "claims_ok": claims_ok,
        "claims_total": claims_total,
        "claims_ok_ratio": round(claims_ok_ratio, 3),
        "claims_status_counts": claims_status_counts,
        "min_claims_ok_ratio": args.min_claims_ok_ratio,
        "pass": claims_ok_ratio >= max(0.0, args.min_claims_ok_ratio),
    }
    if args.fail_on_low_claims and not quality_gate["pass"]:
        raise SystemExit(
            f"claims quality gate failed: {claims_ok}/{claims_total}={claims_ok_ratio:.3f} "
            f"< min {args.min_claims_ok_ratio:.3f}"
        )

    documents: List[Dict[str, Any]] = []
    for d in docs_raw:
        documents.append({
            "source": d.get("source"),
            "patent_number": d.get("patent_number"),
            "title": d.get("title"),
            "url": d.get("url"),
            "abstract": d.get("abstract",""),
            "claims_status": d.get("claims_status",""),
        })

    # matrix[row_doc][col_feature]
    matrix: List[List[Dict[str, Any]]] = []

    # per feature counts
    counts = [{"NO":0,"PARTIAL":0,"YES":0} for _ in feature_texts]

    # per doc overall match score (sum of best scores)
    doc_overall: List[Tuple[int, float]] = []

    # For pair co-occurrence: count docs where both not NO
    n_feat = len(feature_texts)
    pair_union = [[0]*n_feat for _ in range(n_feat)]
    pair_co = [[0]*n_feat for _ in range(n_feat)]

    for di, d in enumerate(docs_raw):
        claims_text = str(d.get("claims_text","") or "")
        abstract = str(d.get("abstract","") or "")
        claims_lower = claims_text.lower()
        abs_lower = abstract.lower()

        row: List[Dict[str, Any]] = []
        doc_score_sum = 0.0
        labels_for_pairs: List[str] = []

        for fi, (fid, ftxt, toks) in enumerate(zip(feature_ids, feature_texts, feature_tokens)):
            score_claims = score_tokens_in_text(toks, claims_lower) if claims_lower else 0.0
            score_abs = score_tokens_in_text(toks, abs_lower) if abs_lower else 0.0

            # claims-first: use max, but keep both
            best = max(score_claims, score_abs)
            lab = label(best)
            counts[fi][lab] += 1
            labels_for_pairs.append(lab)

            doc_score_sum += best

            # snippets: prefer claims
            snippets = extract_snippets(claims_text if claims_text else abstract, toks, max_snips=3, window=90)

            row.append({
                "feature_id": fid,
                "feature": ftxt,
                "tokens": toks[:12],
                "score_claims": round(score_claims, 3),
                "score_abstract": round(score_abs, 3),
                "score_best": round(best, 3),
                "label": lab,
                "evidence_snippets": snippets,
            })

        # pair stats for this doc
        for i in range(n_feat):
            for j in range(i+1, n_feat):
                li, lj = labels_for_pairs[i], labels_for_pairs[j]
                in_union = (li != "NO") or (lj != "NO")
                in_co = (li != "NO") and (lj != "NO")
                if in_union:
                    pair_union[i][j] += 1
                if in_co:
                    pair_co[i][j] += 1

        matrix.append(row)
        doc_overall.append((di, doc_score_sum))

    # novelty candidates per feature
    n_docs = max(1, len(docs_raw))
    novelty_candidates = []
    for fi, (fid, ftxt, toks) in enumerate(zip(feature_ids, feature_texts, feature_tokens)):
        no_ratio = counts[fi]["NO"] / n_docs
        partial_ratio = counts[fi]["PARTIAL"] / n_docs
        novelty_candidates.append({
            "feature_id": fid,
            "feature": ftxt,
            "no_ratio": round(no_ratio, 3),
            "partial_ratio": round(partial_ratio, 3),
            "yes_count": counts[fi]["YES"],
            "partial_count": counts[fi]["PARTIAL"],
            "no_count": counts[fi]["NO"],
            "tokens": toks[:12],
        })
    novelty_candidates.sort(key=lambda x: (x["no_ratio"], x["partial_ratio"]), reverse=True)

    # pair candidates: high union but low co-occurrence
    pair_candidates = []
    for i in range(n_feat):
        for j in range(i+1, n_feat):
            union = pair_union[i][j]
            co = pair_co[i][j]
            union_ratio = union / n_docs
            co_ratio = co / n_docs
            # interesting if union is non-trivial but co is small
            if union_ratio >= 0.3 and co_ratio <= 0.2:
                pair_candidates.append({
                    "pair": [feature_ids[i], feature_ids[j]],
                    "features": [feature_texts[i], feature_texts[j]],
                    "union_ratio": round(union_ratio, 3),
                    "co_ratio": round(co_ratio, 3),
                    "note": "Both features appear across docs, but rarely appear together (candidate novelty combination).",
                })
    pair_candidates.sort(key=lambda x: (x["union_ratio"], -x["co_ratio"]), reverse=True)
    pair_candidates = pair_candidates[:12]

    # rank docs by overall score
    top_docs = sorted(doc_overall, key=lambda x: x[1], reverse=True)[: min(5, len(doc_overall))]
    top_prior_art = []
    for di, s in top_docs:
        d = documents[di]
        top_prior_art.append({**d, "overall_match": round(s, 3)})

    out = {
        "feature_ids": feature_ids,
        "features": feature_texts,
        "documents": documents,
        "quality_gate": quality_gate,
        "top_prior_art": top_prior_art,
        "matrix": matrix,
        "novelty_candidates": novelty_candidates[:10],
        "pair_candidates": pair_candidates,
        "note": "Heuristic claims-first matrix for preliminary comparison; not a legal novelty conclusion.",
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[ok] features: {len(feature_texts)}, documents: {len(documents)}")
    print(
        f"[ok] claims gate: {claims_ok}/{claims_total}={claims_ok_ratio:.3f} "
        f"(min={args.min_claims_ok_ratio:.3f}, pass={quality_gate['pass']})"
    )
    print(f"[ok] out: {args.out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
