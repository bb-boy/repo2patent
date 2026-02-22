# repo2patent

`repo2patent` 是一个面向中国发明专利交底场景的工作流：从 GitHub 项目提取技术证据，生成检索式并完成专利召回，抓取/补录 claims，构建特征对比矩阵，最后产出可交付的 `disclosure.docx`。

## 项目解决什么问题

传统“写交底书”常见断点是：
1. 对代码理解不完整，技术点描述空泛。
2. 只做了标题/摘要级检索，没有进入 claims 级别比对。
3. 新颖点缺少结构化证据链，难以复核。

本项目将流程拆成可审计的中间产物，每一步都有文件输出，支持失败重试和人工兜底。

## 核心能力

1. 从仓库构建 `repo_index.json`，给 LLM 一个结构化“读码导航”。
2. 用 `reading_plan.json` 控制读码范围，输出可追溯 `evidence.json`。
3. 基于 `invention_profile.json` 生成检索式并执行多源召回。
4. 抓取 TopK 对比文献 claims，失败时自动走人工 claims 模板兜底。
5. 输出 claims-first 的 `novelty_matrix.json`，给出候选新颖点组合。
6. 生成 `disclosure.md` 并渲染 `disclosure.docx`。

## 目录结构

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
└─ README.md
```

## 依赖

1. Python 3.8+
2. Git
3. 可选：`python-docx`（只有输出 Word 时需要）

```bash
pip install python-docx
```

## 快速开始（端到端）

在项目根目录执行：

```bash
python scripts/repo_fetcher.py --repo <repo_url_or_local_path> --ref <optional> --workdir .patent_assistant --force
python scripts/repo_indexer.py --repo .patent_assistant/repo --out .patent_assistant/repo_index.json
# LLM 生成 reading_plan.json（符合 references/schemas/reading_plan.schema.json）
python scripts/evidence_builder.py --repo .patent_assistant/repo --index .patent_assistant/repo_index.json --plan reading_plan.json --out .patent_assistant/evidence.json
# LLM 生成 invention_profile.json（符合 references/schemas/invention_profile.schema.json）
python scripts/query_builder.py --profile invention_profile.json --agent-queries queries.agent.json --query-source auto --out queries.json
python scripts/patent_search.py --queries queries.json -s google -c CN -n 30 -a --min-unique-patents 10 --fail-on-low-recall --out-json prior_art.json --failures-json prior_art.failures.json
python scripts/patent_fetch_claims.py --in prior_art.json --topk 10 --claim-sources auto --resume --out prior_art_full.json --cache-dir .patent_assistant/patent_cache
python scripts/novelty_matrix.py --profile invention_profile.json --prior-art-full prior_art_full.json --min-claims-ok-ratio 0.3 --out novelty_matrix.json
# LLM 生成 novelty_findings.json + disclosure.md + missing_info.md
python scripts/docx_renderer.py --input disclosure.md --output disclosure.docx
```

## 详细工作流（每一步含结果示例）

### Step 1: 拉取仓库并固化版本

命令：

```bash
python scripts/repo_fetcher.py --repo https://github.com/example/project.git --ref main --workdir .patent_assistant --force
```

终端示例：

```text
[ok] repo at: .patent_assistant/repo
[ok] commit: 7d8a3d9c6e...
```

产物：`.patent_assistant/repo_meta.json`

```json
{
  "repo_input": "https://github.com/example/project.git",
  "repo_path": "C:/work/repo2patent/.patent_assistant/repo",
  "ref": "main",
  "commit_sha": "7d8a3d9c6e...",
  "fetched_at": "2026-02-22T02:00:00Z"
}
```

### Step 2: 生成仓库索引

命令：

```bash
python scripts/repo_indexer.py --repo .patent_assistant/repo --out .patent_assistant/repo_index.json
```

终端示例：

```text
[ok] indexed files: 326
[ok] entrypoints: ['src/main.py']
[ok] out: .patent_assistant/repo_index.json
```

产物：`.patent_assistant/repo_index.json`

```json
{
  "repo": {
    "url": "https://github.com/example/project.git",
    "path": "C:/work/repo2patent/.patent_assistant/repo",
    "commit_sha": "7d8a3d9c6e..."
  },
  "entrypoints": ["src/main.py"],
  "top_recommended": ["README.md", "src/main.py", "src/pipeline/scheduler.py"]
}
```

### Step 3: 让 LLM 产出 reading_plan.json

输入：`repo_index.json`  
约束：`references/schemas/reading_plan.schema.json`

最小示例：

```json
{
  "plan_version": "1.0",
  "goals": ["提取关键技术机制", "定位可专利化特征"],
  "limits": {
    "max_files": 20,
    "max_total_chars": 150000
  },
  "selections": [
    {
      "path": "README.md",
      "read_type": "full",
      "priority": 5,
      "reason": "获取系统总览",
      "expected_extract": ["系统目标", "模块边界"],
      "tags": ["overview"]
    },
    {
      "path": "src/main.py",
      "read_type": "head",
      "selectors": {"lines": 220},
      "priority": 4,
      "reason": "抓入口流程",
      "expected_extract": ["入口参数", "主流程调用"]
    }
  ]
}
```

### Step 4: 根据 reading plan 生成证据包

命令：

```bash
python scripts/evidence_builder.py --repo .patent_assistant/repo --index .patent_assistant/repo_index.json --plan reading_plan.json --out .patent_assistant/evidence.json
```

终端示例：

```text
[ok] evidence items: 19
[ok] total_chars: 84217
[ok] out: .patent_assistant/evidence.json
```

产物：`.patent_assistant/evidence.json`

```json
[
  {
    "id": "E0001",
    "path": "src/pipeline/scheduler.py",
    "line_range": [45, 103],
    "excerpt": "class Scheduler: ...",
    "tags": ["scheduling", "core_mechanism"],
    "why_selected": "核心调度算法",
    "source": "repo",
    "read_type": "symbols"
  }
]
```

### Step 5: 让 LLM 产出 invention_profile.json

输入：`repo_meta.json` + `evidence.json`  
约束：`references/schemas/invention_profile.schema.json`

最小示例：

```json
{
  "title": "一种面向异构任务的自适应调度方法",
  "technical_field": {
    "domain": "分布式计算",
    "sub_domain": "任务调度"
  },
  "background_problems": ["现有队列策略无法兼顾时延和吞吐"],
  "core_problem": "多目标约束下调度不稳定",
  "solution_overview": "构建带反馈的分层调度器并动态调权",
  "key_features": [
    {"id": "F1", "text": "按任务画像分层入队", "evidence_ids": ["E0001"]},
    {"id": "F2", "text": "使用反馈回路动态调整权重", "evidence_ids": ["E0003"]},
    {"id": "F3", "text": "失败任务触发差异化重试策略", "evidence_ids": ["E0007"]}
  ],
  "keywords": {
    "cn": ["调度", "重试", "反馈控制"],
    "en": ["scheduler", "retry", "feedback loop"]
  }
}
```

### Step 6: 生成检索式 queries.json

命令：

```bash
python scripts/query_builder.py --profile invention_profile.json --agent-queries queries.agent.json --query-source auto --min-agent-queries 4 --out queries.json
```

终端示例：

```text
[ok] queries: 8
[warn] agent query file not found: queries.agent.json
[ok] out: queries.json
```

产物：`queries.json`

```json
{
  "query_source": "profile_fallback_no_agent",
  "agent_queries_raw_count": 0,
  "agent_queries_valid_count": 0,
  "queries": [
    "调度 重试 反馈控制",
    "scheduler retry feedback loop"
  ],
  "warnings": [
    "agent query file not found: queries.agent.json"
  ]
}
```

说明：`queries.agent.json` 支持两种格式。

```json
["query one", "query two"]
```

```json
{"queries": ["query one", "query two"]}
```

### Step 7: 执行专利召回 prior_art.json

命令：

```bash
python scripts/patent_search.py --queries queries.json -s google -c CN -n 30 -a --min-unique-patents 10 --fail-on-low-recall --out-json prior_art.json --failures-json prior_art.failures.json
```

终端示例：

```text
[ok] written json: prior_art.json
[ok] total items: 34
[ok] unique patents: 22
[ok] valid queries: 8, dropped queries: 1
[ok] source failures: 0
```

产物：`prior_art.json`

```json
[
  {
    "source": "Google Patents",
    "patent_number": "CN114567890A",
    "title": "一种任务调度方法及装置",
    "abstract": "本发明公开了...",
    "url": "https://patents.google.com/patent/CN114567890A",
    "query": "调度 重试 反馈控制",
    "query_index": 1,
    "similarity_score": 66.7
  }
]
```

常见失败码：
1. `--fail-on-empty` 且无结果时返回码 `2`
2. `--fail-on-low-recall` 且唯一专利数不足时返回码 `3`

### Step 8: 抓取 claims，生成 prior_art_full.json

命令：

```bash
python scripts/patent_fetch_claims.py --in prior_art.json --topk 10 --claim-sources auto --resume --out prior_art_full.json --cache-dir .patent_assistant/patent_cache --require-min-ok-ratio 0.3
```

终端示例：

```text
[ok] fetched claims: 7/10 (ratio=0.700)
[ok] status counts: {'ok': 6, 'ok_fallback': 1, 'fetch_blocked_403': 3}
[ok] out: prior_art_full.json
```

产物：`prior_art_full.json`

```json
[
  {
    "source": "Google Patents",
    "patent_number": "CN114567890A",
    "title": "一种任务调度方法及装置",
    "url": "https://patents.google.com/patent/CN114567890A",
    "claims_status": "ok",
    "claims_source": "google",
    "claims_page_url": "https://patents.google.com/patent/CN114567890A",
    "claims_text": "1. 一种任务调度方法，其特征在于...",
    "claims": [
      {"num": "1", "text": "一种任务调度方法，其特征在于..."}
    ],
    "claims_fetch_attempts": [
      {
        "source": "google",
        "url": "https://patents.google.com/patent/CN114567890A",
        "result": "ok",
        "claims_count": 12
      }
    ]
  }
]
```

门禁：当 `ok/ok_fallback/manual_ok` 比例低于 `--require-min-ok-ratio` 时，脚本返回码 `2`。

### Step 8B: claims 抓取失败时人工兜底

先生成模板：

```bash
python scripts/manual_claims_template.py --in prior_art.json --topk 10 --out claims_manual.json --out-md claims_manual_checklist.md
```

终端示例：

```text
[ok] template items: 10
[ok] out: claims_manual.json
[ok] out-md: claims_manual_checklist.md
```

模板示例：

```json
{
  "generated_at": "2026-02-22T02:20:00Z",
  "input": "prior_art.json",
  "topk": 10,
  "items": [
    {
      "rank": 1,
      "patent_number": "CN114567890A",
      "url": "https://patents.google.com/patent/CN114567890A",
      "claims_text": "",
      "claims": [],
      "notes": "Fill at least independent claim(s). Use plain text."
    }
  ]
}
```

补录后再合并：

```bash
python scripts/patent_fetch_claims.py --in prior_art.json --topk 10 --resume --manual-claims claims_manual.json --require-min-ok-ratio 0.3 --out prior_art_full.json
```

### Step 9: 构建 novelty_matrix.json

命令：

```bash
python scripts/novelty_matrix.py --profile invention_profile.json --prior-art-full prior_art_full.json --min-claims-ok-ratio 0.3 --fail-on-low-claims --out novelty_matrix.json
```

终端示例：

```text
[ok] features: 8, documents: 10
[ok] claims gate: 7/10=0.700 (min=0.300, pass=True)
[ok] out: novelty_matrix.json
```

产物：`novelty_matrix.json`

```json
{
  "quality_gate": {
    "claims_ok": 7,
    "claims_total": 10,
    "claims_ok_ratio": 0.7,
    "min_claims_ok_ratio": 0.3,
    "pass": true
  },
  "top_prior_art": [
    {
      "patent_number": "CN114567890A",
      "title": "一种任务调度方法及装置",
      "overall_match": 4.83
    }
  ],
  "novelty_candidates": [
    {
      "feature_id": "F2",
      "feature": "使用反馈回路动态调整权重",
      "no_ratio": 0.6,
      "partial_ratio": 0.2
    }
  ],
  "pair_candidates": [
    {
      "pair": ["F2", "F5"],
      "union_ratio": 0.7,
      "co_ratio": 0.1
    }
  ]
}
```

### Step 10: 让 LLM 产出新颖点结论和交底草稿

输入：
1. `invention_profile.json`
2. `prior_art.json`
3. `prior_art_full.json`
4. `novelty_matrix.json`
5. `templates/disclosure_template_cn_invention.md`
6. `references/06_novelty_playbook.md`
7. `references/07_novelty_findings_output.md`

输出：
1. `novelty_findings.json`（符合 `references/schemas/novelty_findings.schema.json`）
2. `disclosure.md`
3. `missing_info.md`（如果仍有缺口）

`novelty_findings.json` 最小示例：

```json
{
  "generated_at": "2026-02-22T02:30:00Z",
  "scope": {
    "repo_url": "https://github.com/example/project.git",
    "commit_sha": "7d8a3d9c6e...",
    "country": "CN",
    "search_sources": ["google"],
    "topk_claims": 10
  },
  "closest_prior_art": [
    {
      "patent_number": "CN114567890A",
      "title": "一种任务调度方法及装置",
      "url": "https://patents.google.com/patent/CN114567890A",
      "why_close": "覆盖了F1/F3，但未覆盖F2的反馈机制"
    }
  ],
  "novelty_points": [
    {
      "id": "NP1",
      "feature_ids": ["F2", "F5"],
      "statement": "引入反馈闭环与差异化重试策略的组合",
      "differential": "最接近文献未公开两者联动机制",
      "supporting_prior_art": [
        {
          "patent_number": "CN114567890A",
          "url": "https://patents.google.com/patent/CN114567890A",
          "matrix_evidence": [
            {"feature_id": "F2", "label": "NO", "score_best": 0.12}
          ]
        }
      ],
      "supporting_snippets": ["...claims snippet..."],
      "confidence": "medium",
      "notes": "建议人工复核独权文本"
    }
  ],
  "risks": [
    {
      "type": "needs_full_text_review",
      "description": "部分文献仅抓取到摘要级描述",
      "impact": "medium"
    }
  ],
  "actions": [
    {
      "action": "补充Top20文献独立权利要求精读",
      "priority": 1,
      "owner": "agent"
    }
  ],
  "evidence_trace": {
    "inputs": {
      "invention_profile": "invention_profile.json",
      "prior_art": "prior_art.json",
      "prior_art_full": "prior_art_full.json",
      "novelty_matrix": "novelty_matrix.json"
    },
    "outputs": {
      "novelty_findings": "novelty_findings.json",
      "disclosure_md": "disclosure.md"
    }
  }
}
```

### Step 11: 渲染 Word 交底书

命令：

```bash
python scripts/docx_renderer.py --input disclosure.md --output disclosure.docx
```

终端示例：

```text
[ok] written: disclosure.docx
```

最终交付物：
1. `disclosure.docx`
2. `novelty_findings.json`
3. `novelty_matrix.json`
4. `prior_art_full.json`
5. `missing_info.md`（如有）

## 关键门禁与失败处理

1. `query_builder.py --strict`：无有效 query 直接失败。
2. `patent_search.py --fail-on-empty`：无召回直接失败。
3. `patent_search.py --fail-on-low-recall`：唯一专利数不足失败。
4. `patent_fetch_claims.py --require-min-ok-ratio`：claims 质量不足失败。
5. `novelty_matrix.py --fail-on-low-claims`：claims 质量门禁失败即停止。

推荐策略：失败时不要跳步，先修复上一步输入再继续。

## 常见问题

1. 检索结果少：提高 query 质量，扩展同义词，增加 `-s all` 多源召回。
2. claims 抓取失败：使用 `manual_claims_template.py` 走人工补录再合并。
3. 文档乱码：统一 UTF-8 编码（含 BOM 文件可读，脚本支持 `utf-8-sig`）。
4. docx 生成失败：安装 `python-docx`。

## 合规声明

1. 本项目输出为“技术与检索辅助结果”，不构成法律意见。
2. 新颖性与创造性结论应由专利代理人结合完整对比文献最终确认。

