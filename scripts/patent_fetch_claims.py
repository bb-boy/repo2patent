#!/usr/bin/env python3
"""
patent_fetch_claims.py - Fetch claims text for top-k Google Patents results.

Input:
- prior_art.json (from patent_search.py --out-json)

Output:
- prior_art_full.json: list of items with claims_text + claims list (best-effort)

Notes:
- This script only fetches claims from Google Patents pages (patents.google.com).
- HTML structure may change; parsing is best-effort.
- Use --cache-dir to avoid repeated downloads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Any, Dict, List, Optional, Tuple

UA = "Mozilla/5.0 (compatible; PatentAssistant/4.0; +https://example.invalid)"
RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
SUPPORTED_CLAIM_SOURCES = {"google", "espacenet", "cnipa", "lens"}

def sleep_with_jitter(base_seconds: float, jitter: float) -> None:
    if base_seconds <= 0:
        return
    factor = 1.0 + random.uniform(-abs(jitter), abs(jitter))
    time.sleep(max(0.0, base_seconds * factor))

def http_get(
    url: str,
    timeout: int = 30,
    retries: int = 4,
    backoff: float = 1.8,
    jitter: float = 0.25,
) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    max_attempts = max(1, retries + 1)
    last_err: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            return data.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in RETRYABLE_HTTP_STATUS and attempt < max_attempts:
                sleep_with_jitter(backoff ** (attempt - 1), jitter)
                continue
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            last_err = e
            if attempt < max_attempts:
                sleep_with_jitter(backoff ** (attempt - 1), jitter)
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt < max_attempts:
                sleep_with_jitter(backoff ** (attempt - 1), jitter)
                continue
            raise
    raise RuntimeError(f"http_get failed after retries: {last_err}")

def cache_path(cache_dir: str, key: str) -> str:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return os.path.join(cache_dir, f"{h}.html")

def strip_tags_keep_newlines(html: str) -> str:
    # convert some tags to newlines to preserve structure
    html = re.sub(r"(?i)<br\\s*/?>", "\\n", html)
    html = re.sub(r"(?i)</p\\s*>", "\\n", html)
    html = re.sub(r"(?i)</div\\s*>", "\\n", html)
    html = re.sub(r"(?i)</li\\s*>", "\\n", html)
    html = re.sub(r"(?i)<li\\b[^>]*>", "- ", html)
    # remove scripts/styles
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    # remove tags
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = unescape(text)
    # normalize spaces
    text = re.sub(r"[ \\t\\r\\f\\v]+", " ", text)
    # keep newlines but collapse excessive
    text = re.sub(r"\\n\\s*\\n\\s*\\n+", "\\n\\n", text)
    return text.strip()

def extract_claims_section(html: str) -> Optional[str]:
    # Try to locate <section itemprop="claims"> ... </section>
    m = re.search(r'(?is)<section[^>]*itemprop="claims"[^>]*>(.*?)</section>', html)
    if m:
        return m.group(1)
    # Fallback: id="claims"
    m = re.search(r'(?is)<section[^>]*id="claims"[^>]*>(.*?)</section>', html)
    if m:
        return m.group(1)
    # Fallback: "Claims" anchor
    m = re.search(r'(?is)<section[^>]*class="[^"]*claims[^"]*"[^>]*>(.*?)</section>', html)
    if m:
        return m.group(1)
    return None

def split_claims(text: str, max_claims: int = 60) -> List[Dict[str, Any]]:
    """
    Best-effort split claims by numbering: "1. ..." newlines.
    If numbering not present, return one big claim block.
    """
    # Insert newlines before patterns like "1." to help split
    t = re.sub(r"(\\s)(\\d{1,3})\\.", r"\\n\\2.", text)
    parts = re.split(r"\\n\\s*(\\d{1,3})\\.", t)
    if len(parts) <= 1:
        return [{"num": None, "text": text.strip()}]

    claims: List[Dict[str, Any]] = []
    # parts: [prefix, num1, body1, num2, body2, ...]
    prefix = parts[0].strip()
    i = 1
    while i + 1 < len(parts):
        num = parts[i].strip()
        body = parts[i+1].strip()
        if body:
            claims.append({"num": num, "text": body})
        i += 2
        if len(claims) >= max_claims:
            break
    if not claims and prefix:
        claims.append({"num": None, "text": prefix})
    return claims

def normalize_patent_number(pn: Any) -> str:
    return str(pn or "").strip().upper()

def patent_country_code(pn: str) -> str:
    m = re.match(r"^([A-Z]{2})", normalize_patent_number(pn))
    return m.group(1) if m else ""

def choose_claim_sources(it: Dict[str, Any], claim_sources_arg: str) -> List[str]:
    arg = (claim_sources_arg or "auto").strip().lower()
    if arg != "auto":
        selected = [s.strip() for s in arg.split(",") if s.strip()]
        selected = [s for s in selected if s in SUPPORTED_CLAIM_SOURCES]
        return selected or ["google"]

    pn = normalize_patent_number(it.get("patent_number", ""))
    cc = patent_country_code(pn)
    # Country-aware default priority.
    if cc == "CN":
        return ["cnipa", "google", "espacenet", "lens"]
    if cc in {"EP", "WO"}:
        return ["espacenet", "google", "lens", "cnipa"]
    if cc in {"US", "JP", "KR", "DE", "FR", "GB"}:
        return ["google", "espacenet", "lens", "cnipa"]
    return ["google", "espacenet", "cnipa", "lens"]

def classify_fetch_error(err: Exception) -> Tuple[str, str]:
    if isinstance(err, urllib.error.HTTPError):
        if err.code == 403:
            return "fetch_blocked_403", str(err)
        if err.code == 412:
            return "fetch_blocked_412", str(err)
        if err.code == 503:
            return "fetch_failed_503", str(err)
        if err.code == 429:
            return "fetch_failed_429", str(err)
        return f"fetch_failed_http_{err.code}", str(err)
    if isinstance(err, (socket.timeout, TimeoutError)):
        return "fetch_timeout", str(err)
    if isinstance(err, urllib.error.URLError):
        return "fetch_failed_network", str(err)
    return "fetch_failed", str(err)

def build_google_url_candidates(it: Dict[str, Any]) -> List[str]:
    url = str(it.get("url", "") or "").strip()
    pn = normalize_patent_number(it.get("patent_number", ""))
    out: List[str] = []
    if url.startswith("https://patents.google.com/"):
        out.append(url)
    if pn:
        out.append(f"https://patents.google.com/patent/{pn}")
        out.append(f"https://patents.google.com/patent/{pn}/en")
        out.append(f"https://patents.google.com/patent/{pn}?oq={pn}")
    # dedup preserve
    seen = set()
    uniq: List[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq

def build_espacenet_url_candidates(it: Dict[str, Any]) -> List[str]:
    pn = normalize_patent_number(it.get("patent_number", ""))
    if not pn:
        return []
    q = urllib.parse.quote(f"pn={pn}")
    out = [
        f"https://worldwide.espacenet.com/patent/search?q={q}",
        f"https://worldwide.espacenet.com/patent/search/publication/{pn}",
    ]
    return out

def build_cnipa_url_candidates(it: Dict[str, Any]) -> List[str]:
    pn = normalize_patent_number(it.get("patent_number", ""))
    if not pn:
        return []
    q = urllib.parse.quote(pn)
    return [
        f"https://pss-system.cponline.cnipa.gov.cn/conventionalSearch?searchWord={q}",
        f"https://pss-system.cponline.cnipa.gov.cn/seniorSearch?searchWord={q}",
    ]

def build_lens_url_candidates(it: Dict[str, Any]) -> List[str]:
    pn = normalize_patent_number(it.get("patent_number", ""))
    if not pn:
        return []
    q = urllib.parse.quote(pn)
    return [
        f"https://www.lens.org/lens/search/patent/list?q={q}",
        f"https://www.lens.org/search/patent/list?q={q}",
    ]

def build_source_url_candidates(it: Dict[str, Any], source: str) -> List[str]:
    src = source.strip().lower()
    if src == "google":
        return build_google_url_candidates(it)
    if src == "espacenet":
        return build_espacenet_url_candidates(it)
    if src == "cnipa":
        return build_cnipa_url_candidates(it)
    if src == "lens":
        return build_lens_url_candidates(it)
    return []

def extract_claims_fallback_from_text(text: str) -> str:
    if not text:
        return ""
    lower = text.lower()
    keywords = ["\nclaims", "\nclaim", "权利要求书", "权利要求"]
    starts = [lower.find(k) for k in keywords if lower.find(k) >= 0]
    if not starts:
        return ""
    s = min(starts)
    e = min(len(text), s + 40000)
    return text[s:e].strip()

def parse_claims_from_html(source: str, html: str) -> Tuple[str, List[Dict[str, Any]], str]:
    sec = extract_claims_section(html)
    if sec:
        text = strip_tags_keep_newlines(sec)
        claims = split_claims(text) if text else []
        return text[:200000], claims, "ok" if text else "empty"

    # Fallback parser for non-Google pages where claims may appear in flattened text.
    flat_text = strip_tags_keep_newlines(html)
    fallback = extract_claims_fallback_from_text(flat_text)
    if fallback:
        claims = split_claims(fallback)
        return fallback[:200000], claims, "ok_fallback"

    return "", [], "claims_section_not_found"

def load_json_file(path: str, default: Any) -> Any:
    if not path or not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def merge_manual_claims(
    out_items: List[Dict[str, Any]],
    manual_claims_path: Optional[str],
) -> List[Dict[str, Any]]:
    if not manual_claims_path:
        return out_items
    manual_obj = load_json_file(manual_claims_path, default=[])
    manual_map: Dict[str, Dict[str, Any]] = {}
    if isinstance(manual_obj, dict):
        records = manual_obj.get("items", [])
    else:
        records = manual_obj
    if not isinstance(records, list):
        records = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        pn = normalize_patent_number(rec.get("patent_number", ""))
        if not pn:
            continue
        manual_map[pn] = rec

    if not manual_map:
        return out_items

    # apply manual claims to existing items
    for it in out_items:
        pn = normalize_patent_number(it.get("patent_number", ""))
        manual = manual_map.get(pn)
        if not manual:
            continue
        claims_text = str(manual.get("claims_text", "") or "").strip()
        claims_list = manual.get("claims")
        if claims_text:
            claims = split_claims(claims_text)
            it["claims_text"] = claims_text[:200000]
            it["claims"] = claims
            it["claims_status"] = "manual_ok"
            it["claims_error"] = ""
            it["manual_claims_source"] = manual_claims_path
        elif isinstance(claims_list, list) and claims_list:
            normalized_claims: List[Dict[str, Any]] = []
            parts: List[str] = []
            for idx, c in enumerate(claims_list, start=1):
                if isinstance(c, dict):
                    num = c.get("num")
                    txt = str(c.get("text", "")).strip()
                else:
                    num = idx
                    txt = str(c).strip()
                if not txt:
                    continue
                normalized_claims.append({"num": num, "text": txt})
                parts.append(f"{num}. {txt}" if num is not None else txt)
            if normalized_claims:
                it["claims"] = normalized_claims
                it["claims_text"] = "\n".join(parts)[:200000]
                it["claims_status"] = "manual_ok"
                it["claims_error"] = ""
                it["manual_claims_source"] = manual_claims_path
    return out_items

def main() -> int:
    p = argparse.ArgumentParser(description="Fetch claims for Google Patents results")
    p.add_argument("--in", dest="input_path", required=True, help="prior_art.json")
    p.add_argument("--topk", type=int, default=10, help="Top K patents to fetch claims for")
    p.add_argument("--out", required=True, help="Output prior_art_full.json")
    p.add_argument("--cache-dir", default=".patent_assistant/patent_cache", help="Cache dir for HTML")
    p.add_argument("--sleep", type=float, default=1.0, help="Sleep seconds between requests")
    p.add_argument("--force", action="store_true", help="Ignore cache and refetch")
    p.add_argument("--timeout", type=int, default=40, help="HTTP timeout seconds")
    p.add_argument("--retries", type=int, default=4, help="Retry attempts on timeout/5xx/429")
    p.add_argument("--backoff", type=float, default=1.8, help="Exponential backoff base")
    p.add_argument("--jitter", type=float, default=0.25, help="Retry sleep jitter")
    p.add_argument(
        "--claim-sources",
        default="auto",
        help="Claim source priority: auto or comma-separated subset of google,espacenet,cnipa,lens",
    )
    p.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Reuse existing --out records and skip already-ok items",
    )
    p.add_argument("--manual-claims", default=None, help="JSON file to merge manual claims (fallback for non-Google)")
    p.add_argument("--require-min-ok-ratio", type=float, default=0.0, help="Exit non-zero if ok ratio below threshold")
    args = p.parse_args()

    os.makedirs(args.cache_dir, exist_ok=True)

    with open(args.input_path, "r", encoding="utf-8-sig") as f:
        prior = json.load(f)
    if not isinstance(prior, list):
        raise SystemExit("prior_art.json must be a JSON list")

    existing_map: Dict[str, Dict[str, Any]] = {}
    if args.resume and os.path.exists(args.out) and (not args.force):
        old = load_json_file(args.out, default=[])
        if isinstance(old, list):
            for rec in old:
                if not isinstance(rec, dict):
                    continue
                key = normalize_patent_number(rec.get("patent_number", ""))
                if key:
                    existing_map[key] = rec

    # Keep top-k items with patent_number/url.
    items: List[Dict[str, Any]] = []
    seen = set()
    for it in prior:
        if not isinstance(it, dict):
            continue
        pn = normalize_patent_number(it.get("patent_number"))
        url = str(it.get("url", "") or "").strip()
        if not pn and not url:
            continue
        key = pn or url
        if key in seen:
            continue
        seen.add(key)
        items.append(it)

    def claimability_score(it: Dict[str, Any]) -> Tuple[int, int, int]:
        pn = normalize_patent_number(it.get("patent_number", ""))
        url = str(it.get("url", "") or "").strip().lower()
        src = str(it.get("source", "") or "").strip().lower()
        has_pn = 1 if pn else 0
        google_url = 1 if "patents.google.com/patent/" in url else 0
        google_source = 1 if src == "google patents" else 0
        return (has_pn, google_url, google_source)

    # Prefer claim-eligible records (patent number + direct patent URL).
    items = sorted(items, key=claimability_score, reverse=True)
    items = items[: max(1, args.topk)]
    out_items: List[Dict[str, Any]] = []

    for idx, it in enumerate(items, 1):
        pn = normalize_patent_number(it.get("patent_number", ""))
        source = str(it.get("source", "") or "").strip()

        existing = existing_map.get(pn)
        if existing and str(existing.get("claims_status", "")) in {"ok", "manual_ok"} and (not args.force):
            out_items.append(existing)
            continue

        source_priority = choose_claim_sources(it, args.claim_sources)
        any_candidate = False
        claims_text = ""
        claims: List[Dict[str, Any]] = []
        claims_status = ""
        claims_page_url = ""
        claims_source = ""
        fetched = False
        had_fetch_success = False
        last_error: Optional[Exception] = None
        had_parse_no_claims = False
        attempt_logs: List[Dict[str, Any]] = []

        for src in source_priority:
            candidates = build_source_url_candidates(it, src)
            if not candidates:
                continue
            any_candidate = True
            for candidate in candidates:
                cpath = cache_path(args.cache_dir, f"{src}:{candidate}")
                html = ""
                from_cache = False

                if (not args.force) and os.path.exists(cpath):
                    with open(cpath, "r", encoding="utf-8", errors="replace") as f:
                        html = f.read()
                    from_cache = True
                    had_fetch_success = True
                else:
                    try:
                        html = http_get(
                            candidate,
                            timeout=args.timeout,
                            retries=args.retries,
                            backoff=args.backoff,
                            jitter=args.jitter,
                        )
                        with open(cpath, "w", encoding="utf-8") as f:
                            f.write(html)
                        fetched = True
                        had_fetch_success = True
                    except Exception as e:
                        last_error = e
                        status, err_msg = classify_fetch_error(e)
                        attempt_logs.append(
                            {
                                "source": src,
                                "url": candidate,
                                "result": status,
                                "error": err_msg,
                            }
                        )
                        continue

                parsed_text, parsed_claims, parsed_status = parse_claims_from_html(src, html)
                attempt_logs.append(
                    {
                        "source": src,
                        "url": candidate,
                        "result": parsed_status,
                        "from_cache": from_cache,
                        "claims_count": len(parsed_claims),
                    }
                )
                if parsed_text:
                    claims_text = parsed_text
                    claims = parsed_claims
                    claims_status = "ok" if parsed_status == "ok" else parsed_status
                    claims_page_url = candidate
                    claims_source = src
                    break
                had_parse_no_claims = True
            if claims_text:
                break

        if claims_text:
            out_items.append({
                **it,
                "claims_status": claims_status,
                "claims_error": "",
                "claims_text": claims_text[:200000],
                "claims": claims,
                "claims_source": claims_source,
                "claims_page_url": claims_page_url,
                "claims_fetch_attempts": attempt_logs,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            if idx < len(items):
                sleep_with_jitter(max(0.0, args.sleep), args.jitter if fetched else max(args.jitter, 0.35))
            continue

        if not any_candidate:
            out_items.append({
                **it,
                "claims_status": "missing_patent_number_or_url",
                "claims_error": "No patent number/url available for claim source routing",
                "claims_text": "",
                "claims": [],
                "claims_source": "",
                "claims_page_url": str(it.get("url", "") or ""),
                "claims_fetch_attempts": attempt_logs,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            if idx < len(items):
                sleep_with_jitter(max(0.0, args.sleep), args.jitter)
            continue

        if had_fetch_success and had_parse_no_claims:
            err_summary = ""
            if last_error is not None:
                last_status, last_msg = classify_fetch_error(last_error)
                err_summary = f"no claims found in fetched pages; last fetch error: {last_status} {last_msg}"
            else:
                err_summary = "no claims found in fetched pages"
            out_items.append({
                **it,
                "claims_status": "claims_section_not_found",
                "claims_error": err_summary,
                "claims_text": "",
                "claims": [],
                "claims_source": "",
                "claims_page_url": str(it.get("url", "") or ""),
                "claims_fetch_attempts": attempt_logs,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            if idx < len(items):
                sleep_with_jitter(max(0.0, args.sleep), args.jitter)
            continue

        if last_error is not None:
            status, err_msg = classify_fetch_error(last_error or RuntimeError("unknown fetch error"))
            out_items.append({
                **it,
                "claims_status": status,
                "claims_error": err_msg,
                "claims_text": "",
                "claims": [],
                "claims_source": "",
                "claims_page_url": str(it.get("url", "") or ""),
                "claims_fetch_attempts": attempt_logs,
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
            if idx < len(items):
                sleep_with_jitter(max(0.0, args.sleep), args.jitter)
            continue

        out_items.append({
            **it,
            "claims_status": "fetch_failed",
            "claims_error": "Unknown claims fetch failure",
            "claims_text": "",
            "claims": [],
            "claims_source": "",
            "claims_page_url": str(it.get("url", "") or ""),
            "claims_fetch_attempts": attempt_logs,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

        # sleep between requests to reduce anti-bot triggers
        if idx < len(items):
            sleep_with_jitter(max(0.0, args.sleep), args.jitter if fetched else max(args.jitter, 0.35))

    out_items = merge_manual_claims(out_items, args.manual_claims)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_items, f, ensure_ascii=False, indent=2)

    status_counts: Dict[str, int] = {}
    for x in out_items:
        s = str(x.get("claims_status", "unknown"))
        status_counts[s] = status_counts.get(s, 0) + 1

    ok = sum(1 for x in out_items if x.get("claims_status") in {"ok", "ok_fallback", "manual_ok"})
    total = len(out_items)
    ok_ratio = (ok / total) if total else 0.0
    print(f"[ok] fetched claims: {ok}/{total} (ratio={ok_ratio:.3f})")
    print(f"[ok] status counts: {status_counts}")
    print(f"[ok] out: {args.out}")
    if ok_ratio < max(0.0, args.require_min_ok_ratio):
        print(
            f"[error] ok_ratio {ok_ratio:.3f} < require_min_ok_ratio {args.require_min_ok_ratio:.3f}",
            file=sys.stderr,
        )
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
