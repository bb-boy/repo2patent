# repo2patent

`repo2patent` 是一个面向 Codex 的技能（skill），用于把软件仓库转成中国发明专利草案，并输出 `DOCX` 成品。

该技能采用“源码事实主线 + 语料风格迁移”的方式：
- 技术事实来自源码阅读与证据锚点（`file:line`）。
- 写作风格来自工作目录专利语料（支持 `CN*.txt / CN*.pdf`）。
- 如语料风格与官方规范冲突，始终以官方规范为准。

## 1. 核心原则

1. 专利写作对象是“仓库对应的技术方案”，不是“工具流程”。
2. `02_repo_inventory.py` 只做索引种子，不输出最终技术结论。
3. 源码语义提取由助手分轮执行，并绑定 `file:line` 证据。
4. 语料学习只影响表达风格，不替代技术事实。
5. 不要求先匹配“技术母型”；母型不是前置门槛。
6. Round1-3 固定执行，`review_cycles` 仅控制 Round4 重复修订次数。
7. 每次实质改稿后必须重新校验与渲染。

## 2. 输入与输出

输入（必填）：
- `repo_url_or_path`

输入（可选）：
- `branch`
- `commit`
- `legal_query`（可多次）
- `target_claims`（默认 18）
- `review_cycles`（默认 2，仅作用于 Round4）
- `invention_name`
- `applicant`
- `inventors`
- `constraints`

输出：
- `analysis/context.json`
- `analysis/corpus_style_profile.md`
- `analysis/legal_rules_lookup.md`
- `analysis/llm_rounds/`
- `analysis/validation_report.md`
- `draft/patent_draft.md`
- `out/patent_draft_<repo_slug>_YYYYMMDD[_HHMMSS].docx`

## 3. 工作流（严格顺序）

1. 环境与仓库准备  
运行 `scripts/00_check_env.ps1` 或 `scripts/00_check_env.sh`；远程仓库时调用 `scripts/01_clone_repo.sh`。

2. 索引种子提取（脚本）  
运行 `scripts/02_repo_inventory.py` 生成 `analysis/context.json`。  
该文件仅包含目录与文档类文件清单，用于导航。

3. 源码语义提取（助手）  
助手基于第2步结果分轮读取源码，提取模块职责、接口、数据流、异常分支。  
每条结论都要绑定 `file:line` 证据。

4. 法规检索（脚本）  
运行 `scripts/query_official_rules.py` 生成 `analysis/legal_rules_lookup.md`。  
先完成官方规范核对，再进入写作。

5. 语料学习（脚本 + 参考）  
运行：
```bash
python scripts/02b_corpus_style_profile.py --corpus-dir <workdir> --out analysis/corpus_style_profile.md
```
语料来源支持 `CN*.txt / CN*.pdf`。  
随后读取：
- `analysis/corpus_style_profile.md`
- `references/local-patent-style-skill.md`
- `references/corpus-style-notes-from-workdir.md`

6. 四轮写作（助手）  
- Round1：技术交底（问题-方案-效果-证据映射）  
- Round2：权利要求（独立项完整 + 从属项递进）  
- Round3：说明书（五段结构 + 输入/处理/输出/异常）  
- Round4：审查修订（清楚性、支持性、单一性、术语一致性、低信息密度润色）

7. 校验与渲染（脚本）  
运行 `scripts/04_validate_draft.py`，然后 `scripts/generate_figures.py`，最后 `scripts/05_render_docx.py`。

## 4. 关键脚本职责

- `scripts/02_repo_inventory.py`  
只输出“目录 + 文档类文件”，不做最终语义判断。

- `scripts/02b_corpus_style_profile.py`  
扫描工作目录 `CN*.txt / CN*.pdf`，生成语料风格画像。  
若 PDF 不可提取文本，会在报告中标记可读性。

- `scripts/query_official_rules.py`  
从规则库生成法规检索结果，约束写作边界。

- `scripts/04_validate_draft.py`  
检查结构、术语一致性、模糊词、权项数量、实施方式密度等。

- `scripts/generate_figures.py`  
优先 Graphviz 生成附图，失败时回退。

- `scripts/05_render_docx.py`  
将 Markdown 草稿渲染为 DOCX，嵌入附图并保持标题完整性。

## 5. 快速执行示例

在 `repo2patent/` 目录下：

```bash
# 1) 环境检查
powershell -ExecutionPolicy Bypass -File scripts/00_check_env.ps1

# 2) 索引
python scripts/02_repo_inventory.py --repo work/repo --out analysis/context.json

# 3) 法规检索
python scripts/query_official_rules.py --rules references/official_rules_catalog.json --context analysis/context.json --out analysis/legal_rules_lookup.md

# 4) 语料画像（支持 txt/pdf）
python scripts/02b_corpus_style_profile.py --corpus-dir .. --out analysis/corpus_style_profile.md

# 5) 产出草稿后校验+渲染
python scripts/04_validate_draft.py --in draft/patent_draft.md --out analysis/validation_report.md --ambiguous assets/STOPWORDS_ambiguous.txt --profile full --rules-dir references --context analysis/context.json --coverage-out analysis/coverage_report.md
python scripts/generate_figures.py --context analysis/context.json --out-dir draft/figures
python scripts/05_render_docx.py --in draft/patent_draft.md --out out/patent_draft_<repo_slug>_YYYYMMDD_HHMMSS.docx --figures-dir draft/figures
```

## 6. 目录说明

```text
repo2patent/
├── SKILL.md
├── README.md
├── scripts/
├── references/
├── assets/
├── analysis/
├── draft/
├── out/
└── work/
```

## 7. 常见问题

Q1：工作目录只有 PDF 语料可以吗？  
A：可以。`02b_corpus_style_profile.py` 已支持 `CN*.pdf`。文本不可提取时会在输出中标记 `readable=no`。

Q2：02 脚本会不会直接决定技术结论？  
A：不会。`02_repo_inventory.py` 只做索引导航，技术结论来自后续源码语义提取。

Q3：大仓库会不会读太多？  
A：不会强制全量细读。助手按优先级分轮读取，并以证据锚点收敛。

Q4：语料不足怎么办？  
A：退回 `references/` 与官方规范继续执行，不中断流程。

## 8. 禁止事项（摘要）

- 禁止把“解析代码生成专利”写入摘要或权利要求。
- 禁止用固定段落库直接拼接正文。
- 禁止调用任何“正文自动拼接/自动套模版”脚本生成草稿。
- 禁止用宣传性词汇替代技术效果论证。

## 9. 参考文件

- `SKILL.md`
- `references/local-patent-style-skill.md`
- `references/corpus-style-notes-from-workdir.md`
- `references/patent-writing-rules.md`
- `references/cnipa-patent-writing-2017-notes.md`
- `references/official_rules_catalog.json`
