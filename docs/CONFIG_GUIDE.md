# 配置指南

> 所有配置项均通过 `.env` 文件管理，复制 `.env.example` 后按需修改。
> **本项目默认使用 BaoStock + AkShare 双免费数据源，无需注册、无需任何 Token，安装即用。**

---

## 核心配置

### 数据模式

```ini
DATA_MODE=jnb
```

| 值 | 说明 | 依赖 |
|---|------|------|
| `jnb` | 接入真实行情数据（BaoStock + AkShare） | 无需任何 Token，`pip install baostock akshare` 即可 |
| `websearch` | 纯 LLM 对话模式，不走行情接口 | 无需任何数据源配置 |

---

## 数据源配置（仅 jnb 模式）

本项目默认使用 **BaoStock + AkShare** 双免费数据源，两者均无需注册、无需 Token，安装即用。

```bash
pip install baostock akshare
```

### 数据源优先级（auto 模式）

`modules/datasource.py` 的 `CompositeDataSource` 在 `auto` 模式下按以下优先级选源：

```
BaoStock（主力：日线/指数/股票列表/交易日历/基础指标 PE/PB/PS/换手率，无需注册）
  → AkShare（补充：资金流向/实时行情/涨跌停/龙虎榜，无需 Token）
  → bridge（HTTP 缓存代理，可选）
  → 本地数据库（SQLite / CockroachDB，离线兜底）
```

| 数据源 | 需要的配置 | 能力 |
|--------|-----------|------|
| BaoStock | 无需配置 | 日线、指数、股票列表、交易日历、PE/PB/PS/换手率 |
| AkShare | 无需配置 | 资金流向、实时行情、涨跌停、龙虎榜 |
| bridge（可选） | `TUSHARE_BRIDGE_*`（见下） | HTTP 缓存代理，自定义数据桥接 |

> K 线读取统一走 **DB 优先** 策略：先查本地 `daily_kline` 表，DB 没有时才调 API 并写回缓存。即使处于降级路径，工具也**不会编造价格或信号**。

### bridge 缓存代理（可选，非必需）

```ini
# TUSHARE_BRIDGE_ENABLED=auto        # auto / always / never
# TUSHARE_BRIDGE_HOST=http://localhost:xxxx
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `TUSHARE_BRIDGE_ENABLED` | `auto` | `auto`（可用时启用）/ `always`（强制）/ `never`（禁用） |
| `TUSHARE_BRIDGE_HOST` | 无 | tushare-data-bridge HTTP 缓存代理地址 |

---

## LLM 配置（可选）

```ini
LLM_API_KEY=你的API密钥
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `LLM_API_KEY` | **否** | 未配置时，系统只做意图识别+知识库检索，不生成回答 |
| `LLM_BASE_URL` | 否（有 Key 时填） | OpenAI 兼容格式的 API 地址 |
| `LLM_MODEL` | 否（有 Key 时填） | 模型名称 |
| `ANTHROPIC_API_KEY` | 否 | 可选，Anthropic Claude API |

**支持的 LLM 提供商**：OpenAI 兼容格式的 API（OpenAI、MiniMax、OpenRouter、通义千问等）以及 Anthropic Claude。

---

## 向量知识库配置（可选，默认关闭）

```ini
# KB_ENABLED=true  # 取消注释以启用
# KB_API_URL=http://localhost:8000
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KB_ENABLED` | `false` | 设为 `true` 开启向量知识库检索 |
| `KB_API_URL` | `http://localhost:8000` | 知识库 API 地址（参考 knowledge-base 项目） |

**知识库依赖**：
- Qdrant 向量数据库（localhost:6333）
- Ollama Embedding 模型（localhost:11434）
- FastAPI 知识库服务（localhost:8000）

**未开启知识库时的行为**：
- 意图识别 ✅ 正常
- 角色框架 ✅ 正常（career/life 用本地 prompt 文件）
- LLM 生成 ✅ 正常（配置了 Key 的话）
- 知识库检索 ❌ 跳过（不影响其他功能）

---

## 数据库配置（双后端）

`modules/database.py` 是唯一数据访问入口，支持**双后端兼容**：

- **未设置 `CRDB_URL`** → SQLite（本地文件，默认 / 测试 / 离线回退）
- **设置 `CRDB_URL`** → CockroachDB（生产，psycopg2 驱动）

调用方代码统一使用 `?` 占位符与统一行访问，兼容层自动屏蔽两种后端的差异（占位符转换、DDL 转换、异常统一、行访问统一）。

### SQLite（默认）

```ini
DATA_DIR=data
DB_PATH=data/stock_data.db
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATA_DIR` | `data` | 数据目录 |
| `DB_PATH` | `data/stock_data.db` | SQLite 数据库路径，支持绝对/相对路径 |

### CockroachDB（生产，可选）

```ini
# CRDB_URL=postgresql://user:pass@host:26257/dbname?sslmode=verify-full
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CRDB_URL` | 空 | CockroachDB 连接串（PostgreSQL 协议）。设置后自动切换到 CockroachDB 后端；为空时走 SQLite |

> 启用 CockroachDB 需安装驱动：`pip install psycopg2-binary`（已列入 `requirements.txt` / `pyproject.toml`）。未设置 `CRDB_URL` 时该依赖不会被加载。

数据库表结构：15 张表 = 11 张核心表 + 4 张自我改进跟踪表，`init_database()` 会一次性创建全部表。

---

## 其他配置（可选）

```ini
# IM_PUSH_WEBHOOK=                    # 飞书 webhook 推送
# COMMENTARY_CACHE_TTL=3600          # 点评缓存 TTL
# SIMULATION_NARRATE_CACHE_TTL=3600  # 模拟叙述缓存 TTL
# ZETTARANC_ENV=/path/to/.env        # 自定义 .env 路径
# ZETTARANC_BACKTEST_IMPL=rust       # rust / python / auto（Rust 内核开关，v4.0.0+）
```

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `IM_PUSH_WEBHOOK` | 空 | 飞书 webhook，用于监控推送 |
| `ZETTARANC_BACKTEST_IMPL` | `rust` | `rust`（强制 Rust 内核）/ `python`（纯 Python）/ `auto`（优先 Rust，失败回退 Python） |

---

## 配置示例

### 最小配置（纯对话，无需任何外部服务）

```ini
DATA_MODE=websearch
```

### 股票分析模式（免费数据源，推荐）

```ini
DATA_MODE=jnb
# 无需任何 Token，pip install baostock akshare 即可
```

### 完整模式（股票 + LLM + 知识库）

```ini
DATA_MODE=jnb
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
KB_ENABLED=true
KB_API_URL=http://localhost:8000
```

### 生产模式（CockroachDB 后端）

```ini
DATA_MODE=jnb
CRDB_URL=postgresql://user:pass@host:26257/zettaranc?sslmode=verify-full
```
