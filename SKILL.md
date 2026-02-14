---
name: repo2patent
description: |
  Input a repository URL or local path, analyze the codebase, learn local patent corpus style, and draft a CN invention patent (claims + specification + abstract) as DOCX. Use when the user asks to generate, improve, or review patent text from a software repository.
---

# 目标
基于源码事实与本地专利语料，生成可提交前打磨的中国发明专利草案（摘要、权利要求书、说明书、附图说明、DOCX）。

# 核心原则（强制）
0. 官方规范优先级最高：若本地语料风格与官方规范冲突，一律以官方规范为准。
1. 写作对象是“仓库对应的技术方案”，不是工具流程。
2. 先学语料再写，不允许直接套固定文案。
3. 写作阶段不依赖硬编码模板脚本拼句。
4. 脚本只用于：事实提取、法规检索、格式校验、DOCX渲染。
5. 全文术语统一，摘要/权利要求/说明书三文一致。
6. `references/patent-draft-template.md` 仅可用于章节骨架参考，不可用于正文内容拼接。
7. 发明名称必须完整一致地出现在 `#` 标题、摘要首句主题和权利要求书主题名称中，不得截断或简写。
8. 说明书采用“技术事实+处理逻辑+效果因果”高密度写法，避免连续单句“进一步地”造成内容空泛。
9. 每轮实质改稿后必须重新执行格式校验与DOCX渲染，确保文稿与成品一致。
10. 对低信息密度句执行适度润色：当句子仅有结论、缺少条件/动作/结果任一要素时，应补足技术语义。
11. 润色必须受源码事实约束：允许扩写“处理条件、执行路径、输出结果、异常分支”，禁止引入无依据参数和新功能。

# 输入
必填：
- `repo_url_or_path`: GitHub URL 或本地仓库路径

可选：
- `branch`
- `commit`
- `legal_query`（可多次）
- `target_claims`（默认 18）
- `review_cycles`（默认 2）
- `invention_name`
- `applicant`
- `inventors`
- `constraints`

# 输出
- `draft/patent_draft.md`
- `analysis/context.json`
- `analysis/legal_rules_lookup.md`
- `analysis/llm_rounds/`（每轮中间稿）
- `analysis/validation_report.md`
- `out/patent_draft_<repo_slug>_YYYYMMDD[_HHMMSS].docx`

# 按需调用脚本（需要什么调用什么）
- 环境检查：`scripts/00_check_env.ps1` 或 `scripts/00_check_env.sh`
- 仓库准备（远程仓库才需要）：`scripts/01_clone_repo.sh`
- 代码事实提取：`scripts/02_repo_inventory.py`
- 法规检索：`scripts/query_official_rules.py`
- 正文写作：由助手基于语料与源码直接生成（不调用正文生成脚本）
- 质量校验：`scripts/04_validate_draft.py`
- 附图生成：`scripts/generate_figures.py`（Graphviz优先生成SVG+PNG；无dot时回退PIL）
- DOCX渲染：`scripts/05_render_docx.py`

# 语料驱动工作流（严格顺序）
1. 环境与仓库：
   - 运行 `scripts/00_check_env.*`。
   - 优先复用本地仓库；仅在远程仓库场景调用 `scripts/01_clone_repo.sh`。
2. 事实提取：
   - 运行 `scripts/02_repo_inventory.py`，抽取模块、方法、接口、消息主题、数据流。
3. 法规检索：
   - 运行 `scripts/query_official_rules.py`，生成当前规则清单。
   - 先完成“官方规范核对清单”，再进入写作阶段。
4. 语料学习（必须）：
   - 读取 `references/local-patent-style-skill.md`。
   - 扫描目录内 `CN*.txt` 专利文本，归纳结构和句式，仅在不与官方规范冲突时采用。
5. 语料驱动自由写作（非硬编码）：
   - 由助手直接写作，不调用正文生成脚本。
   - Round1：技术交底（问题-方案-效果-证据映射）。
   - Round2：权利要求（独立项完整 + 从属项递进）。
   - Round3：说明书（技术领域/背景/发明内容/附图/实施方式），重点展开“发明内容+具体实施方式”并写清输入、处理、输出与异常路径。
   - Round4：审查视角修订（清楚性、支持性、单一性、术语一致性）+ 低信息密度句润色（补足条件、动作、结果）。
6. 校验与渲染：
   - 运行 `scripts/04_validate_draft.py`。
   - 修正校验命中的模糊风险词（如“强/弱/较好/高效”等不可验证表述）。
   - 运行 `scripts/generate_figures.py` 与 `scripts/05_render_docx.py`。
   - 附图必须通过质量门槛：分辨率、清晰度、可读字号、标号完整、非空白图。
   - 回读 `draft/patent_draft.md` 与 `output/*.docx` 结果，确认标题和章节渲染完整。

# 禁止事项
- 禁止把“解析代码生成专利”写进摘要或权利要求。
- 禁止在生成阶段使用固定段落库逐句拼接成文。
- 禁止调用 `scripts/03_generate_draft.py` 生成正文草稿。
- 禁止调用 `scripts/03_generate_draft_llm.py` 生成正文草稿。
- 禁止出现仅措辞变化但技术特征相同的重复权利要求。
- 禁止用宣传性用语替代技术效果论证。

# 质量门槛
- 摘要：对象 + 场景 + 关键步骤 + 技术效果，<=300字。
- 权利要求：独立项完整、从属项递进、引用关系清晰。
- 说明书：五段结构完整；“发明内容”和“具体实施方式”不得写成大量单句空段，关键段落需包含技术条件、处理逻辑与结果关系。
- 文风密度：减少机械重复“进一步地”，允许自然扩写，但不得超出源码事实或引入无依据参数。
- 句子密度：对“只有结论、缺少技术动作”的短句必须润色；润色后每个关键句优先具备“条件+处理+结果”三要素中的至少两项。
- 重点详实：技术问题、发明内容、具体实施方式、技术效果四部分必须详写，不得以口号式短句替代技术叙述。
- 一致性：术语和技术特征在三文中可逐项对应。
- 渲染一致性：Markdown与DOCX标题一致且完整（例如“及系统”不得丢失）。
- 附图质量：优先使用自动布局（Graphviz）；图中不得出现明显重叠、交叉线过多、标号缺失或文本超框。
- 附图版式：DOCX中每张附图应单独占一页并居中排版，图题置于图下方，保证页面视觉平衡。
- 附图标题规则：图内不得绘制“图1/图2/图3+标题”文字，图题仅允许出现在图下方图注位置。
- 附图尺寸规则：绘图与排版前先计算页面可用区域，单图尺寸不得超出一页可用空间，并预留图注空间。
- 分层图规则：分层图不绘制外层总框；仅保留层级标识与模块框。若存在分层参考宽度，层内模块区宽度应保持一致。
- 流程图方向规则：流程图主流程必须由上往下（Top-to-Bottom）绘制。
- 流程图自适应规则：当流程较长或文字较长时，自动缩小节点字号、内边距和节点间距，保证单页可读且不拥挤。

# 官方规范核对清单（写作前/写作后均需执行）
1. 保护范围以权利要求书为准，说明书用于支持与解释。
2. 权利要求应以说明书为依据，清楚、简要限定保护范围。
3. 独立权利要求完整记载必要技术特征，从属权利要求仅作进一步限定。
4. 说明书必须包含：技术领域、背景技术、发明内容、附图说明、具体实施方式。
5. 摘要仅作技术信息用途，不得用于解释保护范围，且不超过300字。
6. 术语统一、引用关系清楚，不得出现导致范围不清楚的表述。

# 参考资料
- `references/local-patent-style-skill.md`
- `references/patent-writing-rules.md`
- `references/cnipa-patent-writing-2017-notes.md`
- `references/patent-draft-template.md`（仅章节结构参考，不用于正文生成）
- `references/official_rules_catalog.json`
