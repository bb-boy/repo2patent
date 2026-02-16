---
name: repo2patent
description: |
  Input a repository URL or local path, analyze the codebase, learn local patent corpus style, and draft a CN invention patent (claims + specification + abstract) as DOCX. Use when the user asks to generate, improve, or review patent text from a software repository.
---

# 目标
基于源码事实与工作目录专利语料，生成可提交前打磨的中国发明专利草案（摘要、权利要求书、说明书、附图说明、DOCX）。

# 核心原则（强制）
0. 官方规范优先级最高：若本地语料风格与官方规范冲突，一律以官方规范为准。
1. 写作对象是“仓库对应的技术方案”，不是工具流程。
2. 先学语料再写，不允许直接套固定文案。
3. 写作阶段不依赖硬编码模板脚本拼句。
4. 脚本可用于：环境检查、仓库准备、仓库索引、法规检索、格式校验、附图生成、DOCX渲染；技术语义提取由助手完成。
5. 全文术语统一，摘要/权利要求/说明书三文一致。
6. `references/patent-draft-template.md` 仅可用于章节骨架参考，不可用于正文内容拼接。
7. 发明名称必须完整一致地出现在 `#` 标题、摘要首句主题和权利要求书主题名称中，不得截断或简写。
8. 说明书采用“技术事实+处理逻辑+效果因果”高密度写法，避免连续单句“进一步地”造成内容空泛。
9. 每轮实质改稿后必须重新执行格式校验与DOCX渲染，确保文稿与成品一致。
10. 对低信息密度句执行适度润色：当句子仅有结论、缺少条件/动作/结果任一要素时，应补足技术语义。
11. 润色必须受源码事实约束：允许扩写“处理条件、执行路径、输出结果、异常分支”，禁止引入无依据参数和新功能。
12. 不要求先匹配“技术母型”再写作：母型仅可作为可选表达参考，不能成为前置门槛。
13. 当语料与项目形态不一致时，必须退回“源码事实主线”写作，不得强行套型。

# 输入
必填：
- `repo_url_or_path`: GitHub URL 或本地仓库路径

可选：
- `branch`
- `commit`
- `legal_query`（可多次）
- `target_claims`（默认 18）
- `review_cycles`（默认 2，仅作用于 Round4 审查修订迭代次数；Round1-3固定执行）
- `invention_name`
- `applicant`
- `inventors`
- `constraints`

# 输出
- `draft/patent_draft.md`
- `analysis/context.json`
- `analysis/corpus_style_profile.md`
- `analysis/legal_rules_lookup.md`
- `analysis/llm_rounds/`（每轮中间稿）
- `analysis/validation_report.md`
- `out/patent_draft_<repo_slug>_YYYYMMDD[_HHMMSS].docx`

# 按需调用脚本（需要什么调用什么）
- 环境检查：`scripts/00_check_env.ps1` 或 `scripts/00_check_env.sh`
- 仓库准备（远程仓库才需要）：`scripts/01_clone_repo.sh`
- 仓库索引提取：`scripts/02_repo_inventory.py`
- 语料画像提取：`scripts/02b_corpus_style_profile.py`
- 法规检索：`scripts/query_official_rules.py`
- 正文写作：由助手基于语料与源码直接生成（不调用正文生成脚本）
- 质量校验：`scripts/04_validate_draft.py`
- 附图生成：`scripts/generate_figures.py`（Graphviz优先生成SVG+PNG；无dot时回退PIL）
- DOCX渲染：`scripts/05_render_docx.py`

# 语料驱动工作流（严格顺序）
1. 环境与仓库：
   - 运行 `scripts/00_check_env.*`。
   - 优先复用本地仓库；仅在远程仓库场景调用 `scripts/01_clone_repo.sh`。
2. 索引种子提取（脚本）：
   - 运行 `scripts/02_repo_inventory.py`，生成 `analysis/context.json`（仅含目录列表与文档类文件清单）。
   - 本步骤不输出最终技术结论，不替代语义分析。
3. 源码语义提取（助手执行）：
   - 由助手基于第2步索引种子分轮读取源码，提取模块职责、接口、消息主题、数据流、异常分支。
   - 每条结论必须绑定证据锚点（`file:line`）；无证据结论不得进入最终上下文。
   - 对大仓库采用分轮与优先级控制，避免无差别全量细读。
4. 法规检索：
   - 运行 `scripts/query_official_rules.py`，生成当前规则清单。
   - 先完成“官方规范核对清单”，再进入写作阶段。
5. 语料学习（必须）：
   - 运行 `scripts/02b_corpus_style_profile.py --corpus-dir <workdir> --out analysis/corpus_style_profile.md`。
   - 读取 `analysis/corpus_style_profile.md`、`references/local-patent-style-skill.md` 与 `references/corpus-style-notes-from-workdir.md`。
   - 扫描工作目录 `CN*.txt / CN*.pdf` 专利文本，提取“章节结构、权利要求句式、术语粒度、效果表达边界”四类风格信号。
   - 输出语料画像（结构模式 + 高频句式 + 禁用表达），仅在不与官方规范冲突时采用。
   - 若工作目录无可用 `CN*.txt / CN*.pdf`，退回 `references/` 内语料与官方规范继续执行，不中断流程。
6. 语料驱动自由写作（非硬编码）：
   - 由助手直接写作，不调用正文生成脚本。
   - 写作以“源码事实链路”组织，不要求预先匹配任何技术母型。
   - Round1：技术交底（问题-方案-效果-证据映射）。
   - Round2：权利要求（独立项完整 + 从属项递进）。
   - Round3：说明书（技术领域/背景/发明内容/附图/实施方式），重点展开“发明内容+具体实施方式”并写清输入、处理、输出与异常路径。
   - Round4：审查视角修订（清楚性、支持性、单一性、术语一致性）+ 低信息密度句润色（补足条件、动作、结果）。
   - Round1-3 固定执行；`review_cycles` 仅控制 Round4 的重复修订次数。
7. 校验与渲染：
   - 运行 `scripts/04_validate_draft.py`。
   - 修正校验命中的模糊风险词（如“强/弱/较好/高效”等不可验证表述）。
   - 运行 `scripts/generate_figures.py` 与 `scripts/05_render_docx.py`。
   - 附图必须通过质量门槛：分辨率、清晰度、可读字号、标号完整、非空白图。
   - 回读 `draft/patent_draft.md` 与 `out/*.docx` 结果，确认标题和章节渲染完整。

# 禁止事项
- 禁止把“解析代码生成专利”写进摘要或权利要求。
- 禁止在生成阶段使用固定段落库逐句拼接成文。
- 禁止调用任何“正文自动拼接/自动套模版”脚本生成草稿。
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

# 官方规范核对清单（写作前/写作后均需执行）
1. 保护范围以权利要求书为准，说明书用于支持与解释。
2. 权利要求应以说明书为依据，清楚、简要限定保护范围。
3. 独立权利要求完整记载必要技术特征，从属权利要求仅作进一步限定。
4. 说明书必须包含：技术领域、背景技术、发明内容、附图说明、具体实施方式。
5. 摘要仅作技术信息用途，不得用于解释保护范围，且不超过300字。
6. 术语统一、引用关系清楚，不得出现导致范围不清楚的表述。

# 参考资料
- `references/local-patent-style-skill.md`
- `references/corpus-style-notes-from-workdir.md`
- `references/patent-writing-rules.md`
- `references/cnipa-patent-writing-2017-notes.md`
- `references/patent-draft-template.md`（仅章节结构参考，不用于正文生成）
- `references/official_rules_catalog.json`
