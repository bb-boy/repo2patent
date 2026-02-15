#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import re
from pathlib import Path

DEFAULT_AMBIGUOUS = [
    "大约",
    "左右",
    "基本上",
    "接近",
    "最好",
    "尤其是",
    "必要时",
    "尽量",
    "优选",
    "高温",
    "高压",
    "强",
    "弱",
    "厚",
    "薄",
]

DEFAULT_PROMO = ["领先", "最佳", "顶级", "革命性", "颠覆性", "行业第一", "完美"]
DEFAULT_TOOL_WORDS = ["代码仓库", "静态解析", "生成专利初稿", "本技能", "本工具", "自动生成专利", "repo2patent"]
DEFAULT_NEGATIVE_SCOPE = ["不包括", "不含有", "不采用", "不呈", "无"]


def load_json_file(path: Path, default: dict):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def section_text(text: str, title: str) -> str:
    m = re.search(rf"(?ms)^##\s*{re.escape(title)}\s*$\n(.*?)(?=^##\s+[^#]|\Z)", text)
    return m.group(1).strip() if m else ""


def subsection_text(text: str, title: str) -> str:
    m = re.search(rf"(?ms)^###\s*{re.escape(title)}\s*$\n(.*?)(?=^###\s+[^#]|\Z)", text)
    return m.group(1).strip() if m else ""


def load_ambiguous(extra_path: str):
    amb = DEFAULT_AMBIGUOUS[:]
    if not extra_path:
        return amb
    p = Path(extra_path)
    if not p.exists():
        return amb
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        w = line.strip()
        if w and not w.startswith("#"):
            amb.append(w)
    return sorted(set(amb), key=len, reverse=True)


def parse_claims(claims_text: str):
    claims = []
    for m in re.finditer(r"(?ms)^\s*(\d+)\.\s*(.*?)(?=^\s*\d+\.\s|\Z)", claims_text):
        claims.append((int(m.group(1)), m.group(2).strip()))
    return claims


def claim_subject(text: str):
    m = re.search(r"^\s*一种([^，。；]+)", text)
    return m.group(1).strip() if m else ""


def context_signals(context_path: str):
    if not context_path:
        return []
    p = Path(context_path)
    if not p.exists():
        return []
    ctx = load_json_file(p, {})
    readme = (ctx.get("readme_excerpt", "") or "").lower()
    signals = []

    def add(name: str, patterns):
        ps = [x.lower() for x in patterns if x]
        if ps:
            signals.append({"name": name, "patterns": ps})

    if "kafka" in readme:
        add("Kafka消息链路", ["kafka", "消息中间件", "主题", "异步消费"])
    if "mysql" in readme:
        add("MySQL存储", ["mysql", "关系型数据库"])
    if "influx" in readme:
        add("InfluxDB时序存储", ["influxdb", "时序数据库", "时序数据"])
    if "websocket" in readme:
        add("WebSocket推送", ["websocket", "实时推送", "推送通道"])
    if "tdms" in readme:
        add("TDMS波形源", ["tdms", "波形", "时序数据"])
    if "rest api" in readme or "/api/" in readme:
        add("REST接口能力", ["rest api", "接口", "/api/"])
    if "fallback" in readme or "主备" in readme:
        add("主备回退", ["fallback", "回退", "备用数据源", "主数据源"])
    if "plc" in readme or "互锁" in readme:
        add("PLC互锁日志", ["plc", "互锁日志", "互锁"])
    if "channel" in readme or "通道" in readme:
        add("通道元数据", ["channel", "通道", "通道元数据"])

    deps = [d.lower() for d in (ctx.get("dependency_files", []) or [])]
    if any(d.endswith("pom.xml") for d in deps):
        add("Maven构建依赖", ["pom.xml", "maven"])
    if any(d.endswith("package.json") for d in deps):
        add("Node构建依赖", ["package.json", "npm"])
    if any(d.endswith("requirements.txt") for d in deps):
        add("Python依赖", ["requirements.txt", "python"])

    endpoints = re.findall(r"/api/[A-Za-z0-9_/\-{}?=&.,]*", ctx.get("readme_excerpt", "") or "")[:8]
    for ep in endpoints:
        add(f"接口:{ep}", [ep.lower(), ep.split("?")[0].lower(), "/api/"])

    # 去重（按name）
    uniq = {}
    for s in signals:
        uniq[s["name"]] = s
    return list(uniq.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ambiguous", default="")
    ap.add_argument("--profile", default="standard", choices=["lite", "standard", "full"])
    ap.add_argument("--rules-dir", default="")
    ap.add_argument("--context", default="")
    ap.add_argument("--coverage-out", default="")
    args = ap.parse_args()

    text = Path(args.inp).read_text(encoding="utf-8", errors="ignore")
    issues = []
    warns = []

    rules_dir = Path(args.rules_dir) if args.rules_dir else Path(__file__).resolve().parent.parent / "references"
    abstract_rules = load_json_file(rules_dir / "rules.abstract.yaml", {})
    claims_rules = load_json_file(rules_dir / "rules.claims.yaml", {})
    spec_rules = load_json_file(rules_dir / "rules.spec.yaml", {})

    amb = load_ambiguous(args.ambiguous)
    amb.extend(claims_rules.get("discouraged_ambiguous_words", []))
    amb = sorted(set(amb), key=len, reverse=True)
    promo_words = sorted(set(DEFAULT_PROMO + abstract_rules.get("forbidden_promo", []) + spec_rules.get("forbidden_promo", [])))
    tool_words = sorted(set(DEFAULT_TOOL_WORDS + abstract_rules.get("forbidden_tool_behavior", [])))
    neg_scope_words = sorted(set(DEFAULT_NEGATIVE_SCOPE + claims_rules.get("negative_scope_words", [])))

    # 标题检查
    title_m = re.search(r"(?m)^#\s*(.+)$", text)
    if not title_m:
        issues.append("- 未找到发明名称标题（`# <发明名称>`）")
    else:
        title = title_m.group(1).strip()
        if len(title) > 25:
            warns.append(f"- 发明名称超过25字：`{title}`")
        if any(x in title for x in ["有限公司", "股份", "™", "®"]):
            issues.append(f"- 发明名称疑似含商号/商标信息：`{title}`")

    # 章节检查
    for sec in ["摘要", "权利要求书", "说明书"]:
        if not section_text(text, sec):
            issues.append(f"- 缺少章节：`## {sec}`")

    # 内部调试段落检查（不建议进入正式申请正文）
    if re.search(r"(?m)^##\s*附：证据锚点与生成参数（内部校核）\s*$", text):
        warns.append("- 检测到内部调试段落“附：证据锚点与生成参数（内部校核）”，正式申请文本建议删除")
    if re.search(r"(?m)^###\s*实施例证据锚点\s*$", text) or re.search(r"(?m)^##\s*生成参数\s*$", text):
        warns.append("- 检测到旧版内部段落（实施例证据锚点/生成参数），正式申请文本建议删除")

    abs_text = section_text(text, "摘要")
    claims_text = section_text(text, "权利要求书")
    spec_text = section_text(text, "说明书")

    # 摘要检查
    if abs_text:
        max_chars = int(abstract_rules.get("max_chars", 300))
        if len(abs_text) > max_chars:
            issues.append(f"- 摘要超限：{len(abs_text)} 字（含标点），需≤{max_chars}字")
        if abstract_rules.get("must_start_with_any"):
            if not any(abs_text.startswith(x) for x in abstract_rules["must_start_with_any"]):
                warns.append("- 摘要建议以“本发明/本实用新型”开头")
        for w in promo_words:
            if w in abs_text:
                issues.append(f"- 摘要含宣传词：`{w}`")
        for w in tool_words:
            if w in abs_text:
                issues.append(f"- 摘要疑似描述工具行为：`{w}`（应改为目标系统技术方案）")

    # 模糊词
    for w in amb:
        if w and w in text:
            warns.append(f"- 模糊/易误解词命中：`{w}`（建议改为可验证限定）")

    # 权利要求检查
    claims = parse_claims(claims_text)
    independent_claims = 0
    if not claims:
        issues.append("- 权利要求书中未检测到编号条目（如 `1. ...`）")
    else:
        nums = [n for n, _ in claims]
        if nums[0] != 1:
            issues.append("- 权利要求编号未从1开始")
        for i in range(1, len(nums)):
            if nums[i] != nums[i - 1] + 1:
                issues.append(f"- 权利要求编号不连续：{nums[i-1]} 后出现 {nums[i]}")
                break

        first_claim = claims[0][1]
        for x in claims_rules.get("required_phrases_first_claim", ["其特征在于", "包括"]):
            if x not in first_claim:
                warns.append(f"- 权利要求1未出现关键结构词：`{x}`")

        claim_subjects = {}
        for n, body in claims:
            claim_subjects[n] = claim_subject(body)

            dep = re.search(r"根据权利要求(.+?)所述的?([^，。；]*)", body)
            if dep:
                refs = [int(r) for r in re.findall(r"\d+", dep.group(1))]
                if not refs:
                    issues.append(f"- 权利要求{n}引用格式不完整")
                for r in refs:
                    if r >= n:
                        issues.append(f"- 权利要求{n}引用了不在其前的权利要求{r}")
                if "其特征在于" not in body:
                    warns.append(f"- 权利要求{n}为从属权利要求但未出现“其特征在于”")
                if len(refs) > 1 and "或" in dep.group(1):
                    warns.append(f"- 权利要求{n}使用多重从属引用（含“或”），需核查形式要求")
                dep_subj = dep.group(2).strip()
                if dep_subj and refs:
                    base_subj = claim_subjects.get(refs[0], "")
                    if base_subj and dep_subj and (dep_subj not in base_subj and base_subj not in dep_subj):
                        warns.append(f"- 权利要求{n}主题名称与被引权利要求{refs[0]}可能不一致")
            else:
                independent_claims += 1
                if not body.startswith("一种"):
                    warns.append(f"- 权利要求{n}既非明显从属也非标准独立开头（`一种...`）")

            for bad in neg_scope_words:
                if bad in body:
                    warns.append(f"- 权利要求{n}包含否定式范围词：`{bad}`（建议改为正面限定）")
                    break

            for bad in claims_rules.get("disallow_figure_reference_words", []):
                if bad in body:
                    warns.append(f"- 权利要求{n}出现附图引用词：`{bad}`（建议删除）")
                    break

        min_claims = (
            claims_rules.get("profiles", {})
            .get(args.profile, {})
            .get("min_claims", 8)
        )
        min_independent = (
            claims_rules.get("profiles", {})
            .get(args.profile, {})
            .get("min_independent_claims", 2)
        )
        if len(claims) < int(min_claims):
            issues.append(f"- 权利要求数量不足：当前{len(claims)}项，{args.profile}档至少{min_claims}项")
        if independent_claims < int(min_independent):
            issues.append(f"- 独立权利要求数量不足：当前{independent_claims}项，至少{min_independent}项")

    # 说明书检查
    if spec_text:
        req_subs = spec_rules.get(
            "required_subsections",
            ["技术领域", "背景技术", "发明内容", "附图说明", "具体实施方式"],
        )
        for sec in req_subs:
            if re.search(rf"(?m)^###\s*{re.escape(sec)}\s*$", spec_text) is None:
                issues.append(f"- 说明书缺少小节：`### {sec}`")

        impl_text = subsection_text(spec_text, "具体实施方式")
        impl_para_count = len(re.findall(r"(?m)^\[\d{4}\]\s*", impl_text))
        min_impl = (
            spec_rules.get("profiles", {})
            .get(args.profile, {})
            .get("min_implementation_paragraphs", 10)
        )
        if impl_para_count < int(min_impl):
            issues.append(f"- 具体实施方式段落不足：当前{impl_para_count}段，{args.profile}档至少{min_impl}段")

        fig_text = subsection_text(spec_text, "附图说明")
        fig_line_count = len(re.findall(r"(?m)^\[\d{4}\]\s*", fig_text))
        fig_min = int(spec_rules.get("required_figure_lines_min", 3))
        if fig_line_count < fig_min:
            warns.append(f"- 附图说明段落较少：当前{fig_line_count}段，建议至少{fig_min}段")

        if not any(k in spec_text for k in spec_rules.get("required_effect_keywords_any", ["有益效果"])):
            warns.append("- 说明书中未检测到明显“有益效果”表述，建议补强")

    # 术语一致性
    for grp in claims_rules.get("term_consistency_groups", []):
        hit = [g for g in grp if g in text]
        if len(hit) >= 2:
            warns.append(f"- 术语可能混用：{', '.join(hit)}（建议统一术语）")

    report = ["# 校验报告", ""]
    if issues:
        report.append("## 未通过项")
        report.extend(issues)
        report.append("")
    if warns:
        report.append("## 风险项")
        report.extend(warns)
        report.append("")
    if not issues and not warns:
        report.append("## 通过")
        report.append("未发现明显格式问题（仍需人工法律审查与新颖性检索）。")
    elif not issues:
        report.append("## 通过（含风险）")
        report.append("无阻断项，但存在可改进风险项，建议修订后再提交。")

    report.append("")
    report.append("## 修正建议")
    report.append("- 优先修正未通过项，再处理风险项。")
    report.append("- 重点检查摘要是否描述目标系统技术方案而非工具流程。")
    report.append("- 人工复核：新颖性/创造性/支持性/单一性。")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.out}")

    if args.coverage_out:
        signals = context_signals(args.context)
        draft_text = text.lower()
        hit = []
        miss = []
        for s in signals:
            if any(p in draft_text for p in s["patterns"]):
                hit.append(s["name"])
            else:
                miss.append(s["name"])
        coverage = ["# 规则覆盖报告", ""]
        coverage.append(f"- profile: {args.profile}")
        coverage.append(f"- claim_count: {len(claims)}")
        coverage.append(f"- independent_claim_count: {independent_claims}")
        coverage.append(f"- issue_count: {len(issues)}")
        coverage.append(f"- warning_count: {len(warns)}")
        coverage.append("")
        coverage.append("## 上下文锚点覆盖")
        coverage.append(f"- context_signals: {len(signals)}")
        coverage.append(f"- matched_signals: {len(hit)}")
        if signals:
            cov = round(len(hit) * 100.0 / len(signals), 1)
            coverage.append(f"- coverage_ratio: {cov}%")
        if hit:
            coverage.append(f"- matched: {', '.join(hit[:20])}")
        if miss:
            coverage.append(f"- missing: {', '.join(miss[:20])}")
        if signals and not hit:
            coverage.append("- matched: 无（建议增强与仓库证据的一致性）")
        coverage.append("")
        coverage.append("## 规则文件")
        coverage.append(f"- rules.abstract.yaml: {'ok' if abstract_rules else 'missing/invalid'}")
        coverage.append(f"- rules.claims.yaml: {'ok' if claims_rules else 'missing/invalid'}")
        coverage.append(f"- rules.spec.yaml: {'ok' if spec_rules else 'missing/invalid'}")
        Path(args.coverage_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.coverage_out).write_text("\n".join(coverage), encoding="utf-8")
        print(f"Wrote {args.coverage_out}")


if __name__ == "__main__":
    main()
