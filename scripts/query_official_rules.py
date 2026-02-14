#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import re
from datetime import datetime
from pathlib import Path


CORE_TERMS = [
    "发明专利",
    "权利要求书",
    "说明书",
    "摘要",
    "清楚",
    "简要",
    "必要技术特征",
    "单一性",
    "保护范围",
    "创造性",
    "新颖性",
]

CORE_RULE_IDS = {
    "PL-A22",
    "PL-A25",
    "PL-A26",
    "PL-A31",
    "PL-A64",
    "IR-A20",
    "IR-A22",
    "IR-A23",
    "IR-A24",
    "IR-A25",
    "IR-A26",
}

STOP_TERMS = {
    "以及",
    "相关",
    "要求",
    "规定",
    "国家",
    "关于",
    "这个",
    "那个",
    "系统",
    "平台",
    "模块",
    "功能",
}


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def split_terms(raw: str):
    if not raw:
        return []
    parts = re.split(r"[\s,;|/，。；、]+", raw)
    out = []
    for p in parts:
        t = p.strip().lower()
        if len(t) < 2:
            continue
        if t in STOP_TERMS:
            continue
        out.append(t)
    return out


def dedup_keep_order(items):
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def derive_terms_from_context(ctx: dict):
    terms = []
    readme = (ctx.get("readme_excerpt", "") or "").lower()
    deps = " ".join(ctx.get("dependency_files", []) or []).lower()
    tech_points = " ".join(ctx.get("technical_points", []) or []).lower()
    flags = ctx.get("feature_flags", {}) or {}

    terms.extend([x.lower() for x in CORE_TERMS])

    if "api" in readme or "接口" in readme:
        terms.extend(["方法权利要求", "步骤", "流程", "技术方案"])
    if "kafka" in readme or flags.get("kafka_pipeline"):
        terms.extend(["系统", "装置", "模块", "技术效果"])
    if "websocket" in readme or flags.get("websocket_push"):
        terms.extend(["实时", "数据传输", "技术效果"])
    if "mysql" in readme or "influx" in readme or flags.get("hybrid_storage_mysql_influx"):
        terms.extend(["数据存储", "系统结构", "具体实施方式"])
    if "fallback" in readme or flags.get("fallback_switching"):
        terms.extend(["技术问题", "技术效果", "可靠性"])
    if "ai" in readme or "algorithm" in readme or "算法" in readme:
        terms.extend(["技术问题", "技术手段", "技术效果", "创造性"])
    if "pom.xml" in deps or "build.gradle" in deps:
        terms.extend(["说明书", "实施方式"])
    if tech_points:
        terms.extend(split_terms(tech_points))

    return dedup_keep_order(terms)


def match_rule(rule: dict, terms):
    title = (rule.get("title", "") or "").lower()
    article = (rule.get("article_or_section", "") or "").lower()
    summary = (rule.get("requirement_summary", "") or "").lower()
    keywords = [str(k).lower() for k in (rule.get("keywords", []) or [])]
    checks = [str(k).lower() for k in (rule.get("writing_checks", []) or [])]

    score = 0
    matched = []

    for t in terms:
        hit = False
        if t in title:
            score += 8
            hit = True
        if any((t in k) or (k in t) for k in keywords):
            score += 7
            hit = True
        if t in summary:
            score += 5
            hit = True
        if t in article:
            score += 4
            hit = True
        if any(t in c for c in checks):
            score += 3
            hit = True
        if hit:
            matched.append(t)

    if rule.get("rule_id") in CORE_RULE_IDS:
        score += 6

    return score, dedup_keep_order(matched)


def source_map(catalog: dict):
    out = {}
    for s in catalog.get("sources", []) or []:
        sid = s.get("source_id")
        if sid:
            out[sid] = s
    return out


def build_report(catalog: dict, ranked, terms, user_terms):
    smap = source_map(catalog)
    lines = [
        "# 官方法规规则查询报告",
        "",
        f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 规则目录版本: {catalog.get('catalog_version', 'unknown')}",
        f"- 用户查询词: {', '.join(user_terms) if user_terms else '（未提供，使用上下文自动推断）'}",
        f"- 检索词: {', '.join(terms[:40])}",
        f"- 命中规则数: {len(ranked)}",
        "",
        "## 说明",
        "- 本报告用于 `repo2patent` 写作阶段的合规校核参考，不替代律师或专利代理师法律意见。",
        "- 法规条文以国家官方发布原文及其最新修订为准。",
        "",
        "## 高相关规则",
    ]

    if not ranked:
        lines.append("- 未检索到高相关规则，请补充 `--query` 或检查 `analysis/context.json`。")
    else:
        for i, item in enumerate(ranked, 1):
            rule = item["rule"]
            src = smap.get(rule.get("source_id"), {})
            lines.append(f"### {i}. {rule.get('rule_id', 'UNKNOWN')} | {rule.get('title', '')}")
            lines.append(f"- 相关度: {item['score']}")
            lines.append(f"- 法律层级: {rule.get('legal_level', '未知')}")
            lines.append(f"- 条款位置: {rule.get('article_or_section', '未标注')}")
            lines.append(f"- 规则摘要: {rule.get('requirement_summary', '')}")
            lines.append(
                f"- 官方来源: {src.get('source_title', rule.get('source_id', '未知来源'))}"
            )
            lines.append(f"- 官方链接: {src.get('source_url', '')}")
            if item["matched_terms"]:
                lines.append(f"- 命中词: {', '.join(item['matched_terms'][:12])}")
            checks = rule.get("writing_checks", []) or []
            if checks:
                lines.append(f"- 写作检查: {checks[0]}")
            lines.append("")

    lines.extend(
        [
            "## 官方来源清单",
        ]
    )
    for s in catalog.get("sources", []) or []:
        lines.append(
            f"- {s.get('source_title', '')}（生效：{s.get('effective_date', '未知')}）：{s.get('source_url', '')}"
        )

    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", required=True, help="official_rules_catalog.json path")
    ap.add_argument("--context", default="", help="analysis/context.json path")
    ap.add_argument("--query", action="append", default=[], help="optional search keyword")
    ap.add_argument("--out", required=True, help="output markdown path")
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    rules_path = Path(args.rules)
    out_path = Path(args.out)
    catalog = load_json(rules_path, {})
    if not catalog or not catalog.get("rules"):
        raise SystemExit(f"Invalid or empty rules catalog: {rules_path}")

    ctx = {}
    if args.context:
        ctx = load_json(Path(args.context), {})

    user_terms = []
    for q in args.query:
        user_terms.extend(split_terms(q))

    derived_terms = derive_terms_from_context(ctx)
    terms = dedup_keep_order(user_terms + derived_terms)
    if not terms:
        terms = [x.lower() for x in CORE_TERMS]

    ranked = []
    for r in catalog.get("rules", []) or []:
        score, matched_terms = match_rule(r, terms)
        if score > 0:
            ranked.append(
                {
                    "rule": r,
                    "score": score,
                    "matched_terms": matched_terms,
                }
            )

    ranked.sort(key=lambda x: (-x["score"], x["rule"].get("rule_id", "")))
    ranked = ranked[: max(1, args.top)]

    report = build_report(catalog, ranked, terms, user_terms)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
