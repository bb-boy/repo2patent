#!/usr/bin/env python3
"""
patent_search.py - initial patent search (recall stage).

Mandatory in the Skill workflow. At minimum, use Google Patents.

It mainly returns title+abstract (+meta). Full claims are fetched in the next step:
- scripts/patent_fetch_claims.py (mandatory)

Notes:
- Some sources require JS/login; for those we output search links.
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
    return False

def query_token_count(query: str) -> int:
    toks = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,8}", query)
    return len([t for t in toks if not is_garbled_text(t)])

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

def search_google_patents(
    query: str,
    limit: int = 30,
    country: str = "CN",
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.8,
    jitter: float = 0.25,
) -> List[Dict[str, Any]]:
    encoded_query = urllib.parse.quote(f"{query} country:{country}")
    url = f"https://patents.google.com/xhr/query?url=q%3D{encoded_query}&num={limit}&exp="
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    raw = _http_get(
        url,
        headers=headers,
        timeout=timeout,
        retries=retries,
        backoff=backoff,
        jitter=jitter,
    )
    data = json.loads(raw.decode("utf-8", errors="replace"))
    results: List[Dict[str, Any]] = []
    clusters = (data.get("results") or {}).get("cluster") or []
    for cluster in clusters:
        for result in cluster.get("result", []) or []:
            patent = (result.get("patent") or {})
            pub = patent.get("publication_number", "") or ""
            title = (patent.get("title", "") or "").replace("<b>", "").replace("</b>", "")
            abstract = (patent.get("abstract", "") or "").replace("<b>", "").replace("</b>", "")
            results.append({
                "source": "Google Patents",
                "patent_number": pub,
                "title": title.strip(),
                "abstract": abstract[:1500].strip(),
                "assignee": patent.get("assignee", "") or "",
                "filing_date": patent.get("filing_date", "") or "",
                "url": f"https://patents.google.com/patent/{pub}" if pub else "",
            })
    return results[:limit]

def search_lens(query: str, limit: int = 20) -> List[Dict]:
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.lens.org/lens/search/patent/list?q={encoded_query}&n={limit}"
    return [{"source":"Lens.org","note":"Lens 页面结构可能变化，建议浏览器访问检索链接","url":url}]

def search_espacenet(query: str, limit: int = 20) -> List[Dict]:
    encoded_query = urllib.parse.quote(query)
    url = f"https://worldwide.espacenet.com/patent/search?q={encoded_query}"
    return [{"source":"Espacenet","note":"需浏览器访问，此处提供搜索链接","url":url}]

def search_cnipa(query: str, limit: int = 20) -> List[Dict]:
    encoded_query = urllib.parse.quote(query)
    url = f"https://pss-system.cponline.cnipa.gov.cn/conventionalSearch?searchWord={encoded_query}"
    return [{"source":"国知局CNIPA","note":"官方数据库通常需要登录，此处提供搜索链接","url":url}]

def analyze_similarity(query: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    kws = [k for k in re.split(r"\\s+", query.lower().strip()) if k]
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
        "lens": lambda q: search_lens(q, limit),
        "espacenet": lambda q: search_espacenet(q, limit),
        "cnipa": lambda q: search_cnipa(q, limit),
    }
    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    if parallel and len(sources) > 1:
        with ThreadPoolExecutor(max_workers=len(sources)) as ex:
            fut = {ex.submit(funcs[s], query): s for s in sources if s in funcs}
            for f in as_completed(fut):
                try:
                    results.extend(f.result())
                except Exception as e:
                    failures.append(
                        {
                            "query": query,
                            "source": fut[f],
                            "error": str(e),
                            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                    )
                    print(f"[{fut[f]}] 搜索失败: {e}", file=sys.stderr)
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
    p = argparse.ArgumentParser(description="多平台专利检索（召回阶段）")
    p.add_argument("--queries", help="queries.json（list 或 {queries:[...]})")
    p.add_argument("query", nargs="?", help="单条检索关键词（空格分隔）")
    p.add_argument("--limit","-n", type=int, default=30)
    p.add_argument("--country","-c", default="CN")
    p.add_argument("--source","-s", default="google", help="google/lens/espacenet/cnipa/all")
    p.add_argument("--analyze","-a", action="store_true", help="相似度（关键词命中）排序")
    p.add_argument("--parallel","-p", action="store_true")
    p.add_argument("--timeout", type=int, default=45, help="HTTP timeout seconds")
    p.add_argument("--retries", type=int, default=4, help="Retry attempts on timeout/5xx/429")
    p.add_argument("--backoff", type=float, default=1.8, help="Exponential backoff base")
    p.add_argument("--jitter", type=float, default=0.25, help="Random jitter factor for retry sleep")
    p.add_argument("--query-sleep", type=float, default=2.0, help="Sleep between queries (seconds)")
    p.add_argument("--query-jitter", type=float, default=0.3, help="Jitter for --query-sleep")
    p.add_argument("--min-query-tokens", type=int, default=2, help="Drop low-information queries")
    p.add_argument(
        "--strict-query-quality",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail when all queries are dropped by quality gate",
    )
    p.add_argument("--fail-on-empty", action="store_true", help="Exit non-zero when no recall items")
    p.add_argument("--min-unique-patents", type=int, default=0, help="Recall gate: minimum unique patent hits")
    p.add_argument(
        "--fail-on-low-recall",
        action="store_true",
        help="Exit non-zero when unique patent hits < --min-unique-patents",
    )
    p.add_argument("--out-json", default=None, help="输出 prior_art.json（建议）")
    p.add_argument("--out-md", default=None, help="输出 prior_art.md（可选）")
    p.add_argument("--failures-json", default=None, help="Write structured failures for replay/debug")
    args = p.parse_args()

    sources = ["google","lens","espacenet","cnipa"] if args.source == "all" else [s.strip().lower() for s in args.source.split(",") if s.strip()]

    queries: List[str] = []
    if args.queries:
        queries = load_queries(args.queries)
    elif args.query:
        queries = [args.query]
    else:
        raise SystemExit("Provide query or --queries")

    valid_queries, dropped_queries = sanitize_queries(queries, min_tokens=args.min_query_tokens)
    for dq in dropped_queries:
        print(f"[warn] 丢弃低质量query: {dq['query']} ({dq['reason']})", file=sys.stderr)
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
    unique_patents = count_unique_patents(all_items)

    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)
        print(f"[ok] written json: {args.out_json}", file=sys.stderr)

    if args.out_md:
        by: Dict[str, List[Dict]] = {}
        for it in all_items:
            by.setdefault(it.get("source","未知"), []).append(it)
        lines: List[str] = ["## 专利检索结果\\n"]
        for src, arr in by.items():
            lines.append(f"### {src}\\n")
            for i, it in enumerate(arr, 1):
                if "note" in it:
                    lines.append(f"- 提示：{it.get('note','')}")
                    if it.get("url"): lines.append(f"  - 链接：{it['url']}")
                    continue
                lines.append(f"{i}. **{it.get('title','无标题')}**")
                if it.get("patent_number"): lines.append(f"   - 专利号：{it['patent_number']}")
                if it.get("similarity_score") is not None: lines.append(f"   - 相似度：{it.get('similarity_score',0)}%")
                if it.get("url"): lines.append(f"   - 链接：{it['url']}")
                if it.get("abstract"):
                    a = it["abstract"].replace("\\n"," ").strip()
                    lines.append(f"   - 摘要：{a[:220]}{'...' if len(a)>220 else ''}")
            lines.append("")
        with open(args.out_md, "w", encoding="utf-8") as f:
            f.write("\\n".join(lines))
        print(f"[ok] written md: {args.out_md}", file=sys.stderr)

    failures_json = args.failures_json
    if not failures_json and args.out_json:
        failures_json = f"{args.out_json}.failures.json"
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
