---
name: repo2patent
version: 5.0.0
description: 面向中国发明专利：从 GitHub 项目/技术方案生成可交付的专利技术交底书（Word .docx），并【必须】完成专利检索 + 权利要求抽取（claims）+ 特征对比矩阵 + 候选新颖点（差异特征组合）提炼。
---

# 专利助手（Patent Assistant）

本 Skill 解决两件事（两者都是**必须**）：

1) **交底书（发明专利）**：从 GitHub 项目抽取证据 → 形成结构化交底书 → 输出 Word（`.docx`）  
2) **检索与新颖点**：基于关键技术特征生成检索式 → 专利检索 → 抽取对比文件的**权利要求（claims）** → 形成“特征×对比文件”矩阵 → 提炼候选新颖点/风险点

---

## 重要声明（必须展示给用户）
- 本 Skill 产出**不构成法律意见**；检索与新颖点为“初步摸底”，不等同正式查新报告或授权结论。
- 新颖性判断通常需要阅读最接近对比文件全文（尤其独立权利要求），本 Skill 通过抓取 claims 提升可靠性，但仍可能因术语差异/解析失败造成误判。
- 任何性能指标/有益效果若无证据或实验数据，必须标注“待补充”，不得编造。

---

## 法规/权威依据（请在 references 查阅链接）
- 专利法第22条：新颖性/创造性/实用性及“新颖性”的法定定义（现有技术/抵触申请）。见 `references/00_authoritative_sources.md`  
- 专利法第26条：说明书清楚完整、权利要求以说明书为依据等。  
- 实施细则第20条：说明书章节结构与写作规范（技术领域/背景技术/发明内容/附图说明/具体实施方式）。

---

## 输入（至少提供一项）
- GitHub repo URL（优先）或本地 repo 路径
- 可选：ref（branch/tag/commit SHA）
- 可选：范围提示（scope）：只关注某个模块/目录（例如 `src/scheduler/`）

---

## 输出（必须）
- `disclosure.docx`：交付给代理人/内部评审的交底书（主交付）
- `disclosure.json`：结构化交底内容（必须，schema 化）
- `run_report.md`：流程执行报告（日志分流文件，不进入交底正文）
- `prior_art.json`：检索结果（结构化，召回）
- `prior_art_full.json`：对比文件“精读包”（至少包含 claims）
- `claims_manual.json`：人工回填 claims（当自动抓取失败时必须产出）
- `novelty_matrix.json`：特征×对比文件矩阵（claim 优先）+ 候选差异特征/差异组合统计
- `missing_info.md`：待补信息清单
- `.patent_assistant/evidence.json`：证据包（路径+行号+片段，可审计）

---

# 必做工作流（包含 B/C）

> 说明  
> - A：检索召回（prior_art.json）  
> - **B：抓取权利要求（prior_art_full.json）** ← 本版本新增（必须）  
> - **C：基于 claims 的特征级对比与新颖点提炼** ← 本版本加强（必须）

---

## Step 1：下载并固化版本（脚本）
```bash
python scripts/repo_fetcher.py --repo <repo_url_or_path> --ref <optional> --workdir .patent_assistant --force
```
产物：`.patent_assistant/repo/`、`.patent_assistant/repo_meta.json`

## Step 2：生成导航索引（脚本）
```bash
python scripts/repo_indexer.py --repo .patent_assistant/repo --out .patent_assistant/repo_index.json
```

## Step 3：LLM 生成阅读计划 reading_plan.json（guided-only）
LLM 只读取 `.patent_assistant/repo_index.json`，输出 `reading_plan.json`（必须符合 schema）：
- schema：`references/schemas/reading_plan.schema.json`

Planner 硬性要求：
- 必须包含 README（或同等 overview 文档）
- 若 `repo_index.json` 给出了 entrypoints，必须包含至少 1 个 entrypoint
- 必须包含至少 1 个“机制强信号”模块（scheduler/pipeline/index/cache/dedup/optimizer/retry/score 等）
- 不得超过预算：`max_files`、`max_total_chars`

## Step 4：按 reading_plan 抽取证据包（脚本）
```bash
python scripts/evidence_builder.py   --repo .patent_assistant/repo   --index .patent_assistant/repo_index.json   --plan reading_plan.json   --out .patent_assistant/evidence.json
```

## Step 5：LLM 产出 invention_profile.json（关键技术特征/关键词/变体）
LLM 只读取：
- `.patent_assistant/repo_meta.json`
- `.patent_assistant/evidence.json`
并输出结构化 `invention_profile.json`（必须符合 schema）：
- schema：`references/schemas/invention_profile.schema.json`

要求至少包含：
- 发明名称（建议：一种…的方法/系统/装置）
- 背景缺陷要点（>=1）
- **关键技术特征 F1..Fn（3–10 条，每条尽量“可检查、可对比”，并附 evidence_id）**
- 关键词（cn/en）
- 变体要点（>=3）

若关键信息缺失，必须输出 `missing_info.md`（参考 `references/04_inventor_question_bank.md`）。

---

# A. 检索召回（必须）

## Step 6：生成检索式（默认由 Codex agent 接管 + 脚本校验）
先由 Codex agent 产出 `queries.agent.json`（list 或 `{queries:[...]}`），再由脚本做质量门禁与回退合并：
```bash
python scripts/query_builder.py \
  --profile invention_profile.json \
  --agent-queries queries.agent.json \
  --query-source auto \
  --min-agent-queries 4 \
  --strict \
  --min-query-tokens 2 \
  --out queries.json
```
说明：
- `--query-source auto`：agent 优先；若 agent 查询缺失/不足，自动回退并合并 profile 查询。
- 若 `queries.agent.json` 不存在，流程可继续（回退 profile），但会给出 warning。

## Step 7：执行专利检索（脚本，必须）
至少使用 Google Patents（可追加 lens/espacenet/cnipa 等）。
```bash
python scripts/patent_search.py \
  --queries queries.json \
  -s google -c CN -n 30 -a \
  --timeout 45 --retries 4 --backoff 1.8 --jitter 0.25 \
  --query-sleep 2 --query-jitter 0.3 \
  --min-unique-patents 10 --fail-on-low-recall \
  --fail-on-empty \
  --out-json prior_art.json \
  --failures-json prior_art.failures.json
```

> Step 7 召回门禁  
> - 若 unique patents < 10，必须由 Codex agent 重写 `queries.agent.json` 并重新执行 Step 6-7。  
> - 不得在召回不足时直接进入 Step 8。

---

# B. 抓取权利要求 claims（必须）

## Step 8A：自动抓取 TopK 对比文件的权利要求（脚本，必须）
```bash
python scripts/patent_fetch_claims.py \
  --in prior_art.json \
  --topk 10 \
  --claim-sources auto \
  --timeout 40 --retries 4 --backoff 1.8 --jitter 0.25 \
  --sleep 2 --resume \
  --out prior_art_full.json \
  --cache-dir .patent_assistant/patent_cache
```

> 说明  
> - 自动路由支持 `google/espacenet/cnipa/lens`（`--claim-sources auto`）。  
> - 每条文献会记录 `claims_fetch_attempts`（来源、URL、失败原因）。  
> - 如果 `claims_status` 大量失败（403/412/503 等），必须进入 Step 8B，由 Codex agent 接管完成 claims 回填。

## Step 8B：Codex agent 接管完成 claims（自动失败时必须执行）

### 8B-1 生成人工任务模板
```bash
python scripts/manual_claims_template.py \
  --in prior_art.json \
  --topk 10 \
  --out claims_manual.json \
  --out-md claims_manual_checklist.md
```

### 8B-2 由 Codex agent 执行人工提取（用户无需手工录入）
- Codex agent 按 `claims_manual_checklist.md` 逐条打开专利链接，提取至少独立权利要求（建议 1-3 条）。  
- Codex agent 将提取结果写入 `claims_manual.json`（字段：`patent_number` + `claims_text` 或 `claims[]`）。  
- 若站点被封（403/412/503）导致 agent 无法访问，agent 必须向用户明确说明并请求可访问链接/PDF；拿到后继续由 agent 完成录入。

### 8B-3 合并人工 claims 并生成最终 prior_art_full
```bash
python scripts/patent_fetch_claims.py \
  --in prior_art.json \
  --topk 10 \
  --resume \
  --manual-claims claims_manual.json \
  --require-min-ok-ratio 0.3 \
  --out prior_art_full.json \
  --cache-dir .patent_assistant/patent_cache
```

> Step 8 完成判定  
> - `prior_art_full.json` 中 `claims_status in {ok, ok_fallback, manual_ok}` 的比例应 >= 0.3；  
> - 未达到阈值时，Codex agent 必须继续补录 claims（或向用户请求可访问资料后补录），不得直接进入 Step 9。

---

# C. 基于 claims 的对比矩阵与新颖点提炼（必须）

## Step 9：生成新颖性对比矩阵（脚本，必须）
```bash
python scripts/novelty_matrix.py \
  --profile invention_profile.json \
  --prior-art-full prior_art_full.json \
  --min-claims-ok-ratio 0.3 \
  --fail-on-low-claims \
  --out novelty_matrix.json
```

矩阵输出包含：
- 每篇对比文件、每条特征的 label：YES/PARTIAL/NO（以 claims 命中为主，abstract 为辅）
- evidence_snippets：从 claims 中截取的命中片段（便于人工复核）
- novelty_candidates：单特征差异候选（NO 占比高）
- pair_candidates：差异组合候选（“分别出现但很少同时出现”的特征对）

## Step 10：LLM 输出结构化结论 + 结构化交底内容（必须）

LLM 输入：
- `invention_profile.json`
- `prior_art.json`
- `prior_art_full.json`（含 claims）
- `novelty_matrix.json`
- `templates/disclosure_template_cn_invention.md`
- `templates/disclosure_structured_template.json`
- `references/06_novelty_playbook.md`
- `references/07_novelty_findings_output.md`
- `references/08_disclosure_output.md`

LLM **必须同时输出三份文件**：
1) `novelty_findings.json`（结构化新颖点结论，必须符合 schema）  
   - schema：`references/schemas/novelty_findings.schema.json`
2) `disclosure.json`（结构化交底内容，必须符合 schema）
   - schema：`references/schemas/disclosure.schema.json`
3) `missing_info.md`（若仍缺）

硬性要求：
- 必须选出 1–3 篇“最接近对比文件”（优先 claims_status=ok）
- 每个候选新颖点必须写成“差异特征组合”（例如：F2+F5+F7），并给出：
  - 对比文件专利号/链接
  - 矩阵标签（YES/PARTIAL/NO）与 claims 片段证据（snippets）
  - 风险提示（术语差异/claims 抓取失败/需读全文确认）
- 必须输出 risks 与 actions（补强建议与优先级）

## Step 11：构建交底 Markdown + 分流运行报告（脚本，必须）
```bash
python scripts/disclosure_builder.py --in disclosure.json --out-md disclosure.md --strict
python scripts/run_report_builder.py \
  --repo-meta .patent_assistant/repo_meta.json \
  --queries queries.json \
  --prior-art prior_art.json \
  --prior-art-full prior_art_full.json \
  --novelty-matrix novelty_matrix.json \
  --failures prior_art.failures.json \
  --out run_report.md
```

要求：
- `run_report.md` 只能包含流程日志/统计信息，不得作为交底正文输入。
- `disclosure_builder.py` 严格拦截 workflow/log 词进入 `disclosure.md`。

## Step 12：渲染 Word（脚本，必须）
```bash
python scripts/docx_renderer.py --input disclosure.md --output disclosure.docx
```

---

## 证据与可追溯（必须）
- 关键机制/关键步骤/关键参数：必须引用 `evidence_id`
- 新颖点结论必须可追溯到：F条目 + 对比文件（专利号/链接）+ claims 命中片段 + 矩阵判断

## Strict Mode Addendum (Mandatory)
- Do not fabricate or synthesize `prior_art.json` records.
- Step 7 must come from real search execution (`scripts/patent_search.py`) and pass strict source integrity checks.
- `prior_art.json` source names containing `manual/fallback/synthetic/mock/test` are invalid.
- If claims auto-fetch fails, agent may perform manual claims completion, but each manual item must include:
  - `claims_source_url` (direct accessible evidence link)
  - `claims_source_type` in `{google_patents, office_portal, pdf_copy, freepatentsonline}`
- Without the fields above, manual claims merge must fail in strict mode.
- If network/search endpoint is blocked, explicitly report blocker and request user-provided accessible links/PDF; do not create fake prior-art entries.
- Auto claim-source routing includes `fpo` (FreePatentsOnline) as a strict fallback, especially for US publications/grants when Google/Espacenet pages are blocked.

## Step 7.5 Semantic Reranking (Mandatory in strict workflow)
- After Step 7 search, run `scripts/prior_art_rerank.py` on `prior_art.json` before claims fetching.
- Use `invention_profile.json` as semantic anchor; optional `--agent-rerank` can blend agent-scored relevance.
- Recommended output: `prior_art.reranked.json` and feed it into Step 8 (`patent_fetch_claims`).
- In Step 8, keep `--prefer-relevance` enabled so TopK claims fetching follows reranked relevance.
- Optional gate: `--fail-on-low-relevance --min-topk-avg-score <X>` to prevent low-quality candidates entering claims stage.
