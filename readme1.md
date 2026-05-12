# 🤖 Multi-Agent 智能旅行助手

一个基于多 Agent 协作的智能旅行规划系统，通过多个专业 Agent 分工协作，为用户提供个性化的旅行规划、景点推荐、美食搜索、交通查询等一站式服务。

> 灵感来源于 Microsoft Agent Framework 的 Magentic 编排思路，使用 Manager LLM 动态决策 Agent 调用流程。

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)
![DeepSeek](https://img.shields.io/badge/DeepSeek-Chat-orange)
![MCP](https://img.shields.io/badge/MCP-Protocol-purple)

---

## ✨ 功能特性

### 核心功能
- **🗺️ 智能行程规划** - 根据用户偏好、预算、时间自动生成完整旅行方案
- **📍 实时定位推荐** - 基于 GPS 坐标推荐附近景点、餐厅，提供高德导航链接
- **✈️ 交通查询** - 机票（飞常准）、火车票（12306）实时查询
- **📕 小红书攻略** - 搜索真实用户分享的旅行笔记与避坑指南
- **💾 用户记忆** - 自动保存用户偏好（饮食禁忌、酒店要求等），下次自动应用

### 技术亮点
- **SSE 流式响应** - 实时推送 Agent 思考过程与执行结果
- **MCP 协议支持** - 统一接入多个第三方服务（高德、小红书、飞常准等）
- **自动降级** - MCP 服务不可用时无缝切换到 Mock 数据，保证体验不断链
- **多 Agent 编排** - 5 个专业 Agent 协作，Manager LLM 动态调度

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| AI 模型 | DeepSeek Chat（兼容 OpenAI API） |
| Agent 架构 | 自定义多 Agent 编排 + Function Calling |
| 协议支持 | MCP (Model Context Protocol) - SSE / HTTP |
| 前端 | 纯 HTML/CSS/JS 单页应用，手机壳 UI |
| 数据存储 | JSON 文件持久化 (data/memory.json) |

---

## 📁 项目结构

```
travelagent/
├── backend/
│   ├── agents/              # 5 个专业 Agent
│   │   ├── base.py          # Agent 基类（Tool Calling 封装）
│   │   ├── interaction.py   # 交互 Agent：澄清需求、保存偏好
│   │   ├── planning.py      # 规划 Agent：行程生成、小红书+高德+携程
│   │   ├── navigation.py    # 导航 Agent：定位、周边搜索、路线规划
│   │   ├── search.py        # 搜索 Agent：机票、火车、机场天气
│   │   └── testing.py       # 测试 Agent：最终回复质检
│   ├── mcp/                 # MCP 客户端（支持 mock 降级）
│   │   ├── base.py          # MCPClient 统一封装（SSE/HTTP 自动识别）
│   │   ├── amap.py          # 高德地图（逆地理编码、POI、导航）
│   │   ├── xhs.py           # 小红书（笔记搜索）
│   │   ├── variflight.py    # 飞常准（机票查询）
│   │   └── train12306.py    # 12306（火车查询）
│   ├── memory/
│   │   └── memory_store.py  # 用户偏好持久化
│   ├── config.py            # 环境变量配置中心
│   ├── orchestrator.py      # 主持人编排（Manager LLM 决策调度）
│   └── main.py              # FastAPI 入口
├── frontend/
│   └── index.html           # 手机壳风格聊天 UI（单文件 SPA）
├── data/
│   └── memory.json          # 运行时生成的用户记忆文件
├── requirements.txt         # Python 依赖
├── .env.example             # 环境变量模板
└── readme1.md               # 本文件
```

---

## 🚀 快速开始

### 1. 克隆项目并创建虚拟环境

```bash
# 创建虚拟环境
python -m venv .venv

# Windows
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 DeepSeek API Key
# 其他 MCP 服务 URL 可以先留空，系统会自动使用 mock 数据
```

**必需配置**：
```env
OPENAI_API_KEY=sk-your-api-key-here
```

### 4. 启动服务

```bash
python -m backend.main
```

访问 http://127.0.0.1:8000 即可看到手机壳风格的聊天界面。

---

## ⚙️ MCP 服务配置（可选）

系统支持 5 个 MCP 服务，URL 留空时会自动使用内置 mock 数据。

### 高德地图（推荐接入）

```env
AMAP_MCP_URL=https://mcp.amap.com/sse?key=YOUR_AMAP_KEY
AMAP_API_KEY=YOUR_AMAP_KEY
AMAP_JS_KEY=YOUR_JS_KEY  # 用于前端地图展示
```
申请地址：https://lbs.amap.com/api/mcp-server

### 飞常准（机票查询）

```env
VARIFLIGHT_MCP_URL=https://mcp.api-inference.modelscope.net/<your-token>/sse
```
获取方式：https://www.modelscope.cn/mcp/servers/@variflight-ai/variflight-mcp

### 小红书（攻略搜索）

```bash
# 启动 Docker 服务
docker run -d --name xhs-mcp -p 18060:18060 \
  -v ${PWD}/xhs-data:/app/data xpzouying/xiaohongshu-mcp

# 首次扫码登录
docker exec -it xhs-mcp /app/login
```

```env
XHS_MCP_URL=http://localhost:18060/mcp
```

### 12306（火车查询）

支持对接社区 MCP Server [Joooook/12306-mcp](https://github.com/Joooook/12306-mcp)：

```bash
# 本地启动 12306 MCP Server
npx -y 12306-mcp --port 8088
```

```env
TRAIN12306_MCP_URL=http://127.0.0.1:8088/mcp
```

未配置时自动使用 mock 数据并跳转 12306 真实查询页面。


---

## 🎯 使用示例

| 场景 | 输入示例 | 说明 |
|------|----------|------|
| 模糊意图 | "想去成都玩" | interaction_agent 会主动澄清时间、预算 |
| 完整规划 | "5月1日到5月3日，预算3000，喜欢小众景点" | planning_agent 生成完整行程 |
| 附近推荐 | "现在突然想吃辣的，附近有什么？" | 点击定位按钮后，navigation_agent 基于坐标推荐 |
| 交通查询 | "查5月1日北京到成都的机票和高铁" | search_agent 查询并返回订票链接 |
| 偏好记忆 | "不吃香菜" / "我喜欢有泳池的酒店" | interaction_agent 自动保存长期偏好 |

---

## 🏗️ 架构说明

### Agent 编排流程

```
用户输入
   ↓
坐标/地址信息注入（如果有定位）
   ↓
Manager LLM 决策 → 选择 next_agent
   ↓
Agent 执行 → 调用 MCP 工具
   ↓
结果回传 Manager → 判断是否继续 / 结束
   ↓
SSE 流式推送给前端
```

### Agent 分工

- **interaction_agent** - 处理问候、闲聊、需求澄清、偏好保存
- **planning_agent** - 行程规划核心，整合小红书+高德+携程数据
- **navigation_agent** - 基于 GPS 的实时推荐与导航
- **search_agent** - 交通信息聚合（机票+火车+天气）
- **testing_agent** - 质检，确保回复完整、格式正确

---

## 📄 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/chat` | POST | SSE 流式对话 |
| `/api/memory/{uid}` | GET | 获取用户记忆 |
| `/api/memory/{uid}` | DELETE | 清空用户记忆 |
| `/api/reverse` | GET | 经纬度反查地址 |
| `/api/healthz` | GET | 健康检查 |
| `/` | GET | 前端页面 |

---

## 📝 注意事项

1. **用户区分** - 当前通过前端写死的 `user_id` 区分用户，未接入 OAuth
2. **流式粒度** - SSE 流式到 Agent 级别，Agent 内部回复不分 token 流出
3. **测试 Agent** - 仅做单轮 PASS/WARN 质检，不会自动重跑
4. **Mock 降级** - MCP 服务失败时自动降级，不会影响主流程

---

## 📜 License

MIT License
