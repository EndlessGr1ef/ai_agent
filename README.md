# PRTS AI Agent - 罗德岛战术系统

一个基于 LangChain 和 ChromaDB 构建的模块化 LLM Agent 系统，专门模拟《明日方舟》中的 **PRTS (Primitive Rhodes Island Terminal Service)**。

## ✨ 核心特性

### 🤖 智能代理 (Agent)
- **PRTS 终端主题**：深度还原明日方舟终端风格，支持 `[PRTS]$`, `[INFO]`, `[STATUS]` 等状态提示。
- **双重输出格式**：自动生成 `summary`（存入记忆）和 `content`（面向博士），优化长对话性能。
- **流式输出 & 思考可见**：实时显示 `[thinking]` 过程，让博士清晰了解 PRTS 的推理逻辑。
- **上下文智能压缩**：使用本地 Transformer 模型，减少 60-80% 的历史长度，大幅降低 token 成本。
- **会话持久化记忆**：基于向量检索的长期记忆，跨会话关联博士的查询历史。

### 🔍 检索增强 (RAG) & 数据库管理
- **PRTS DB CLI** ⭐：一站式交互式 CLI 工具（`python prts_db_cli.py`），集成查询、入库、提炼、删除功能。
- **知识提炼 (Distillation)**：利用 LLM 自动将冗长的百科文档提炼为核心知识点，提升检索效率。
- **统一向量存储**：支持原始版（Raw）与提炼版（Distilled）文档共存，支持优先检索精炼内容。
- **多维元数据过滤**：精准过滤干员职业、星级、稀有度、剧情章节等属性。

### 🕷️ 智能爬虫 (Scraping)
- **PRTS Wiki 深度适配**：支持干员信息、主线/活动剧情、特殊关卡等内容的自动化采集。
- **自动增量验证**：对比在线列表与本地文件，自动识别缺失内容，实现秒级增量更新。
- **元数据自动注入**：爬取过程中自动提取剧情角色、对话数、干员星级等关键元数据。

## 📁 项目结构

```
ai_agent/
├── src/
│   ├── main.py                # 应用入口
│   ├── cli/                   # PRTS DB CLI 工具集
│   ├── agents/                # Agent 实现 (Base, Chat, RAG)
│   ├── rag/                   # RAG 核心逻辑 (Scrapers, Pipelines, Enhanced Retrieval)
│   ├── data/                  # 数据处理 (Ingestion, Distillation, Scraping)
│   ├── config/                # 统一配置 (LLM, Embeddings, Env)
│   ├── streaming/             # 流式输出处理
│   └── utils/                 # 工具类 (Memory, Token Counter, Verifier)
├── docs/
│   ├── prts/                  # 原始文档库
│   └── prts_distilled/        # 提炼版文档库
├── prts_db_cli.py             # 统一数据库管理工具
├── scrape_prts.py             # 智能爬虫脚本
└── requirements.txt           # 依赖清单
```

## 🛠️ 快速开始

### 1. 环境准备
```bash
# 安装依赖
pip install -r requirements.txt
pip install transformers  # 用于上下文压缩

# 下载预训练模型（推荐）
python download_models.py
```

### 2. 配置环境变量
创建 `.env` 文件：
```bash
ANTHROPIC_API_KEY=your_key  # 或 OPENAI_API_KEY
OPENAI_MODEL=MiniMax-M2
OPENAI_BASE_URL=https://api.minimaxi.com/anthropic
EMBED_MODEL_NAME=BAAI/bge-large-zh-v1.5
```

### 3. 数据准备 (三步曲)
```bash
# 第一步：爬取 PRTS Wiki 内容 (带自动验证)
python scrape_prts.py --type characters
python scrape_prts.py --type stories

# 第二步：启动交互式 CLI 进行管理
python prts_db_cli.py
# (在菜单中选择 3 进行知识提炼，选择 2 进行统一入库)
```

### 4. 启动 PRTS 系统
```bash
# RAG 检索模式（推荐）
python src/main.py --use-rag --session-id "doctor-001"

# 启用精炼内容优先模式
python src/main.py --use-rag --prefer-distilled
```

## 🚀 进阶用法

### 数据库管理 CLI (`prts_db_cli.py`)
交互式菜单支持：
1. **Query**: 语义搜索、统计分析、元数据检查。
2. **Ingest**: 原始/提炼文档的单项或混合入库。
3. **Distill**: 批量生成提炼版文档，跳过已处理文件。
4. **Delete**: 安全删除 Collection（带二次确认）。

### 智能爬虫参数
- `--verify-only`: 仅检查缺失，不执行下载。
- `--max-concurrent`: 设置并发数（默认 5-8，建议不要过高）。
- `--type [characters|stories|all]`: 选择采集类型。

## 📊 性能指标
- **压缩率**: 历史记录压缩 **60-80%**。
- **检索延迟**: 本地向量检索 **<100ms**。
- **存储效率**: 提炼版文档显著降低 token 消耗。

## 📝 更新日志

### v0.4.0 - 2026-01-08 - 🛡️ 统筹管理版
- ✨ **PRTS DB CLI**：新增统一的交互式数据库管理工具。
- ✨ **智能增量验证**：爬虫支持在线/本地内容自动对比。
- ✨ **优先检索策略**：支持 `is_distilled` 标记，优先读取精炼知识。
- 🔧 **架构重构**：将数据处理逻辑迁移至 `src/data` 和 `src/rag` 模块化目录。

### v0.3.1 - 2025-11-22 - 🔧 RAG 优化
- ✨ **嵌入模型统一**：全面转向 `BAAI/bge-large-zh-v1.5`，大幅提升中文理解力。

## 📄 许可证
本项目采用 MIT 许可证。

---
**[STATUS]** 系统状态: 正常 | **[AUTH]** 权限确认: 博士
