# repo2patent

一个将软件代码仓库自动转换为中国发明专利申请文档的工具。基于代码库事实和本地专利语料，生成标准的专利申请文档（摘要、权利要求书、说明书、附图说明及 DOCX 格式文档）。

## 🎯 核心功能

- **代码事实提取**：自动分析仓库的模块结构、接口设计、数据流和技术方案
- **语料学习**：学习本地专利语料风格，遵守国家知识产权局（CNIPA）专利撰写规范
- **自动生成**：生成完整的专利草稿，包括摘要、权利要求书、说明书
- **质量校验**：验证术语一致性、格式规范性、清楚性和支持性
- **附图生成**：自动生成系统架构图、流程图、模块关系图
- **DOCX 输出**：生成可提交的 DOCX 格式专利申请文档

## 📋 技术特点

### 官方规范优先
- 依据《专利法》第 26 条、第 59 条和《专利审查指南》
- 严格遵守清楚性、简要性、完整性和支持性要求
- 本地语料风格与官方规范冲突时，以官方规范为准

### 语料驱动写作
- 不使用固定模板拼接，基于真实语料学习写作风格
- 禁止将"代码解析流程"写入专利，专利对象是仓库实现的技术方案
- 术语统一，摘要、权利要求、说明书三文一致

### 质量控制
- 自动检测模糊表述、不可验证用语、术语不一致
- 多轮审查与修订流程
- 每轮修改后重新校验和渲染

## 🚀 快速开始

### 环境要求

- Python 3.8+
- 可选：Graphviz（用于生成高质量附图）
- 可选：Git（用于克隆远程仓库）

### 安装依赖

```bash
# 检查环境
.\scripts\00_check_env.ps1  # Windows
# 或
bash scripts/00_check_env.sh  # Linux/macOS
```

Python 依赖包已包含在 `.vendor/` 目录中，无需额外安装。

### 基本使用

```bash
# 1. 准备仓库（如果是远程仓库）
bash scripts/01_clone_repo.sh <your-repo-url> [branch]

# 2. 提取代码事实
python scripts/02_repo_inventory.py --repo work/repo

# 3. 查询官方规则
python scripts/query_official_rules.py --query "软件发明"

# 4. 生成专利草稿
# 由 LLM 助手基于语料和代码事实直接写作
# 结果保存到 draft/patent_draft.md

# 5. 校验草稿质量
python scripts/04_validate_draft.py --input draft/patent_draft.md

# 6. 生成附图
python scripts/generate_figures.py --input draft/patent_draft.md

# 7. 渲染 DOCX
python scripts/05_render_docx.py --input draft/patent_draft.md --output out/
```

## 📂 项目结构

```
repo2patent/
├── agents/              # LLM 代理配置
├── analysis/            # 分析结果和中间文件
│   ├── context.json              # 代码事实提取结果
│   ├── legal_rules_lookup.md     # 法规检索结果
│   ├── validation_report.md      # 质量校验报告
│   └── llm_rounds/               # 各轮写作中间稿
├── assets/              # 资源文件
│   └── STOPWORDS_ambiguous.txt   # 模糊词库
├── draft/               # 生成的专利草稿（.gitignore）
│   ├── patent_draft.md           # Markdown 格式草稿
│   └── figures/                  # 附图源文件
├── out/                 # 最终输出（.gitignore）
│   └── patent_draft_*.docx       # DOCX 格式成品
├── output/              # 备用输出目录（.gitignore）
├── references/          # 参考文件和语料
│   ├── cn111177271a-style-notes.md
│   ├── cnipa-patent-writing-2017-notes.md
│   ├── local-patent-style-skill.md
│   ├── official_rules_catalog.json
│   ├── patent-draft-template.md
│   └── patent-writing-rules.md
├── scripts/             # 工具脚本
│   ├── 00_check_env.*            # 环境检查
│   ├── 01_clone_repo.sh          # 仓库克隆
│   ├── 02_repo_inventory.py      # 代码事实提取
│   ├── 04_validate_draft.py      # 草稿校验
│   ├── 05_render_docx.py         # DOCX 渲染
│   ├── generate_figures.py       # 附图生成
│   └── query_official_rules.py   # 法规检索
├── work/                # 工作目录
│   └── repo/                     # 待分析的源码仓库
└── SKILL.md             # 完整的工作流程说明
```

## 🔧 核心脚本说明

### 代码事实提取（02_repo_inventory.py）
自动分析仓库，提取：
- 模块结构和类关系
- 方法和接口定义
- 消息主题和数据流
- 技术特征和处理逻辑

### 草稿校验（04_validate_draft.py）
检查专利草稿的：
- 术语一致性（摘要、权利要求、说明书）
- 模糊表述（"高效"、"强烈"、"较好"等）
- 格式规范（章节结构、引用关系）
- 发明名称一致性

### 附图生成（generate_figures.py）
- 优先使用 Graphviz 自动布局生成 SVG + PNG
- 无 Graphviz 时回退到 PIL 手动渲染
- 确保附图清晰、标号完整、无重叠

### DOCX 渲染（05_render_docx.py）
- 将 Markdown 草稿转换为标准 DOCX 格式
- 保持标题完整性（如"及系统"不会丢失）
- 附图单独占页并居中排版

## 🎓 工作流程

完整的语料驱动专利撰写流程：

1. **环境检查**：运行 `00_check_env.*`
2. **仓库准备**：远程仓库需运行 `01_clone_repo.sh`
3. **事实提取**：运行 `02_repo_inventory.py`
4. **法规检索**：运行 `query_official_rules.py`
5. **语料学习**：读取 `references/` 目录下的专利语料
6. **自由写作**：
   - Round 1: 技术交底（问题-方案-效果映射）
   - Round 2: 权利要求书（独立项+从属项）
   - Round 3: 说明书（五段结构完整）
   - Round 4: 审查与修订（清楚性、支持性、一致性）
7. **校验渲染**：
   - 运行 `04_validate_draft.py` 校验质量
   - 运行 `generate_figures.py` 生成附图
   - 运行 `05_render_docx.py` 输出成品

详细说明请参考 [SKILL.md](SKILL.md)。

## � 示例输出

以下是生成的专利初稿示例（摘要与权利要求书）：

![专利初稿示例 - 摘要与权利要求书](assets/patent_draft_sample.png)

*图示：基于波形数据处理系统生成的专利草稿，包含完整的摘要和6项权利要求。*

## �📝 质量要求

### 摘要
- 对象 + 场景 + 关键步骤 + 技术效果
- 不超过 300 字
- 禁止写工具流程

### 权利要求
- 独立项完整（包含全部必要技术特征）
- 从属项递进（逐步限定、不重复）
- 引用关系清晰
- 无宣传性用语

### 说明书
- 五段结构：技术领域、背景技术、发明内容、附图说明、具体实施方式
- 重点详实："技术问题"、"发明内容"、"具体实施方式"、"技术效果"
- 高密度写法：技术事实 + 处理逻辑 + 效果因果
- 术语统一、可实施程度充分

### 附图
- 系统架构图、流程图、模块关系图
- 分辨率足够、标号完整
- 无重叠、无空白图
- DOCX 中单独占页并居中

## 🚫 禁止事项

- ❌ 禁止把"解析代码生成专利"写入专利文本
- ❌ 禁止使用固定段落库拼接正文
- ❌ 禁止调用已废弃的 `03_generate_draft*.py` 脚本
- ❌ 禁止重复相同技术特征的权利要求
- ❌ 禁止使用宣传性用语替代技术论证

## 📚 参考资料

本工具遵循以下规范：
- 《中华人民共和国专利法》
- 《专利审查指南》
- 《如何撰写专利申请文件》（2017-07-20）
- CNIPA 专利撰写规范（2017）

## 📄 许可证

本项目仅供学习和研究使用。生成的专利草稿需经专业代理人审核后方可提交。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## ⚠️ 免责声明

- 本工具生成的专利草稿仅供参考，不构成法律意见
- 实际提交前必须经过专业专利代理人审核和修改
- 专利申请的法律责任由申请人自行承担

## 📮 联系方式

如有问题或建议，请在 GitHub 上提交 Issue。
