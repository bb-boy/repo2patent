# repo2patent

> 🧠 从 GitHub 项目到专利技术交底书的可审计流水线  
> 🔍 强制包含检索与 claims（权利要求）比对  
> 📄 最终输出 Word（`.docx`，默认宋体）

## ✨ 这个 Skill 做什么

`repo2patent` 面向中国发明专利场景，核心目标是把“代码仓库里的技术方案”转成“可交付的专利交底材料”。

它不是单纯写文案，而是一个分阶段流水线：

- 📦 读取仓库并建立索引（知道该看哪些文件）
- 🧾 按阅读计划抽取证据（`evidence.json`）
- 🧭 由 agent 优先生成检索词并做门禁
- 🔎 执行专利检索并产出 `prior_art.json`
- 🧲 抓取 TopK 对比文献 claims（自动 + 接管回填）
- 📊 生成 claims-first 对比矩阵 `novelty_matrix.json`
- 📝 生成交底 Markdown 并渲染 `disclosure.docx`

---

## 🗂️ 仓库结构

```text
repo2patent/
├─ scripts/
│  ├─ repo_fetcher.py
│  ├─ repo_indexer.py
│  ├─ evidence_builder.py
│  ├─ query_builder.py
│  ├─ patent_search.py
│  ├─ patent_fetch_claims.py
│  ├─ manual_claims_template.py
│  ├─ novelty_matrix.py
│  └─ docx_renderer.py
├─ references/
│  ├─ 00_authoritative_sources.md
│  ├─ ...
│  └─ schemas/
├─ templates/
│  └─ disclosure_template_cn_invention.md
├─ SKILL.md
└─ README.md
```

---

## ⚙️ 环境依赖

- Python 3.8+
- Git
- 可选：`python-docx`（生成 Word 必需）

```bash
pip install python-docx
```

---

## 🚀 5 分钟快速开始（端到端）

> 下列命令在仓库根目录执行。

```bash
python -m scripts.repo_fetcher --repo <repo_url_or_local_path> --ref main --workdir .patent_assistant --force
python -m scripts.repo_indexer --repo .patent_assistant/repo --out .patent_assistant/repo_index.json
python -m scripts.evidence_builder --repo .patent_assistant/repo --index .patent_assistant/repo_index.json --plan reading_plan.json --out .patent_assistant/evidence.json
python -m scripts.query_builder --profile invention_profile.json --agent-queries queries.agent.json --query-source auto --strict --out queries.json
python -m scripts.patent_search --queries queries.json -s all -c CN -n 30 -a --strict-source-integrity --fail-on-empty --min-unique-patents 10 --fail-on-low-recall --out-json prior_art.json --failures-json prior_art.failures.json
python -m scripts.patent_fetch_claims --in prior_art.json --topk 10 --claim-sources auto --strict-prior-art --strict-manual-evidence --require-min-ok-ratio 0.3 --out prior_art_full.json --cache-dir .patent_assistant/patent_cache
python -m scripts.novelty_matrix --profile invention_profile.json --prior-art-full prior_art_full.json --min-claims-ok-ratio 0.3 --fail-on-low-claims --out novelty_matrix.json
# LLM 生成 disclosure.md 后：
python -m scripts.docx_renderer --input disclosure.md --output disclosure.docx --font-name 宋体
```

---

## 🧭 完整工作流（每一步含输入/输出/示例/门禁）

## 1. 📥 拉取仓库并固化版本

目标：
- 获取可重复分析的代码快照，记录 commit。

输入：
- `--repo`（Git URL 或本地路径）
- `--ref`（可选：分支/标签/提交）

命令：

```bash
python -m scripts.repo_fetcher --repo https://github.com/example/project.git --ref main --workdir .patent_assistant --force
```

输出：
- `.patent_assistant/repo/`
- `.patent_assistant/repo_meta.json`

终端示例：

```text
[ok] repo at: .patent_assistant/repo
[ok] commit: 7d8a3d9c6e...
```

门禁：
- 目标目录已存在且未指定 `--force` 会失败。
- 本地路径不存在会失败。

---

## 2. 🗺️ 建立仓库索引

目标：
- 生成结构化 `repo_index.json`，指导后续阅读计划。

命令：

```bash
python -m scripts.repo_indexer --repo .patent_assistant/repo --out .patent_assistant/repo_index.json
```

输出：
- `.patent_assistant/repo_index.json`

终端示例：

```text
[ok] indexed files: 326
[ok] entrypoints: ['src/main.py']
[ok] out: .patent_assistant/repo_index.json
```

门禁：
- 无硬门禁阈值；建议控制 `--max_files` 以避免过大仓库拖慢。

---

## 3. 📚 生成阅读计划（LLM 步骤）

目标：
- 让模型先决定“读哪些文件、读到什么粒度”。

输入：
- `repo_index.json`
- 约束：`references/schemas/reading_plan.schema.json`

输出：
- `reading_plan.json`

最小示例：

```json
{
  "plan_version": "1.0",
  "goals": ["提取关键技术机制", "定位可专利化特征"],
  "limits": {"max_files": 20, "max_total_chars": 150000},
  "selections": [
    {
      "path": "src/main.py",
      "read_type": "head",
      "selectors": {"lines": 220},
      "priority": 5,
      "reason": "入口流程",
      "expected_extract": ["关键流程", "关键参数"]
    }
  ]
}
```

---

## 4. 🧩 抽取证据包

目标：
- 把代码证据落盘为 `evidence.json`，供后续 profile 与新颖点判断引用。

命令：

```bash
python -m scripts.evidence_builder --repo .patent_assistant/repo --index .patent_assistant/repo_index.json --plan reading_plan.json --out .patent_assistant/evidence.json
```

输出：
- `.patent_assistant/evidence.json`

终端示例：

```text
[ok] evidence items: 19
[ok] total_chars: 84217
[ok] out: .patent_assistant/evidence.json
```

---

## 5. 🧠 生成发明画像（LLM 步骤）

目标：
- 把证据提炼为可检索、可比对的结构化发明描述。

输入：
- `repo_meta.json` + `evidence.json`
- 约束：`references/schemas/invention_profile.schema.json`

输出：
- `invention_profile.json`

最小示例：

```json
{
  "title": "一种面向边缘场景的任务编排方法",
  "technical_field": {"domain": "分布式系统", "sub_domain": "任务调度"},
  "core_problem": "多目标约束下调度不稳定",
  "key_features": [
    {"id": "F1", "text": "按任务画像分层调度", "evidence_ids": ["E0001"]},
    {"id": "F2", "text": "反馈闭环动态调整", "evidence_ids": ["E0003"]},
    {"id": "F3", "text": "差异化重试策略", "evidence_ids": ["E0007"]}
  ],
  "keywords": {"cn": ["调度", "反馈"], "en": ["scheduler", "feedback loop"]}
}
```

---

## 6. 🧪 生成检索词（agent-first）

目标：
- 由 agent 优先给出检索词，脚本执行质量门禁与回退合并。

命令：

```bash
python -m scripts.query_builder --profile invention_profile.json --agent-queries queries.agent.json --query-source auto --min-agent-queries 4 --strict --out queries.json
```

输出：
- `queries.json`

终端示例：

```text
[ok] queries: 8
[ok] out: queries.json
```

门禁：
- `--strict` 默认开启：最终无有效 query 直接失败。
- `--min-query-tokens` 默认 `2`：过滤低信息检索式。
- `--query-source auto`：agent 不足时自动合并 profile，不跳步。

---

## 7. 🔍 执行专利检索（Step 7）

目标：
- 得到可追溯 `prior_art.json` 与失败日志。

命令：

```bash
python -m scripts.patent_search --queries queries.json -s all -c CN -n 30 -a --strict-source-integrity --fail-on-empty --min-unique-patents 10 --fail-on-low-recall --out-json prior_art.json --failures-json prior_art.failures.json
```

输出：
- `prior_art.json`
- `prior_art.failures.json`

终端示例（真实风格）：

```text
[ok] total items: 60
[ok] unique patents: 36
[ok] valid queries: 8, dropped queries: 0
[ok] source failures: 3
```

门禁（关键）：
- `--strict-source-integrity`（默认开）：禁止 synthetic/manual/fallback 等来源。
- `--fail-on-empty`：0 条结果返回 exit code `2`。
- `--fail-on-low-recall + --min-unique-patents 10`：唯一专利数不足返回 exit code `3`。

---

## 8A. 🧲 自动抓取 claims（Step 8A）

目标：
- 对 TopK 对比文献抓取 claims，输出 `prior_art_full.json`。

命令：

```bash
python -m scripts.patent_fetch_claims --in prior_art.json --topk 10 --claim-sources auto --strict-prior-art --strict-manual-evidence --require-min-ok-ratio 0.3 --out prior_art_full.json --cache-dir .patent_assistant/patent_cache
```

输出：
- `prior_art_full.json`

终端示例：

```text
[ok] fetched claims: 7/10 (ratio=0.700)
[ok] status counts: {'ok': 7, 'claims_section_not_found': 3}
[ok] out: prior_art_full.json
```

门禁（关键）：
- `--strict-prior-art`（默认开）：输入必须通过来源与追溯校验。
- `--require-min-ok-ratio 0.3`：`ok/ok_fallback/manual_ok` 比例低于阈值返回 exit code `2`。

自动源路由（当前实现）：
- US/JP/KR/DE/FR/GB：`fpo -> google -> espacenet -> lens -> cnipa`
- EP/WO：`espacenet -> google -> lens -> cnipa -> fpo`
- CN：`cnipa -> google -> espacenet -> lens -> fpo`

---

## 8B. 🛠️ 自动失败后的 agent 接管（必须可追溯）

目标：
- 在 403/412/503 等拦截下，继续完成 claims 回填而不伪造数据。

步骤 1：生成回填模板

```bash
python -m scripts.manual_claims_template --in prior_art.json --topk 10 --out claims_manual.json --out-md claims_manual_checklist.md --strict-source-integrity
```

步骤 2：agent 按 checklist 补录 claims（不是让用户手工逐条编辑）

步骤 3：合并回 `prior_art_full.json`

```bash
python -m scripts.patent_fetch_claims --in prior_art.json --topk 10 --resume --manual-claims claims_manual.json --strict-manual-evidence --require-min-ok-ratio 0.3 --out prior_art_full.json
```

严格证据字段（必须）：
- `claims_source_url`：可访问证据链接（http/https）
- `claims_source_type`：`google_patents | office_portal | pdf_copy | freepatentsonline`

---

## 9. 📊 生成 claims-first 对比矩阵（Step 9）

目标：
- 产出特征×文献对比矩阵，并做 claims 质量二次门禁。

命令：

```bash
python -m scripts.novelty_matrix --profile invention_profile.json --prior-art-full prior_art_full.json --min-claims-ok-ratio 0.3 --fail-on-low-claims --out novelty_matrix.json
```

输出：
- `novelty_matrix.json`

终端示例：

```text
[ok] features: 10, documents: 10
[ok] claims gate: 7/10=0.700 (min=0.300, pass=True)
[ok] out: novelty_matrix.json
```

门禁：
- `--fail-on-low-claims` 开启时，低于 `--min-claims-ok-ratio` 直接失败。

---

## 10. 📝 交底内容生成（LLM 步骤）

目标：
- 结合 `invention_profile + prior_art + prior_art_full + novelty_matrix` 输出交底正文 Markdown。

建议输入：
- `templates/disclosure_template_cn_invention.md`
- `references/06_novelty_playbook.md`
- `references/07_novelty_findings_output.md`

输出：
- `disclosure.md`

---

## 11. 📄 渲染 Word（宋体）

命令：

```bash
python -m scripts.docx_renderer --input disclosure.md --output disclosure.docx --font-name 宋体
```

输出：
- `disclosure.docx`

终端示例：

```text
[ok] written: disclosure.docx
```

说明：
- 默认字体就是 `宋体`，`--font-name` 可显式指定。

---

## 📦 关键产物总览

- `.patent_assistant/repo_meta.json`
- `.patent_assistant/repo_index.json`
- `.patent_assistant/evidence.json`
- `invention_profile.json`
- `queries.json`
- `prior_art.json`
- `prior_art.failures.json`
- `prior_art_full.json`
- `claims_manual.json`（仅当自动抓取不足时）
- `novelty_matrix.json`
- `disclosure.md`
- `disclosure.docx`

---

## 🧰 脚本总览（功能 + 参数详解）

> 下述参数均为当前代码实现（`scripts/`）的真实参数。

## `scripts/repo_fetcher.py`

功能：
- 拉取远程仓库或复制本地仓库到工作目录，并记录 commit 到 `repo_meta.json`。

常用命令：

```bash
python -m scripts.repo_fetcher --repo <repo_url_or_local_path> --ref main --workdir .patent_assistant --force
```

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--repo` | 是 | - | Git URL 或本地路径 |
| `--ref` | 否 | `None` | 分支/标签/提交 |
| `--workdir` | 否 | `.patent_assistant` | 工作目录 |
| `--dest` | 否 | `repo` | 输出子目录名 |
| `--force` | 否 | `False` | 覆盖已有目录 |
| `--clone-retries` | 否 | `3` | 克隆重试次数 |
| `--clone-backoff` | 否 | `2.0` | 克隆重试退避系数 |

## `scripts/repo_indexer.py`

功能：
- 扫描仓库，构建文件元数据、入口点和文档索引。

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--repo` | 是 | - | 本地仓库路径 |
| `--out` | 是 | - | `repo_index.json` 输出路径 |
| `--max_files` | 否 | `5000` | 最大索引文件数 |
| `--max_doc_headings` | 否 | `60` | 每个文档最多记录标题数 |

## `scripts/evidence_builder.py`

功能：
- 按 `reading_plan.json` 从仓库抽取片段，生成证据列表 `evidence.json`。

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--repo` | 是 | - | 本地仓库路径 |
| `--index` | 是 | - | `repo_index.json` |
| `--plan` | 是 | - | `reading_plan.json` |
| `--out` | 是 | - | `evidence.json` |
| `--max_chunk_chars` | 否 | 脚本内置常量 | 单片段最大字符数 |

## `scripts/query_builder.py`

功能：
- 基于 `invention_profile` 生成检索词，并可融合 `queries.agent.json`。

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--profile` | 是 | - | `invention_profile.json` |
| `--agent-queries` | 否 | `queries.agent.json` | agent 检索词文件（list 或 `{queries:[]}`） |
| `--query-source` | 否 | `auto` | `auto/agent/profile` |
| `--min-agent-queries` | 否 | `4` | auto 模式下 agent 主导阈值 |
| `--merge-profile` / `--no-merge-profile` | 否 | `True` | 是否合并 profile 检索词 |
| `--out` | 是 | - | `queries.json` |
| `--max-queries` | 否 | `8` | 最大检索词数 |
| `--min-query-tokens` | 否 | `2` | 低于该 token 数会被过滤 |
| `--strict` / `--no-strict` | 否 | `True` | 无有效 query 是否失败 |

## `scripts/patent_search.py`

功能：
- 多源检索专利并去重，输出 `prior_art.json` 和失败日志。

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--queries` | 否 | - | `queries.json` |
| `query` | 否 | - | 单条检索词（位置参数） |
| `--limit`, `-n` | 否 | `30` | 每条 query 的召回上限 |
| `--country`, `-c` | 否 | `CN` | 国家/地区偏好 |
| `--source`, `-s` | 否 | `google` | `google/lens/espacenet/cnipa/all` |
| `--analyze`, `-a` | 否 | `False` | 按相似度排序 |
| `--parallel`, `-p` | 否 | `False` | 多源并发请求 |
| `--timeout` | 否 | `45` | HTTP 超时秒数 |
| `--retries` | 否 | `4` | 重试次数 |
| `--backoff` | 否 | `1.8` | 退避系数 |
| `--jitter` | 否 | `0.25` | 重试抖动 |
| `--query-sleep` | 否 | `2.0` | query 间隔 |
| `--query-jitter` | 否 | `0.3` | query 间隔抖动 |
| `--min-query-tokens` | 否 | `2` | query 质量门限 |
| `--strict-query-quality` / `--no-strict-query-quality` | 否 | `True` | 全部 query 被丢弃是否失败 |
| `--strict-source-integrity` / `--no-strict-source-integrity` | 否 | `True` | 来源完整性门禁 |
| `--fail-on-empty` | 否 | `False` | 空召回失败（exit 2） |
| `--min-unique-patents` | 否 | `0` | 唯一专利数门槛 |
| `--fail-on-low-recall` | 否 | `False` | 低召回失败（exit 3） |
| `--out-json` | 否 | `None` | 输出 `prior_art.json` |
| `--out-md` | 否 | `None` | 输出 Markdown 列表 |
| `--failures-json` | 否 | `None` | 输出失败明细 JSON |

## `scripts/patent_fetch_claims.py`

功能：
- 抓取 TopK 文献 claims，支持缓存、断点续跑、手工回填合并与严格证据门禁。

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--in` | 是 | - | `prior_art.json` |
| `--topk` | 否 | `10` | 抓取文献数 |
| `--out` | 是 | - | `prior_art_full.json` |
| `--cache-dir` | 否 | `.patent_assistant/patent_cache` | HTML 缓存目录 |
| `--sleep` | 否 | `1.0` | 请求间隔秒数 |
| `--force` | 否 | `False` | 忽略缓存重抓 |
| `--timeout` | 否 | `40` | HTTP 超时 |
| `--retries` | 否 | `4` | 重试次数 |
| `--backoff` | 否 | `1.8` | 退避系数 |
| `--jitter` | 否 | `0.25` | 抖动 |
| `--claim-sources` | 否 | `auto` | `google,espacenet,cnipa,lens,fpo` 子集或 `auto` |
| `--resume` / `--no-resume` | 否 | `True` | 复用既有 `--out` 结果 |
| `--manual-claims` | 否 | `None` | 合并手工 claims JSON |
| `--require-min-ok-ratio` | 否 | `0.0` | 最低通过率门槛（低于 exit 2） |
| `--strict-prior-art` / `--no-strict-prior-art` | 否 | `True` | prior_art 完整性门禁 |
| `--strict-manual-evidence` / `--no-strict-manual-evidence` | 否 | `True` | 手工证据字段强校验 |

## `scripts/manual_claims_template.py`

功能：
- 从 `prior_art.json` 生成接管模板和 checklist。

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--in` | 是 | - | `prior_art.json` |
| `--topk` | 否 | `10` | 生成模板条数 |
| `--out` | 是 | - | `claims_manual.json` |
| `--out-md` | 否 | `None` | `claims_manual_checklist.md` |
| `--strict-source-integrity` / `--no-strict-source-integrity` | 否 | `True` | prior_art 来源门禁 |

## `scripts/novelty_matrix.py`

功能：
- 生成 claims-first 特征对比矩阵，并输出 `quality_gate` 统计。

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--profile` | 是 | - | `invention_profile.json` |
| `--prior-art-full` | 是 | - | `prior_art_full.json` |
| `--out` | 是 | - | `novelty_matrix.json` |
| `--max-docs` | 否 | `10` | 参与矩阵文献数 |
| `--min-claims-ok-ratio` | 否 | `0.3` | claims 通过率阈值 |
| `--fail-on-low-claims` / `--no-fail-on-low-claims` | 否 | `False` | 低于阈值是否失败 |

## `scripts/docx_renderer.py`

功能：
- 将 `disclosure.md` 渲染为 `.docx`，支持统一字体（默认宋体）。

参数：

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--input`, `-i` | 是 | - | 输入 Markdown（`disclosure.md`） |
| `--output`, `-o` | 是 | - | 输出 Word 路径 |
| `--font-name` | 否 | `宋体` | 输出字体 |

---

## 🚦关键门禁与失败码

- `query_builder --strict`：无有效 query 失败。
- `patent_search --fail-on-empty`：返回码 `2`。
- `patent_search --fail-on-low-recall --min-unique-patents N`：返回码 `3`。
- `patent_fetch_claims --require-min-ok-ratio X`：返回码 `2`。
- `novelty_matrix --fail-on-low-claims`：低于阈值时报错退出。

---

## 🧷 严格模式策略（v5.2）

- 不允许伪造 `prior_art.json`。
- 检索与 claims 阶段必须保留 `query` / `query_index` 追溯链路。
- 手工回填 claims 必须带证据来源字段。
- 被站点拦截时应报告 blocker，并请求可访问链接/PDF，不得合成结果。

---

## ❓常见问题

Q: 为什么会出现“检索成功但 claims 很低”？  
A: 通常是专利详情页被拦截（403/412/503）或页面结构差异。先启用 `fpo` 回退，再进入 Step 8B 接管补录。

Q: 最终 Word 字体如何固定宋体？  
A: `docx_renderer` 默认就是宋体；也可显式传 `--font-name 宋体`。

Q: 能否只跑检索与 claims？  
A: 可以。最小链路是 `query_builder -> patent_search -> patent_fetch_claims`。

---

## ⚖️ 合规说明

- 本项目输出用于技术整理与检索辅助，不构成法律意见。
- 新颖性/创造性的最终结论应由专利代理人结合完整对比文件确认。
