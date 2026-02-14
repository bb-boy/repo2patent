#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import re
from pathlib import Path

DEFAULT_AMBIGUOUS = [
    "大约", "左右", "基本上", "接近", "最好", "尤其是", "必要时", "尽量", "优选",
    "高温", "高压", "强", "弱", "厚", "薄",
]

PROMO_WORDS = ["领先", "最佳", "顶级", "革命性", "颠覆性", "显著领先", "行业第一", "完美"]
SKILL_BEHAVIOR_WORDS = ["代码仓库", "静态解析", "生成专利初稿", "本技能", "本工具", "自动生成专利"]
NEGATIVE_SCOPE_WORDS = ["不包括", "不含有", "不采用", "不呈", "无"]


def section_text(text: str, title: str) -> str:
    m = re.search(
        rf"(?ms)^##\s*{re.escape(title)}\s*$\n(.*?)(?=^##\s+[^#]|\Z)",
        text,
    )
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
    for m in re.finditer(r"(?m)^\s*(\d+)\.\s*(.+)$", claims_text):
        claims.append((int(m.group(1)), m.group(2).strip()))
    return claims


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ambiguous", default="")
    args = ap.parse_args()

    text = Path(args.inp).read_text(encoding="utf-8", errors="ignore")
    issues = []
    warns = []
    amb = load_ambiguous(args.ambiguous)

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

    # 必要章节
    for sec in ["摘要", "权利要求书", "说明书"]:
        if not section_text(text, sec):
            issues.append(f"- 缺少章节：`## {sec}`")

    # 摘要检查
    abs_text = section_text(text, "摘要")
    if abs_text:
        L = len(abs_text)
        if L > 300:
            issues.append(f"- 摘要超限：{L} 字（含标点），需≤300字")
        for w in PROMO_WORDS:
            if w in abs_text:
                issues.append(f"- 摘要含商业宣传词：`{w}`")
        for w in SKILL_BEHAVIOR_WORDS:
            if w in abs_text:
                issues.append(f"- 摘要疑似描述了技能/工具行为：`{w}`（应改为目标系统技术方案）")
        if "本发明" not in abs_text and "本实用新型" not in abs_text:
            warns.append("- 摘要未出现“本发明/本实用新型”表述（可酌情调整）")

    # 模糊词
    for w in amb:
        if w and w in text:
            warns.append(f"- 模糊/易误解词命中：`{w}`（建议删除或改为可验证限定）")

    claims_text = section_text(text, "权利要求书")
    claims = parse_claims(claims_text)
    if not claims:
        issues.append("- 权利要求书中未检测到编号条目（如 `1. ...`）")
    else:
        # 编号连续性
        nums = [n for n, _ in claims]
        if nums[0] != 1:
            issues.append("- 权利要求编号未从1开始")
        for i in range(1, len(nums)):
            if nums[i] != nums[i - 1] + 1:
                issues.append(f"- 权利要求编号不连续：{nums[i-1]} 后出现 {nums[i]}")
                break

        # 独立权利要求基本结构
        first_claim = claims[0][1]
        if "其特征在于" not in first_claim:
            warns.append("- 权利要求1未出现“其特征在于”")
        if "包括" not in first_claim:
            warns.append("- 权利要求1未出现“包括”结构词，建议检查完整性")

        # 从属关系与限定性
        for n, body in claims[1:]:
            dep = re.search(r"根据权利要求(.+?)所述", body)
            if dep:
                refs = re.findall(r"\d+", dep.group(1))
                if not refs:
                    issues.append(f"- 权利要求{n}引用格式不完整")
                else:
                    for r in refs:
                        if int(r) >= n:
                            issues.append(f"- 权利要求{n}引用了不在其前的权利要求{r}")
                if "其特征在于" not in body:
                    warns.append(f"- 权利要求{n}为从属权利要求但未出现“其特征在于”")
            else:
                # 非从属通常应为并列独立权利要求
                if not body.startswith("一种"):
                    warns.append(f"- 权利要求{n}既非明显从属也非标准独立开头（`一种...`）")

            for bad in NEGATIVE_SCOPE_WORDS:
                if bad in body:
                    warns.append(f"- 权利要求{n}包含否定式范围词：`{bad}`（建议改为正面限定）")
                    break

    # 说明书支持性（粗检查）
    spec_text = section_text(text, "说明书")
    if spec_text:
        for sec in ["技术领域", "背景技术", "发明内容", "具体实施方式"]:
            if re.search(rf"###\s*{re.escape(sec)}", spec_text) is None:
                warns.append(f"- 说明书中建议包含 `### {sec}` 小节")

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
    report.append("- 重点检查摘要是否描述目标技术方案而非工具流程。")
    report.append("- 人工复核：新颖性/创造性/支持性/单一性。")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
