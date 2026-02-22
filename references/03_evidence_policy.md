# 证据政策（Evidence Policy）

本 Skill 是“Repo 驱动交底书 + claims 对比新颖点初判”，必须可追溯。

## 证据（evidence）格式
每条证据必须包含：
- evidence_id（如 E0001）
- path（文件路径）
- line_range（起止行）
- excerpt（原文片段）
- why_selected（为何选择）

## 写作约束
- 交底书中所有关键机制/关键步骤/关键参数必须引用 evidence_id
- 没有证据的内容：只能写“待补充”并在 missing_info.md 列出
- 有益效果/性能指标必须有证据或实验数据，否则不得填写具体数值

## 新颖点约束
- 每个候选新颖点必须指向：
  - 对应关键特征（F条目）
  - 至少一个对比文件（专利号/链接）
  - claims 命中片段（如果存在）或“未命中”提示（需人工复核）
  - novelty_matrix 中的对比结果（YES/PARTIAL/NO）
