# Step10 输出：novelty_findings.json（结构化新颖点结论）

目的：把“新颖点提炼”从纯文本（disclosure.md）变成可复用的结构化产物，便于后续：
- 自动生成权利要求骨架（claim skeleton）
- 自动生成对比表/内部评审表
- 追溯每个新颖点的证据链（F条目 + 对比文件 + claims 片段 + 矩阵标签）

## 输入（LLM 只能使用这些）
- invention_profile.json（关键特征 F1..Fn）
- prior_art.json（召回结果）
- prior_art_full.json（TopK claims）
- novelty_matrix.json（claims-first 对比矩阵，含 evidence_snippets、pair_candidates、top_prior_art）

## 输出（LLM 必须同时输出）
1) novelty_findings.json（符合 schema：references/schemas/novelty_findings.schema.json）
2) disclosure.md（交底书草稿，必须在“检索与新颖点初判”章节引用 novelty_findings 的 NP#）
3) missing_info.md（如有）

## novelty_points（NP）写作要求
- 以“差异特征组合”表达：NP1 = [F2, F5, F7]（至少 2 个特征优先；允许 1 个但需说明为何不通用）
- 每个 NP 必须包含：
  - statement：一句话新颖点表述（面向权利要求表达）
  - differential：相对最接近对比文件的差异解释
  - supporting_prior_art：至少 1 篇对比文件，附矩阵证据（YES/PARTIAL/NO + snippets）
  - confidence：high/medium/low
  - notes：风险提示（术语差异、claims 抓取失败、需要阅读全文等）

## closest_prior_art 选择规则
- 从 novelty_matrix.json 的 top_prior_art 里选择 1–3 篇（优先 claims_status=ok）
- 如果 claims_status 不 ok，必须把风险写入 risks（claims_fetch_failed）

## risks/actions
- risks：列出影响结论可靠性的因素（术语差异、检索不足、特征过泛、需要阅读全文、缺效果数据等）
- actions：给出下一步补强（扩展同义词检索式、增加 topk、人工读独权、补实验等），并给优先级 1–5
