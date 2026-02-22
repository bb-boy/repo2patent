# repo2patent

**必做**：Repo → 证据包 → 关键特征（profile）→ 检索召回（A）→ 抓取权利要求（B）→ 特征对比/新颖点（C）→ 交底书 Word（.docx）

## 依赖
- Python 3.8+
- git
- 输出 Word（可选）：python-docx
  - `pip install python-docx`

## 脚本最小集合（v4）
- repo_fetcher.py
- repo_indexer.py
- evidence_builder.py（内置 reading_plan 校验）
- query_builder.py（agent优先生成 + profile回退 + 质量门禁）
- patent_search.py（召回 prior_art.json）
- patent_fetch_claims.py（自动抓取+合并人工 claims → prior_art_full.json）
- manual_claims_template.py（生成人工 claims 回填模板）
- novelty_matrix.py（基于 claims 的矩阵 + 差异候选）
- docx_renderer.py

## 快速跑通（示例）
```bash
python scripts/repo_fetcher.py --repo <repo_url> --workdir .patent_assistant --force
python scripts/repo_indexer.py --repo .patent_assistant/repo --out .patent_assistant/repo_index.json
# LLM -> reading_plan.json
python scripts/evidence_builder.py --repo .patent_assistant/repo --index .patent_assistant/repo_index.json --plan reading_plan.json --out .patent_assistant/evidence.json
# LLM -> invention_profile.json
# Codex agent -> queries.agent.json（list 或 {"queries":[...]})
python scripts/query_builder.py --profile invention_profile.json --agent-queries queries.agent.json --query-source auto --out queries.json
python scripts/patent_search.py --queries queries.json -s google -c CN -n 30 -a --min-unique-patents 10 --fail-on-low-recall --out-json prior_art.json
python scripts.patent_fetch_claims.py --in prior_art.json --topk 10 --claim-sources auto --out prior_art_full.json --cache-dir .patent_assistant/patent_cache
python scripts/novelty_matrix.py --profile invention_profile.json --prior-art-full prior_art_full.json --out novelty_matrix.json
# LLM -> disclosure.md + missing_info.md
python scripts/docx_renderer.py --input disclosure.md --output disclosure.docx
```

## agent 检索词格式
`queries.agent.json` 支持两种格式：
```json
["query one", "query two"]
```
或
```json
{"queries": ["query one", "query two"]}
```



## Step10 结构化输出
- novelty_findings.json: 结构化新颖点结论（schema: references/schemas/novelty_findings.schema.json）

## 稳健运行建议（P0/P1/P2）

### P0：输入质量门禁 + 低质量结果拦截
```bash
python -m scripts.query_builder \
  --profile invention_profile.json \
  --agent-queries queries.agent.json \
  --query-source auto \
  --min-agent-queries 4 \
  --out queries.json \
  --strict \
  --min-query-tokens 2

python -m scripts.novelty_matrix \
  --profile invention_profile.json \
  --prior-art-full prior_art_full.json \
  --out novelty_matrix.json \
  --min-claims-ok-ratio 0.3 \
  --fail-on-low-claims
```

### P1：检索/抓取重试退避与失败明细
```bash
python -m scripts.patent_search \
  --queries queries.json \
  -s google -c CN -n 30 \
  --timeout 45 --retries 4 --backoff 1.8 --jitter 0.25 \
  --query-sleep 2 --query-jitter 0.3 \
  --min-unique-patents 10 --fail-on-low-recall \
  --fail-on-empty \
  --out-json prior_art.json \
  --failures-json prior_art.failures.json

python -m scripts.patent_fetch_claims \
  --in prior_art.json --topk 10 \
  --claim-sources auto \
  --timeout 40 --retries 4 --backoff 1.8 --jitter 0.25 \
  --sleep 2 --resume \
  --out prior_art_full.json \
  --cache-dir .patent_assistant/patent_cache
```

### P2：多源召回 + 人工 claims 兜底
```bash
# 多源召回（Google失败时仍可保留 Lens/Espacenet/CNIPA 候选）
python -m scripts.patent_search --queries queries.json -s all -n 20 --min-unique-patents 15 --fail-on-low-recall --out-json prior_art.json

# 生成人工 claims 回填模板（由 Codex agent 执行）
python -m scripts.manual_claims_template \
  --in prior_art.json \
  --topk 10 \
  --out claims_manual.json \
  --out-md claims_manual_checklist.md

# Codex agent 抓取/提取 claims 后合并（manual file: {"items":[{patent_number, claims_text|claims}...]})
python -m scripts.patent_fetch_claims \
  --in prior_art.json --topk 10 \
  --resume \
  --manual-claims claims_manual.json \
  --require-min-ok-ratio 0.3 \
  --out prior_art_full.json
```
