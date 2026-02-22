#!/usr/bin/env python3
"""
patent_search.py - strict patent recall search for repo2patent Step 7.

Primary path:
- Google Patents xhr/query API

Fallback paths:
- Google Patents HTML search result parsing
- Espacenet/Lens/CNIPA search page publication-number parsing
"""
from __future__ import annotations

import argparse
import json
import random
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

RETRYABLE_HTTP_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
PATENT_URL_RE = re.compile(r"/patent/([A-Za-z0-9]+)", re.IGNORECASE)
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,8}")
PUB_NO_RE = re.compile(r"\b(?:CN|US|EP|WO|JP|KR|DE|FR|GB)\d{6,14}[A-Z0-9]{0,4}\b", re.IGNORECASE)

ALLOWED_RESULT_SOURCES = {"Google Patents", "Lens.org", "Espacenet", "CNIPA"}
FORBIDDEN_SOURCE_MARKERS = ("manual", "fallback", "synthetic", "mock", "test")
MOJIBAKE_MARKERS = set("锛銆鍙鏃鏈鍥鍚鎴闂涓崭笓鍒妫索")


def _sleep_with_jitter(base_seconds: float, jitter: float) -> None:
    if base_seconds <= 0:
        return
    factor = 1.0 + random.uniform(-abs(jitter), abs(jitter))
    time.sleep(max(0.0, base_seconds * factor))


def _http_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.8,
    jitter: float = 0.25,
) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    max_attempts = max(1, retries + 1)
    last_err: Optional[Exception] = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in RETRYABLE_HTTP_STATUS and attempt < max_attempts:
                _sleep_with_jitter(backoff ** (attempt - 1), jitter)
                continue
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            last_err = e
            if attempt < max_attempts:
                _sleep_with_jitter(backoff ** (attempt - 1), jitter)
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt < max_attempts:
                _sleep_with_jitter(backoff ** (attempt - 1), jitter)
                continue
            raise
    raise RuntimeError(f"HTTP GET failed after retries: {last_err}")


def is_garbled_text(text: str) -> bool:
    s = str(text).strip()
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


def query_token_count(query: str) -> int:
    tokens = TOKEN_RE.findall(query)
    return len([t for t in tokens if not is_garbled_text(t)])


def sanitize_queries(raw_queries: List[str], min_tokens: int) -> Tuple[List[str], List[Dict[str, Any]]]:
    valid: List[str] = []
    dropped: List[Dict[str, Any]] = []
    seen = set()
    for q in raw_queries:
        query = str(q).strip()
        if not query:
            continue
        reason = ""
        if is_garbled_text(query):
            reason = "garbled_query"
        elif query_token_count(query) < max(1, min_tokens):
            reason = "too_few_tokens"
        if reason:
            dropped.append({"query": query, "reason": reason})
            continue
        if query in seen:
            continue
        seen.add(query)
        valid.append(query)
    return valid, dropped


def dedup_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for it in items:
        source = str(it.get("source", ""))
        patent_number = str(it.get("patent_number", "")).strip()
        url = str(it.get("url", "")).strip()
        if patent_number:
            key = (source, patent_number)
        elif url:
            key = (source, url)
        else:
            key = (source, str(it.get("title", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def validate_result_items(items: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    for i, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            errors.append(f"item[{i}] is not object")
            continue
        source = str(it.get("source", "")).strip()
        source_l = source.lower()
        if any(mark in source_l for mark in FORBIDDEN_SOURCE_MARKERS):
            errors.append(f"item[{i}] has forbidden source marker: {source}")
        if source and source not in ALLOWED_RESULT_SOURCES:
            errors.append(f"item[{i}] has unknown source: {source}")

        is_note_only = "note" in it
        if not is_note_only:
            title = str(it.get("title", "")).strip()
            patent_number = str(it.get("patent_number", "")).strip()
            url = str(it.get("url", "")).strip()
            if not title:
                errors.append(f"item[{i}] missing title")
            if not (patent_number or url):
                errors.append(f"item[{i}] missing patent_number/url")
    return errors


def count_unique_patents(items: List[Dict[str, Any]]) -> int:
    uniq = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        if "note" in it:
            continue
        pn = str(it.get("patent_number", "")).strip().upper()
        if pn:
            uniq.add(pn)
            continue
        url = str(it.get("url", "")).strip()
        m = PATENT_URL_RE.search(url)
        if m:
            uniq.add(m.group(1).upper())
    return len(uniq)


def _extract_publication_numbers(html_text: str, country: str, max_items: int) -> List[str]:
    country_u = str(country or "").strip().upper()
    out: List[str] = []
    seen = set()
    for m in PUB_NO_RE.finditer(html_text):
        pn = m.group(0).upper()
        if country_u and len(country_u) == 2:
            if not (pn.startswith(country_u) or pn.startswith("WO") or pn.startswith("EP")):
                continue
        if pn in seen:
            continue
        seen.add(pn)
        out.append(pn)
        if len(out) >= max_items:
            break
    return out


def _pn_url_for_source(source: str, pn: str) -> str:
    s = source.strip().lower()
    if s == "google patents":
        return f"https://patents.google.com/patent/{pn}"
    if s == "espacenet":
        return f"https://worldwide.espacenet.com/patent/search/publication/{pn}"
    if s == "lens.org":
        q = urllib.parse.quote(pn)
        return f"https://www.lens.org/lens/search/patent/list?q={q}"
    if s == "cnipa":
        q = urllib.parse.quote(pn)
        return f"https://pss-system.cponline.cnipa.gov.cn/conventionalSearch?searchWord={q}"
    return ""


def _records_from_search_page(
    source: str,
    search_url: str,
    query: str,
    limit: int,
    country: str,
    timeout: int,
    retries: int,
    backoff: float,
    jitter: float,
) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    raw = _http_get(search_url, headers=headers, timeout=timeout, retries=retries, backoff=backoff, jitter=jitter)
    text = raw.decode("utf-8", errors="replace")
    pns = _extract_publication_numbers(text, country=country, max_items=max(30, limit * 3))
    out: List[Dict[str, Any]] = []
    for pn in pns[:limit]:
        out.append(
            {
                "source": source,
                "patent_number": pn,
                "title": f"{pn} ({source} recall)",
                "abstract": "",
                "url": _pn_url_for_source(source, pn),
                "recall_method": "search_page_regex",
            }
        )
    return out


def search_google_patents_xhr(
    query: str,
    limit: int,
    country: str,
    timeout: int,
    retries: int,
    backoff: float,
    jitter: float,
) -> List[Dict[str, Any]]:
    encoded_query = urllib.parse.quote(f"{query} country:{country}")
    url = f"https://patents.google.com/xhr/query?url=q%3D{encoded_query}&num={limit}&exp="
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    raw = _http_get(url, headers=headers, timeout=timeout, retries=retries, backoff=backoff, jitter=jitter)
    data = json.loads(raw.decode("utf-8", errors="replace"))
    results: List[Dict[str, Any]] = []
    clusters = (data.get("results") or {}).get("cluster") or []
    for cluster in clusters:
        for result in cluster.get("result", []) or []:
            patent = result.get("patent") or {}
            pub = str(patent.get("publication_number", "") or "").strip()
            title = str(patent.get("title", "") or "").replace("<b>", "").replace("</b>", "").strip()
            abstract = str(patent.get("abstract", "") or "").replace("<b>", "").replace("</b>", "").strip()
            if not (pub or title):
                continue
            results.append(
                {
                    "source": "Google Patents",
                    "patent_number": pub,
                    "title": title or f"{pub} (Google Patents)",
                    "abstract": abstract[:1500],
                    "assignee": str(patent.get("assignee", "") or ""),
                    "filing_date": str(patent.get("filing_date", "") or ""),
                    "url": f"https://patents.google.com/patent/{pub}" if pub else "",
                    "recall_method": "google_xhr",
                }
            )
    return results[:limit]


def search_google_patents_html(
    query: str,
    limit: int,
    country: str,
    timeout: int,
    retries: int,
    backoff: float,
    jitter: float,
) -> List[Dict[str, Any]]:
    q = urllib.parse.quote(f"{query} country:{country}")
    url = f"https://patents.google.com/?q={q}"
    out = _records_from_search_page(
        source="Google Patents",
        search_url=url,
        query=query,
        limit=limit,
        country=country,
        timeout=timeout,
        retries=retries,
        backoff=backoff,
        jitter=jitter,
    )
    for x in out:
        x["recall_method"] = "google_html"
    return out


def search_google_patents(
    query: str,
    limit: int = 30,
    country: str = "CN",
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.8,
    jitter: float = 0.25,
) -> List[Dict[str, Any]]:
    last_err: Optional[Exception] = None
    try:
        xhr_items = search_google_patents_xhr(query, limit, country, timeout, retries, backoff, jitter)
        if xhr_items:
            return xhr_items[:limit]
    except Exception as e:
        last_err = e

    try:
        html_items = search_google_patents_html(query, limit, country, timeout, retries, backoff, jitter)
        if html_items:
            return html_items[:limit]
    except Exception as e:
        last_err = e

    if last_err is not None:
        raise last_err
    return []


def search_lens(
    query: str,
    limit: int = 20,
    country: str = "CN",
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.8,
    jitter: float = 0.25,
) -> List[Dict[str, Any]]:
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.lens.org/lens/search/patent/list?q={encoded_query}&n={limit}"
    try:
        items = _records_from_search_page(
            source="Lens.org",
            search_url=url,
            query=query,
            limit=limit,
            country=country,
            timeout=timeout,
            retries=retries,
            backoff=backoff,
            jitter=jitter,
        )
        if items:
            return items
    except Exception:
        pass
    return [{"source": "Lens.org", "note": "Lens 页面解析失败，仅返回检索链接。", "url": url}]


def search_espacenet(
    query: str,
    limit: int = 20,
    country: str = "CN",
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.8,
    jitter: float = 0.25,
) -> List[Dict[str, Any]]:
    encoded_query = urllib.parse.quote(query)
    url = f"https://worldwide.espacenet.com/patent/search?q={encoded_query}"
    try:
        items = _records_from_search_page(
            source="Espacenet",
            search_url=url,
            query=query,
            limit=limit,
            country=country,
            timeout=timeout,
            retries=retries,
            backoff=backoff,
            jitter=jitter,
        )
        if items:
            return items
    except Exception:
        pass
    return [{"source": "Espacenet", "note": "Espacenet 页面解析失败，仅返回检索链接。", "url": url}]


def search_cnipa(
    query: str,
    limit: int = 20,
    country: str = "CN",
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.8,
    jitter: float = 0.25,
) -> List[Dict[str, Any]]:
    encoded_query = urllib.parse.quote(query)
    url = f"https://pss-system.cponline.cnipa.gov.cn/conventionalSearch?searchWord={encoded_query}"
    try:
        items = _records_from_search_page(
            source="CNIPA",
            search_url=url,
            query=query,
            limit=limit,
            country=country,
            timeout=timeout,
            retries=retries,
            backoff=backoff,
            jitter=jitter,
        )
        if items:
            return items
    except Exception:
        pass
    return [{"source": "CNIPA", "note": "CNIPA 页面解析失败，仅返回检索链接。", "url": url}]


def analyze_similarity(query: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kws = [k for k in re.split(r"\s+", query.lower().strip()) if k]
    kw_set = set(kws)
    for it in items:
        if "note" in it:
            continue
        text = f"{it.get('title','')} {it.get('abstract','')}".lower()
        matched = sum(1 for kw in kw_set if kw in text) if kw_set else 0
        it["similarity_score"] = round((matched / len(kw_set) * 100.0), 1) if kw_set else 0.0
    return sorted(items, key=lambda d: d.get("similarity_score", 0.0), reverse=True)


def run_sources(
    query: str,
    sources: List[str],
    limit: int,
    country: str,
    parallel: bool,
    timeout: int,
    retries: int,
    backoff: float,
    jitter: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    funcs: Dict[str, Callable[[str], List[Dict[str, Any]]]] = {
        "google": lambda q: search_google_patents(q, limit, country, timeout, retries, backoff, jitter),
        "lens": lambda q: search_lens(q, limit, country, timeout, retries, backoff, jitter),
        "espacenet": lambda q: search_espacenet(q, limit, country, timeout, retries, backoff, jitter),
        "cnipa": lambda q: search_cnipa(q, limit, country, timeout, retries, backoff, jitter),
    }
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    if parallel and len(sources) > 1:
        with ThreadPoolExecutor(max_workers=len(sources)) as ex:
            fut = {ex.submit(funcs[s], query): s for s in sources if s in funcs}
            for f in as_completed(fut):
                src = fut[f]
                try:
                    results.extend(f.result())
                except Exception as e:
                    failures.append(
                        {
                            "query": query,
                            "source": src,
                            "error": str(e),
                            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                    )
                    print(f"[{src}] 搜索失败: {e}", file=sys.stderr)
    else:
        for s in sources:
            if s not in funcs:
                continue
            try:
                results.extend(funcs[s](query))
            except Exception as e:
                failures.append(
                    {
                        "query": query,
                        "source": s,
                        "error": str(e),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                )
                print(f"[{s}] 搜索失败: {e}", file=sys.stderr)
    return results, failures


def load_queries(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8-sig") as f:
        obj = json.load(f)
    if isinstance(obj, dict) and isinstance(obj.get("queries"), list):
        return [str(q) for q in obj["queries"] if str(q).strip()]
    if isinstance(obj, list):
        return [str(q) for q in obj if str(q).strip()]
    raise ValueError("queries.json must be a list or {queries:[...]}")


def main() -> int:
    p = argparse.ArgumentParser(description="Patent recall search (strict workflow mode).")
    p.add_argument("--queries", help="queries.json (list or {queries:[...]})")
    p.add_argument("query", nargs="?", help="single query")
    p.add_argument("--limit", "-n", type=int, default=30)
    p.add_argument("--country", "-c", default="CN")
    p.add_argument("--source", "-s", default="google", help="google/lens/espacenet/cnipa/all")
    p.add_argument("--analyze", "-a", action="store_true", help="sort by keyword-match score")
    p.add_argument("--parallel", "-p", action="store_true")
    p.add_argument("--timeout", type=int, default=45, help="HTTP timeout seconds")
    p.add_argument("--retries", type=int, default=4, help="retry attempts on timeout/5xx/429")
    p.add_argument("--backoff", type=float, default=1.8, help="exponential backoff base")
    p.add_argument("--jitter", type=float, default=0.25, help="retry sleep jitter")
    p.add_argument("--query-sleep", type=float, default=2.0, help="sleep between queries")
    p.add_argument("--query-jitter", type=float, default=0.3, help="query sleep jitter")
    p.add_argument("--min-query-tokens", type=int, default=2, help="drop low-information queries")
    p.add_argument(
        "--strict-query-quality",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="fail when all queries are dropped by quality gate",
    )
    p.add_argument(
        "--strict-source-integrity",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="fail when source looks synthetic/unknown",
    )
    p.add_argument("--fail-on-empty", action="store_true", help="exit non-zero when no recall items")
    p.add_argument("--min-unique-patents", type=int, default=0, help="minimum unique patent hits")
    p.add_argument("--fail-on-low-recall", action="store_true", help="exit non-zero when recall below threshold")
    p.add_argument("--out-json", default=None, help="write prior_art.json")
    p.add_argument("--out-md", default=None, help="write prior_art.md")
    p.add_argument("--failures-json", default=None, help="write structured failures")
    args = p.parse_args()

    sources = (
        ["google", "lens", "espacenet", "cnipa"]
        if args.source == "all"
        else [s.strip().lower() for s in args.source.split(",") if s.strip()]
    )

    if args.queries:
        queries = load_queries(args.queries)
    elif args.query:
        queries = [args.query]
    else:
        raise SystemExit("Provide query or --queries")

    valid_queries, dropped_queries = sanitize_queries(queries, min_tokens=args.min_query_tokens)
    for dq in dropped_queries:
        print(f"[warn] dropped low-quality query: {dq['query']} ({dq['reason']})", file=sys.stderr)
    if args.strict_query_quality and not valid_queries:
        raise SystemExit("All queries failed quality gate. Fix encoding/keywords and retry.")
    if not valid_queries:
        valid_queries = queries

    all_items: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for i, q in enumerate(valid_queries, start=1):
        items, errs = run_sources(
            q,
            sources=sources,
            limit=args.limit,
            country=args.country,
            parallel=args.parallel,
            timeout=args.timeout,
            retries=args.retries,
            backoff=args.backoff,
            jitter=args.jitter,
        )
        failures.extend(errs)
        if args.analyze:
            items = analyze_similarity(q, items)
        for it in items:
            it["query"] = q
            it["query_index"] = i
        all_items.extend(items)
        if i < len(valid_queries):
            _sleep_with_jitter(args.query_sleep, args.query_jitter)

    all_items = dedup_items(all_items)
    validation_errors = validate_result_items(all_items)
    if validation_errors and args.strict_source_integrity:
        raise SystemExit("prior_art validation failed:\n- " + "\n- ".join(validation_errors[:20]))

    unique_patents = count_unique_patents(all_items)

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)
        print(f"[ok] written json: {args.out_json}", file=sys.stderr)

    if args.out_md:
        by: Dict[str, List[Dict[str, Any]]] = {}
        for it in all_items:
            by.setdefault(str(it.get("source", "Unknown")), []).append(it)

        lines: List[str] = ["## 专利检索结果\n"]
        for src, arr in by.items():
            lines.append(f"### {src}\n")
            for i, it in enumerate(arr, start=1):
                if "note" in it:
                    lines.append(f"- 提示：{it.get('note', '')}")
                    if it.get("url"):
                        lines.append(f"  - 链接：{it['url']}")
                    continue
                lines.append(f"{i}. **{it.get('title', '(no title)')}**")
                if it.get("patent_number"):
                    lines.append(f"   - 专利号：{it['patent_number']}")
                if it.get("similarity_score") is not None:
                    lines.append(f"   - 相似度：{it.get('similarity_score', 0)}%")
                if it.get("url"):
                    lines.append(f"   - 链接：{it['url']}")
                if it.get("abstract"):
                    a = str(it["abstract"]).replace("\n", " ").strip()
                    lines.append(f"   - 摘要：{a[:220]}{'...' if len(a) > 220 else ''}")
            lines.append("")
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[ok] written md: {args.out_md}", file=sys.stderr)

    failures_json = args.failures_json or (f"{args.out_json}.failures.json" if args.out_json else None)
    if failures_json:
        with open(failures_json, "w", encoding="utf-8") as f:
            json.dump(failures, f, ensure_ascii=False, indent=2)
        if failures:
            print(f"[warn] failures logged: {failures_json} ({len(failures)})", file=sys.stderr)

    if not args.out_json and not args.out_md:
        print(json.dumps(all_items, ensure_ascii=False, indent=2))
    else:
        print(f"[ok] total items: {len(all_items)}", file=sys.stderr)
        print(f"[ok] unique patents: {unique_patents}", file=sys.stderr)
        print(f"[ok] valid queries: {len(valid_queries)}, dropped queries: {len(dropped_queries)}", file=sys.stderr)
        print(f"[ok] source failures: {len(failures)}", file=sys.stderr)

    if args.fail_on_empty and len(all_items) == 0:
        return 2
    if args.fail_on_low_recall and unique_patents < max(0, args.min_unique_patents):
        print(
            f"[error] unique patents {unique_patents} < min_unique_patents {args.min_unique_patents}",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
