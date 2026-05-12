<div align="center">

# 🧳 Multi-Agent 智能旅行助手

**一个借鉴 Microsoft Agent Framework Magentic 模式的多 Agent 编排实战项目**

基于 FastAPI 和 DeepSeek 构建的端到端旅行助手，由 Manager LLM 负责调度，5 个领域 Agent 协作完成需求澄清 → 行程规划 → 交通规划 → 票务搜索 → 输出质检全流程，接入高德、小红书、12306、飞常准等生态 MCP，并配备分层记忆系统支持个性化服务。

[English](README_EN.md) | 中文

[![Python](https://img.shields.io/badge/Python-3.11+-3776ab.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-1c4ed8.svg)](https://www.deepseek.com/)
[![MCP](https://img.shields.io/badge/MCP-1.2+-7c3aed.svg)](https://modelcontextprotocol.io/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ed.svg?logo=docker&logoColor=white)](#-快速开始-docker-推荐)
[![CI](https://img.shields.io/badge/CI-pytest-success.svg)](.github/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## ✨ 核心亮点

| 维度 | 实现 |
| --- | --- |
| **多 Agent 编排** | Manager LLM 用 JSON 输出 `next_agent / subtask / final_answer`，路由到 5 个领域 Agent；每个 Agent 内部 ReAct 循环 + 工具调用 |
| **真实 MCP 接入** | 自研 `MCPClient` 同时支持 **SSE / Streamable HTTP**，集成高德、小红书、12306、飞常准、AIGOHOTEL 酒店 5 个生态 MCP；任一未配置自动 mock 兜底 |
| **分层记忆系统** | **短期记忆**（进程内按会话缓存，30 分钟自动过期）存储会话便签与完整消息；**长期记忆**（SQLite 持久化）存储跨对话用户偏好；两层统一注入 Manager 和下游 Agent 上下文 |
| **DeepSeek 兼容兜底** | 处理 DeepSeek 偶发以 DSML 形式输出工具调用的问题（`_parse_dsml_calls`）；manager `json_object` 模式双层包裹兜底（`_extract_decision`） |
| **流式可中断** | FastAPI + `sse-starlette` 推送 `manager / agent_start / agent_end / final` 事件；前端 `AbortController` 一键打断，后端自动取消 orchestrator |
| **POI 智能链接化** | 后端 `_enrich_poi_locations` 用高德 geocode 给 LLM 输出的店名补坐标；前端 `linkifyPois` 包成可点 marker URL，店名直接跳高德 Web |
| **域名白名单超链接** | 渲染 markdown 时按域名分配色：小红书 红 / 携程 蓝 / 12306 绿 / 高德 POI 粉，其它域名 URL 一律剥成纯文字防止 LLM 编造 |
| **本地经验补充** | 导航 Agent 给完官方公交方案后强制再走小红书，挖村巴 / 接驳车 / 直通车这些高德漏掉的本地路线 |
| **DEMO_MODE 离线演示** | 一个开关把所有 MCP URL 视为空，全部走 mock；零外部 key 即可体验完整流程 |

> 完整改造点（DeepSeek 兼容、anyio cancel scope 修复、POI 坐标补全、SSE 取消、分层记忆等）记录在 commit history 与源码注释中。



**数据流**：用户输入 → 浏览器自动定位 → 读取分层记忆（短期会话便签 + 长期偏好）→ Manager LLM 决策 → 选定 Agent 跑工具循环 → 工具结果回流给 Agent → 必要时 Manager 再分派 → `final` 事件携带 markdown + POI 列表 + 用户位置 → 前端渲染（含店名/链接超链接化），同时同步消息到短期缓存。

---

## 🧠 分层记忆系统

| | 短期记忆 | 长期记忆 |
|---|---|---|
| **存储方式** | 进程内 Python dict | SQLite 数据库 |
| **作用域** | 单次会话（30 分钟无活动过期；重启消失） | 跨对话永久有效 |
| **内容** | 完整消息缓存（最近 20 条供 Manager 使用）+ 会话便签 | 用户偏好列表 |
| **写入工具** | `save_session_context`（出行人数、日期、目的地等） | `save_user_preference`（饮食禁忌、住宿偏好等） |
| **注入位置** | Manager 系统提示 + 所有 Agent extra_context | Manager 系统提示 + 所有 Agent extra_context |

短期缓存消失时自动降级读 DB 历史（最近 8 条），保证跨重启上下文不丢。

---

## 🛠️ 技术栈

- **后端**：Python 3.11、FastAPI、`sse-starlette`、`mcp`（官方 SDK，SSE + Streamable HTTP）、`openai` SDK（兼容 DeepSeek）、Pydantic v2、SQLAlchemy 异步
- **LLM**：DeepSeek-Chat（function calling，本项目所有 Agent 工具调用基础）
- **MCP**：高德、小红书（`xpzouying/xiaohongshu-mcp`）、12306（`Joooook/12306-mcp`，魔搭社区托管）、飞常准（魔搭社区托管）、AIGOHOTEL 酒店（`yorklu/AI_Go_Hotel_MCP`，魔搭社区托管）
- **存储**：SQLite（默认）/ PostgreSQL（生产可切换），异步 SQLAlchemy
- **前端**：纯 HTML/CSS/JS 单文件 SPA，自研轻量 markdown 渲染器，浏览器 `navigator.geolocation`
- **部署**：Docker + docker-compose

---

## 🚀 快速开始 (Docker, 推荐)

```powershell
# 1. 克隆
git clone <your-repo-url> travelagent
cd travelagent

# 2. 配置 .env（最小可运行：只需 OPENAI_API_KEY）
copy .env.example .env
# 用记事本编辑 .env，把 OPENAI_API_KEY 换成你的 DeepSeek key
# 想完全离线体验？把 DEMO_MODE=true，所有 MCP 自动走 mock，无需任何外部 key

# 3. 一键起
docker compose up -d --build

# 4. 打开浏览器
start http://127.0.0.1:8000
```

**进阶**：本地起小红书 / 12306 MCP 容器：

```powershell
# 同时启动 backend + 小红书 MCP（首次需扫码登录）
docker compose --profile xhs up -d
docker exec -it xhs-mcp /app/login   # 用手机扫码

# 启用本地 12306 MCP（也可改用魔搭 SSE，见下文）
docker compose --profile train up -d
```

---

## 🐍 快速开始 (本地 Python)

```powershell
# 用 conda（推荐，避免 anyio / mcp 版本打架）
conda create -n travelagent python=3.11 -y
conda activate travelagent
pip install -r requirements.txt

# 配置
copy .env.example .env
notepad .env

# 启动
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
# 访问 http://127.0.0.1:8000
```

运行单元测试：

```powershell
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## 💬 体验建议

| 场景 | 试试这样问 | 触发的 Agent |
| --- | --- | --- |
| 模糊需求 → 澄清 | 「想去成都玩」 | interaction |
| 明确行程 → 排日程 | 「5 月 17-19 日，成都，预算 3000，喜欢小众」 | planning |
| 会话便签记录 | 「我们 3 个人，其中一个小孩」 | interaction（保存短期记忆） |
| 实时改路 | 点右上「定位」后问「附近有什么吃的？」 | navigation |
| 本地经验 | 「我现在在黄埔区，怎么去广州塔，最好有本地人推荐的路线」 | navigation + xhs |
| 票务搜索 | 「5 月 17 日北京到上海有什么高铁」 | search |
| 长期偏好 | 「我不吃香菜」「喜欢有泳池的酒店」 | interaction（保存长期记忆） |
| 中途想停 | 任意复杂提问后点红色「停止」按钮 | AbortController |

---

## 🔌 接真实 MCP Server

`MCPClient` 按 URL 路径自动选 transport：`/sse` 走 SSE，`/mcp` 走 Streamable HTTP。任一 URL 留空 / 调用抛异常都会自动落 mock。

### 高德（推荐必接）

```env
AMAP_MCP_URL=https://mcp.amap.com/sse?key=YOUR_AMAP_KEY
AMAP_API_KEY=YOUR_AMAP_KEY
```

申请：<https://lbs.amap.com/api/mcp-server>

### 飞常准（机票）

魔搭社区托管，登录后获取个人 SSE 端点：

```env
VARIFLIGHT_MCP_URL=https://mcp.api-inference.modelscope.net/<your-token>/sse
```

入口：[ModelScope · Variflight MCP](https://www.modelscope.cn/mcp/servers/@variflight-ai/variflight-mcp)

### 12306

推荐魔搭社区托管，免本地部署：

```env
TRAIN12306_MCP_URL=https://mcp.api-inference.modelscope.net/<your-token>/sse
```

入口：[ModelScope · @Joooook/12306-mcp](https://www.modelscope.cn/mcp/servers/@Joooook/12306-mcp)

后端已适配 `get-tickets` 工具，自动用 `from_station_telecode` 拼出 12306 真实余票页 URL，前端把车次号渲染成绿色可点链接。

### 小红书（社区方案）

[`xpzouying/xiaohongshu-mcp`](https://github.com/xpzouying/xiaohongshu-mcp) 走 Streamable HTTP，需扫码登录：

```powershell
docker compose --profile xhs up -d
docker exec -it xhs-mcp /app/login
```

```env
XHS_MCP_URL=http://localhost:18060/mcp
```

### AIGOHOTEL 酒店

魔搭社区托管（`yorklu/AI_Go_Hotel_MCP`），支持真实酒店搜索：

1. 前往 <https://mcp.agentichotel.cn/apply> 申请 API Key（`mcp_` 前缀）
2. 在 [ModelScope · AI_Go_Hotel_MCP](https://www.modelscope.cn/mcp/servers/yorklu/AI_Go_Hotel_MCP) 登录后获取个人 SSE/MCP 端点，形如：
   `https://mcp.api-inference.modelscope.net/<your-token>/mcp`

```env
HOTEL_MCP_URL=https://mcp.api-inference.modelscope.net/<your-token>/mcp
```

留空则自动走内置 mock 兜底。


## 📂 目录结构

```
travelagent/
├── backend/
│   ├── agents/                # 5 个 Agent
│   │   ├── base.py            # Agent 基类 + ReAct 循环 + DSML 兼容兜底
│   │   ├── interaction.py     # 澄清需求 + 分层记忆写入
│   │   ├── planning.py
│   │   ├── navigation.py
│   │   ├── search.py
│   │   └── testing.py
│   ├── mcp/                   # 5 个 MCP 客户端 + mock
│   │   ├── base.py            # MCPClient（短连接 + SSE/Streamable HTTP 自动选）
│   │   ├── amap.py
│   │   ├── xhs.py
│   │   ├── train12306.py
│   │   ├── hotel.py
│   │   └── variflight.py
│   ├── memory/
│   │   ├── memory_store.py    # 长期记忆（SQLAlchemy 异步，SQLite/PG）
│   │   └── short_term.py      # 短期记忆（进程内缓存，30 分钟自动过期）
│   ├── orchestrator.py        # Manager LLM 编排 + 分层记忆调度
│   ├── config.py
│   └── main.py                # FastAPI 入口
├── frontend/
│   └── index.html             # 单文件 SPA（含 markdown 渲染、SSE、定位、暂停）
├── tests/                     # pytest 单元测试
├── data/                      # 运行时数据库（memory.db）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```







## 📄 License

MIT
