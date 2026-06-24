# zettaranc-skill · Code Wiki

> **版本**：v3.1.1 ｜ **文档生成日期**：2026-06-24
> 本文档是对 zettaranc-skill 仓库的完整代码 Wiki，覆盖项目整体架构、各层模块职责、关键类与函数、依赖关系与运行方式。

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [目录结构总览](#3-目录结构总览)
4. [核心数据流](#4-核心数据流)
5. [LLM 角色层（SKILL.md）](#5-llm-角色层skillmd)
6. [Python 数据层（modules/）](#6-python-数据层modules)
   - 6.1 [基础设施层](#61-基础设施层)
   - 6.2 [指标计算引擎（indicators/）](#62-指标计算引擎indicators)
   - 6.3 [战法识别引擎（strategies/）](#63-战法识别引擎strategies)
   - 6.4 [达尔文自优化器（self_optimizer/）](#64-达尔文自优化器self_optimizer)
   - 6.5 [业务编排层](#65-业务编排层)
   - 6.6 [意图识别与 LLM 集成](#66-意图识别与-llm-集成)
   - 6.7 [自我改进闭环系统](#67-自我改进闭环系统)
7. [REST API 层（api/）](#7-rest-api-层api)
8. [前端 Web 看板（frontend/）](#8-前端-web-看板frontend)
9. [知识层（knowledge/ 与 rules/）](#9-知识层knowledge-与-rules)
10. [测试体系（tests/）](#10-测试体系tests)
11. [工具脚本（scripts/ 与 corpus/）](#11-工具脚本scripts-与-corpus)
12. [数据库架构](#12-数据库架构)
13. [依赖关系总览](#13-依赖关系总览)
14. [项目运行方式](#14-项目运行方式)
15. [CI/CD 与质量门](#15-cicd-与质量门)
16. [关键设计原则](#16-关键设计原则)

---

## 1. 项目概述

**zettaranc-skill** 是一个混合体项目：**AI Skill（思维框架蒸馏包）+ 真实数据量化工具**。

- **核心目标**：将 B 站 UP 主 / 前阳光私募冠军基金经理 zettaranc（万千）的投资思维框架、决策启发式和表达 DNA，封装为可供 Claude Code / Cursor 等 AI 工具调用的 Skill 文件（`SKILL.md`），同时提供基于真实 Tushare 行情数据的 Python 数据层支撑。
- **语料基础**：约 467 篇直播/付费课整理文章（~200 万字）+ 13 个 ztalk 视频 transcript（~12.7 万字）+ 9 篇交易心理系列（~3.3 万字）。
- **许可证**：MIT
- **版本**：v3.1.1（语义化版本：MAJOR 心智模型重构 / MINOR 新增模块 / PATCH 修复）

### 双模式架构

| 模式 | 环境变量 | 说明 |
|------|---------|------|
| **JNB 模式** | `DATA_MODE=jnb` | 接入 Tushare 真实行情，具备实时数据查询、技术指标计算、战法识别能力 |
| **普通小万** | `DATA_MODE=websearch` | 纯 LLM 对话，不走任何外部数据接口 |

### 六大核心能力

| 能力 | 说明 |
|------|------|
| 🎯 意图识别 | 自动识别 stock/career/life/chat 四种意图，路由到对应角色框架 |
| 📊 股票分析 | 60+ 技术指标实时计算，30+ 战法自动识别，支持 `--json` 输出 |
| 📈 策略回测 | 少妇战法六步闭环 / 多策略融合 / 组合回测 |
| 🔍 智能选股 | 曼城评分 + 蜈蚣图过滤 + 沙漏评分 + 牛绳判断 |
| 👁️ 观察池管理 | 自选股批量监控，每日信号扫描 + 报告生成 |
| 🤖 宿主集成 | 所有 CLI 命令支持 `--json`，宿主可直接调用获取结构化数据 |

---

## 2. 整体架构

项目采用**五层架构**，从底层数据源到顶层用户交互逐层抽象：

```
┌─────────────────────────────────────────────────────────────────┐
│  ⑤ 用户交互层                                                    │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐ │
│  │ CLI (zt 命令)     │  │ Web 看板 (React + FastAPI)           │ │
│  │ modules/cli.py    │  │ frontend/ + api/                     │ │
│  └──────────────────┘  └──────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  ④ LLM 角色层 (SKILL.md)                                         │
│  角色扮演协议 + 9 心智模型 + 44 决策启发式 + 表达 DNA              │
├─────────────────────────────────────────────────────────────────┤
│  ③ 业务编排层 (modules/)                                         │
│  screener / backtest / loop_engine / portfolio_diagnosis /       │
│  watchlist / trade_manager / intent_router / monitor             │
├─────────────────────────────────────────────────────────────────┤
│  ② 计算引擎层 (modules/indicators + modules/strategies)          │
│  60+ 技术指标 + 30+ 战法识别 + 三波理论 + 麒麟会四阶段             │
├─────────────────────────────────────────────────────────────────┤
│  ① 数据层 (modules/database + tushare_client + data_sync)        │
│  SQLite (12 张表) + Tushare API + Bridge 降级网关                │
└─────────────────────────────────────────────────────────────────┘
```

### 关键架构特点

1. **数据准备与 LLM 分离**：Python 层只负责数据准备（指标计算、信号检测、报告生成），所有点评话术由 LLM 用 Z哥角色生成，避免"AI味"。
2. **双模式切换**：通过 `DATA_MODE` 环境变量在 JNB（真实数据）和 websearch（纯 LLM）模式间切换。
3. **降级网关**：`bridge_client.py` 实现 bridge 优先、本地 SQLite 回退的降级策略。
4. **CLI 优先**：所有功能都可通过 `zt` 命令调用，支持 `--json` 输出供宿主解析。
5. **自我改进闭环**：跟踪 → 复盘 → 优化 → 应用，形成达尔文式参数进化系统。

---

## 3. 目录结构总览

```
zettaranc-skill/
├── SKILL.md                    # 核心 Skill 文件（LLM 角色扮演协议）
├── README.md                   # 项目介绍
├── AGENTS.md                   # AI Agent 开发指南
├── pyproject.toml              # 包定义 + zt/zt-web/zt-monitor 命令入口
├── requirements.txt            # Python 依赖
├── .env.example                # 环境变量模板
│
├── modules/                    # Python 数据层（核心代码）
│   ├── __init__.py             # 包导出 + dotenv 统一加载
│   ├── database.py             # SQLite 管理（12 张表）
│   ├── tushare_client.py       # Tushare API 封装
│   ├── data_sync.py            # 数据同步器
│   ├── bridge_client.py        # Bridge 降级网关
│   ├── cli.py / cli_commands.py# CLI 命令入口
│   ├── screener.py             # 选股评分体系
│   ├── backtest.py             # 通用回测框架
│   ├── backtest_six_step.py    # 少妇战法六步闭环回测
│   ├── loop_engine.py          # 六步闭环状态机
│   ├── portfolio_diagnosis.py  # 持股诊断
│   ├── watchlist.py            # 自选股观察池
│   ├── trade_parser.py         # 口语化输入解析
│   ├── trade_manager.py        # 交易记录 CRUD
│   ├── trade_reviewer.py       # 交割单数据准备层
│   ├── intent_router.py        # 意图识别与路由
│   ├── intent_chat.py          # LLM 聊天接口
│   ├── knowledge_retriever.py  # RAG 知识检索
│   ├── llm_providers.py        # LLM 提供者抽象
│   ├── commentary_service.py   # Z哥点评服务
│   ├── report.py               # 量化评估报告
│   ├── monitor.py              # 自选股监控
│   ├── notifier.py             # 通知推送
│   ├── setup_wizard.py         # 初始化向导
│   ├── review_generator.py     # 复盘报告生成
│   ├── harness_updater.py      # Guardrails 更新
│   ├── improvement_logger.py   # 改进日志（JSONL）
│   ├── tracking_manager.py     # 跟踪池管理
│   ├── tracking_syncer.py      # 跟踪数据同步
│   ├── tracking_tables.sql     # 跟踪表 SQL
│   ├── indicators/             # 技术指标引擎（60+ 指标）
│   ├── strategies/             # 战法识别引擎（30+ 战法）
│   └── self_optimizer/         # 达尔文自优化器
│
├── api/                        # FastAPI REST 适配层
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置（pydantic-settings）
│   ├── models/                 # Pydantic 数据模型（8 个文件）
│   ├── routes/                 # 路由处理（8 个文件）
│   ├── services/               # 业务服务层（6 个文件）
│   └── utils/serializers.py    # 序列化工具
│
├── frontend/                   # React Web 看板
│   ├── package.json            # React 19 + Vite 8 + TS 6
│   ├── vite.config.ts          # Vite 配置（代理 /api → 8000）
│   └── src/
│       ├── api/                # API 客户端（7 个域模块）
│       ├── pages/              # 7 个页面组件
│       ├── components/         # 组件（charts/layout/stock/ui）
│       ├── stores/appStore.ts  # zustand 全局状态
│       ├── hooks/              # React Query Hooks
│       └── lib/                # 工具库（constants/formatters/hooks）
│
├── knowledge/                  # 知识文档（20+ 篇交易体系）
├── rules/                      # 意图识别规则与角色框架
├── tests/                      # 单元测试（pytest，36 个文件）
├── scripts/                    # 工具脚本（薄壳）
├── corpus/                     # 语料采集与质检工具
├── references/research/        # 11 份调研提炼文件
└── data/                       # SQLite 数据库（不入库）
```

---

## 4. 核心数据流

### 4.1 宿主调用数据流

```
用户输入 → 宿主(Claude Code/Cursor) → 调用 CLI 工具(zt analyze/screen/backtest --json)
                                            ↓
                                    Python 层执行真实计算
                                            ↓
                                    JSON 结构化数据返回宿主
                                            ↓
                                    宿主用 Z哥口吻包装回复
```

### 4.2 数据同步与计算流

```
Tushare API → data_sync → SQLite → indicators/ → strategies/ → backtest/
                                              ↓
                                    screener（蜈蚣图/沙漏/牛绳过滤）
                                              ↓
                                    loop_engine（少妇六步闭环）
                                              ↓
                                    SKILL.md (LLM 角色层 + 工具描述)
```

### 4.3 Web 看板数据流

```
React 组件 → api 模块(axios) → Vite proxy(/api → 8000) → FastAPI route
                                                            ↓
                                                         service 层
                                                            ↓
                                                      modules 数据层
                                                            ↓
                                                   SQLite / Tushare
```

### 4.4 自我改进闭环

```
tracking_manager（跟踪池）→ tracking_syncer（同步数据）
        ↓
review_generator（月度复盘）→ harness_updater（Guardrails 建议）
        ↓
self_optimizer（参数优化：mutate → backtest score → ratchet）
        ↓
improvement_logger（JSONL 日志记录）
```

---

## 5. LLM 角色层（SKILL.md）

[SKILL.md](file:///workspace/SKILL.md) 是项目的核心交付物——一个可直接被 AI 工具加载的角色扮演协议。

### 5.1 文件结构（Skill-Schema-V2）

| 章节 | 职责 |
|------|------|
| **路由声明（Routing Surface）** | 定义何时加载/不加载本 Skill，触发条件与优先级 |
| **契约（Contract Surface）** | 输入契约（用户问题/股票代码/K线数据/交易记录）、输出契约（评分/战法/风险/操作建议）、边界与限制 |
| **运行时资源索引** | 按需加载的运行时资源清单 |
| **安全边界** | 免责声明、版权边界、敏感信息处理 |
| **角色规则** | Z哥口吻、表达 DNA、风格验证清单 |
| **可用工具** | CLI 工具描述与调用示例 |
| **回答工作流** | 多轮问诊系统、复盘流程 |

### 5.2 核心内容

- **9 个核心心智模型**：四层交易结构、少妇战法、双线战法、麒麟会、三波理论、呼吸理论、铁蝴蝶、四块砖、关键K
- **44 条决策启发式**：覆盖进场/出场/仓位/风险/心态
- **表达 DNA**：长铺垫+短结论、设问自答、死规矩体、算账句、用「我」而非「Z哥认为」
- **诚实边界**：标注公开表达与真实想法的差异

### 5.3 加载顺序

```
路由 → 契约 → 运行时索引 → 安全边界 → 首次对话 → 角色规则 → 可用工具 → 回答工作流
```

---

## 6. Python 数据层（modules/）

### 6.1 基础设施层

#### [modules/__init__.py](file:///workspace/modules/__init__.py)

**职责**：包导出和初始化，统一加载 `.env` 环境变量。

**关键函数**：
- `get_data_mode() -> str`：返回当前数据模式（jnb/websearch）
- `get_project_root() -> Path`：返回项目根目录

**设计要点**：单一加载点原则——在包首次 import 时一次性加载 `.env`，子模块不再重复加载，避免环境变量竞争。

---

#### [modules/database.py](file:///workspace/modules/database.py)

**职责**：SQLite 数据库管理，定义 12 张表（8 张核心 + 4 张 `_self` 后缀的自我改进表），提供连接上下文管理器和 CRUD 函数。

**关键类与函数**：
- `@dataclass TradeRecord`：交易记录数据类
- `@dataclass StockInfo`：股票信息数据类
- `get_db_path() -> Path`：从环境变量读取 DB 路径
- `get_db_connection() -> sqlite3.Connection`：返回开启 WAL 模式的连接
- `get_connection()`：上下文管理器（自动 commit/rollback）
- `init_database() -> None`：创建所有表 + 索引
- `init_tracking_tables() -> None`：创建 4 张 `_self` 表
- CRUD 函数：`add_to_watchlist` / `remove_from_watchlist` / `list_watchlist` / `add_trade` / `get_recent_trades` / `record_llm_response` 等

**设计要点**：
- **WAL 模式**：连接时自动 `PRAGMA journal_mode=WAL`，提升并发读性能
- **上下文管理器模式**：`get_connection()` 自动处理事务，异常时 rollback
- **幂等性**：所有 CREATE TABLE 使用 `IF NOT EXISTS`
- **复合索引**：每张表均建立 `(ts_code, trade_date DESC)` 复合索引

---

#### [modules/tushare_client.py](file:///workspace/modules/tushare_client.py)

**职责**：封装 Tushare 中转 SDK，提供日线、资金流向、财务数据、涨跌停列表等 API 调用，内置限流和重试机制。

**关键类**：
- `class TushareClient`：
  - `__init__(token: str, api_url: str = "")`
  - `_rate_limit() -> None`：120 次/分钟限流
  - `_call_api_with_retry(api_name: str, **kwargs) -> pd.DataFrame`：带重试的 API 调用
  - `get_daily(ts_code, start_date, end_date) -> pd.DataFrame`
  - `get_moneyflow(ts_code, start_date, end_date) -> pd.DataFrame`
  - `get_stock_basic() -> pd.DataFrame`
  - `get_financial_data(ts_code, period) -> pd.DataFrame`
  - `check_connection() -> bool`

**设计要点**：
- **中转 URL 支持**：通过 `TUSHARE_API_URL` 环境变量配置，代码中不硬编码内部域名
- **限流控制**：所有 API 调用必须经过 `_rate_limit()`
- **错误处理**：API 失败时返回空 DataFrame/None 而非抛异常中断

---

#### [modules/data_sync.py](file:///workspace/modules/data_sync.py)

**职责**：Tushare 数据同步器，支持增量/全量同步，将数据写入 SQLite，并计算技术指标缓存。

**关键类与函数**：
- `class _RateLimiter`：多进程安全限流器（`multiprocessing.Lock` + 滑动窗口 token bucket）
- `class DataSyncer`：
  - `sync_stock_basic() -> int`
  - `sync_daily_kline(ts_code, days=365) -> int`
  - `sync_missing(ts_code) -> int`：增量同步缺失日期
  - `sync_indicator_cache(ts_code, days=365) -> int`
  - `sync_daily_and_compute(ts_code, days=365) -> dict`：一站式同步+计算
  - `sync_stk_factor(ts_code, days=365) -> int`：Tushare 官方指标（diff 验证）
  - `get_sync_status() -> dict`

**设计要点**：
- **多进程安全限流**：`_RateLimiter` 使用 `multiprocessing.Lock`
- **懒加载**：`_get_indicator_funcs()` 首次调用时才加载指标函数，避免循环导入
- **增量同步**：通过 `sync_log` 表判断缺失日期
- **diff 验证**：`sync_stk_factor` 同步官方指标用于对比验证

---

#### [modules/bridge_client.py](file:///workspace/modules/bridge_client.py)

**职责**：Tushare Data Bridge 客户端，封装 bridge HTTP API，提供降级网关：bridge 不通时回退到本地 SQLite。

**关键类与函数**：
- `@dataclass(frozen=True) BridgeConfig`：Bridge 连接配置（host/port/timeout/enabled），`base_url` property
- `get_bridge_config() -> BridgeConfig`
- `set_bridge_config(**kwargs) -> None`：动态更新配置
- `is_bridge_available() -> bool`：健康检查
- `get_daily_klines(ts_code, days, start_date, end_date) -> list[dict]`：降级网关
- `get_all_stocks_bridge_first(exchange) -> list[dict]`：降级网关

**设计要点**：
- **frozen dataclass**：保证配置不可变
- **三种启用模式**：`auto`（默认，health 检查）/`always`（强制）/`never`（禁用）
- **延迟导入**：`_get_local_daily` 内部延迟导入 `modules.database`，避免循环依赖
- **统一升序**：所有日线数据返回时按 `trade_date` 升序排列

---

### 6.2 指标计算引擎（indicators/）

[modules/indicators/](file:///workspace/modules/indicators/) 是技术指标计算的核心，提供 60+ 指标，采用管道模式编排。

#### [indicators/core.py](file:///workspace/modules/indicators/core.py)

**职责**：定义基础类型、数学工具函数和通达信标准核心指标计算。

**关键类与函数**：
- `class TradeSignal(Enum)`：B1/B2/B3/SB1/S1/S2/HOLD/WATCH
- `@dataclass DailyData`：单日行情数据类（含 OHLCV、形态字段、KDJ/MACD/BBI 扩展字段），支持字典式访问
- `@dataclass IndicatorResult`：约 80 个字段的指标结果聚合体
- 数学工具：`calculate_ma` / `calculate_ema` / `calculate_sma_td`（通达信 SMA）/ `calculate_sma_series` / `calculate_slope`
- 核心指标：
  - `calculate_kdj(klines, period=9, k_ma=3, d_ma=3) -> tuple[float, float, float]`
  - `precompute_kdj_sequence(klines, period=9) -> list[tuple]`：Pandas 向量化 O(n)
  - `calculate_macd(klines, fast=12, slow=26, signal=9) -> tuple[list, list, list]`
  - `calculate_bbi(klines) -> float`
  - `calculate_rsi(klines, period=14) -> float` / `calculate_rsi_multi(klines) -> tuple`
  - `calculate_wr(klines, period=14) -> float` / `calculate_wr_multi(klines) -> tuple`
  - `calculate_bollinger(klines, period=20, std_dev=2.0) -> tuple`
  - `calculate_vol_ratio(klines, period=5) -> float`
  - `detect_macd_trap(dif_list, dea_list) -> dict[str, bool]`：金叉空/死叉多

**提供的指标清单**：MA、EMA、SMA(通达信)、SLOPE、KDJ、MACD、BBI、RSI(6/12/24)、WR(5/10)、Bollinger Bands、量比、MACD 陷阱

---

#### [indicators/data_layer.py](file:///workspace/modules/indicators/data_layer.py)

**职责**：数据接入层 + 内存/SQLite 双层缓存 + 指标计算管道编排 + 砖型图可视化 + 结果格式化。是 `analyze_stock()` 的核心实现位置。

**关键函数**：
- `_load_indicator_cache(ts_code, trade_date) -> IndicatorResult | None`：内存→DB
- `_save_indicator_cache(result, klines) -> bool`
- `clear_indicator_memory_cache()`
- `get_kline_data(ts_code, days=100) -> list[DailyData]`
- `analyze_stock(ts_code, days=100) -> IndicatorResult`：**管道模式主入口**
- `visualize_brick_chart(klines, lookback=20) -> str`：文本砖型图
- `format_result(result) -> str`：人类可读报告

**30 步管道**（`_PIPELINE`）：KDJ → MACD → BBI → 均线 → RSI → WR → 布林带 → 量比 → 双线 → 单针20 → 单针30 → 砖型图 → 前高前低 → DMI → 量价形态 → B1 → B2 → 关键K → 暴力K → 两个30 → 娜娜 → 黄金碗 → 呼吸 → SB1 → SB1详细 → 双枪 → 异动 → B3 → 四块砖 → 卖出评分

**设计要点**：每步含最小 K 线数阈值，不足则跳过；内存缓存 + DB 缓存双层。

---

#### [indicators/volume_patterns.py](file:///workspace/modules/indicators/volume_patterns.py)

**职责**：量价模式检测——异动选股、防卖飞评分、交易信号集成、主力出货五式、量比战法引擎。

**关键函数**：
- `detect_volume_anomaly(klines) -> dict`：异动选股（詹姆斯级/徐杰级）
- `calculate_sell_score(klines) -> tuple[int, str, dict[str, bool]]`：防卖飞 V1.4 五分制
- `detect_trade_signal(klines) -> TradeSignal`：集成 MACD 一票否决
- `detect_chuhuo_wushi(klines) -> dict`：主力出货五式
- `detect_volume_ratio_strategy(klines) -> dict`：量比战法引擎（7 种场景）
- `detect_volume_attack(klines) -> dict`：量比攻击信号

---

#### [indicators/wave_theory.py](file:///workspace/modules/indicators/wave_theory.py)

**职责**：三波理论识别——建仓波 → 拉升波 → 冲刺波阶段判断。

**关键函数**：
- `detect_three_waves(klines) -> dict`：返回 wave/confidence/stats/b1_suggestion
- `classify_wave_for_b1(klines) -> str`：简化接口（可干/等回调/不看/观望）

---

#### [indicators/kirin_detector.py](file:///workspace/modules/indicators/kirin_detector.py)

**职责**：麒麟会（庄家）四阶段状态机识别——吸筹 → 拉升 → 派发 → 回落，含铁蝴蝶/学院派铁蝴蝶子类型。

**关键函数**：
- `detect_kirin_stage(klines) -> dict`：返回 stage/confidence/sub_type/scores/indicators/operation
- 辅助函数：`_calculate_red_green_ratio` / `_detect_n_shape_raise` / `_detect_healthy_breathing` / `_calculate_position_ratio` / `_calculate_pull_speed`

---

#### [indicators/price_patterns/](file:///workspace/modules/indicators/price_patterns/) 子目录

7 个子模块，提供 33 个价格形态函数：

| 文件 | 职责 | 关键函数 |
|------|------|---------|
| [base.py](file:///workspace/modules/indicators/price_patterns/base.py) | 双线战法、RSL、单针、DMI | `calculate_zg_white` / `calculate_dg_yellow` / `detect_double_line_cross` / `detect_needle_20` / `detect_needle_30` / `calculate_dmi` |
| [brick.py](file:///workspace/modules/indicators/price_patterns/brick.py) | 砖型图系统 | `calculate_brick_value` / `calculate_brick_history` / `detect_brick_trend` / `detect_four_brick_system` |
| [bull_rope.py](file:///workspace/modules/indicators/price_patterns/bull_rope.py) | 牛绳理论 | `detect_bull_rope(klines) -> dict` |
| [complex_patterns.py](file:///workspace/modules/indicators/price_patterns/complex_patterns.py) | 复合高级形态 | `detect_divergence` / `detect_macd_signals` / `detect_double_gun` / `detect_sb1_detailed` / `detect_nana_chart` / `detect_golden_bowl` / `detect_breathing_structure` / `detect_b3` / `detect_zaihou_chongjian` / `detect_yueyueyushi` |
| [key_candles.py](file:///workspace/modules/indicators/price_patterns/key_candles.py) | 关键 K 线理论 | `detect_key_k` / `detect_violence_k` / `detect_key_candle` / `detect_key_candle_coverage` / `detect_abc_stages` |
| [sandglass.py](file:///workspace/modules/indicators/price_patterns/sandglass.py) | 沙漏评分 V9 | `calculate_sandglass_score(klines) -> dict`（五因子：缩量收敛/枢轴邻近/量能斜率/均线结构/事件风险） |
| [screener_helper.py](file:///workspace/modules/indicators/price_patterns/screener_helper.py) | 选股辅助形态 | `detect_fanbao` / `detect_volume_pattern` / `detect_didi` / `calculate_zuchong_target` / `detect_b1_today` / `detect_b2_today` / `check_two_30_rule` / `detect_centipede_pattern` |

---

### 6.3 战法识别引擎（strategies/）

[modules/strategies/](file:///workspace/modules/strategies/) 提供 30+ 战法识别，采用注册表 + 编排器模式。

#### [strategies/core.py](file:///workspace/modules/strategies/core.py)

**职责**：战法核心类型定义 + K线数据获取（联表查询）+ DailyData 转换 + KDJ/BBI/MACD 缓存式获取。

**关键类**：
- `class StrategyType(Enum)`：B1/B2/B3/SB1/长安战法/四分之三阴量/娜娜图形/超级B1/异动+地量地价/平行重炮/坑里起好货/对称VA/S1/S2/S3/吸筹/拉升/派发/回落/观察/四块砖翻绿/四块砖减仓/四块砖反弹
- `class Priority(Enum)`：CRITICAL(3)/OPPORTUNITY(2)/OBSERVE(1)
- `class Action(Enum)`：BUY/SELL/HOLD/WATCH
- `@dataclass StrategySignal`：ts_code/trade_date/strategy/confidence/description/details/action/target_price/stop_loss/risk_ratio/price/reason/priority

**关键函数**：
- `get_kline_data(ts_code, days=120) -> list[dict]`：联表查询 daily_kline + indicator_cache + moneyflow
- `_ensure_daily_klines(klines) -> list[DailyData]`：自动 dict→DailyData 转换
- `_get_kdj(klines, index) -> tuple` / `_get_bbi(klines, index) -> float` / `_get_macd_dif(klines, index) -> float`：属性优先，无则动态计算并缓存到 DailyData（O(1)）

---

#### [strategies/__init__.py](file:///workspace/modules/strategies/__init__.py)

**职责**：战法包聚合导出 + 全量战法检测编排器。

**关键函数**：
- `detect_all_strategies(ts_code, days=120) -> list[StrategySignal]`：**全量战法检测主入口**
- `get_latest_signal(ts_code, days=120) -> StrategySignal | None`
- `analyze_with_strategies(ts_code, days=120) -> dict[str, Any]`：综合战法分析
- `_post_process_signals(signals) -> list[StrategySignal]`：去重 + 排序 + 截断

**编排的战法清单**（18 类逐日检测 + P1/P2 全局检测）：
- 逐日：B1、B2、B3、SB1、长安战法、四分之三阴量、娜娜图形、异动+地量地价、平行重炮、坑里起好货、对称VA、S1、S2、S3、砖形图信号、买盘枯竭、绿肥红瘦出货、阶梯放量下跌、顶部大风车
- P1 全局（最新日）：滴滴战法、MACD金叉空/死叉多、主力出货五式、量比攻击、灾后重建、跃跃欲试、关键K
- P2 全局：三波理论、麒麟会四阶段

---

#### [strategies/base_strategies.py](file:///workspace/modules/strategies/base_strategies.py)

**职责**：基础战法 B1/B2/B3/SB1 检测，已升级 MDC 多维验证 + 麒麟阶段背景 + self_optimizer 参数可覆盖。

**关键函数**：
- `detect_b1(klines, index, kirin_context=None) -> StrategySignal | None`：J<j_threshold(默认-10) + 非绿砖 + MDC 加分（麒麟吸筹+20%/回落+10%/派发-30%、布林下轨+15%、主力净流入+10%、RSI6<25+5%、ADX>40+10%）
- `detect_b2(klines, index, kirin_context=None) -> StrategySignal | None`：前有B1 + 放量长阳 + J拐头 + MDC 加分
- `detect_b3(klines, index) -> StrategySignal | None`：B2后 + 小阳线 + 振幅<7%
- `detect_sb1(klines, index) -> StrategySignal | None`：前2天放量下跌 + 今日缩量企稳 + J<j_negative_threshold

**参数化**：通过 `self_optimizer.param_registry.get_active_param` 读取可调参数（b1.j_threshold/rsi6_ceiling/adx_floor/green_brick_limit、b2.min_pct、sb1.j_negative_threshold）。

---

#### [strategies/compound_strategies.py](file:///workspace/modules/strategies/compound_strategies.py)

**职责**：复合战法检测——长安战法、四分之三阴量、娜娜图形、异动+地量地价、平行重炮、坑里起好货、对称VA。

**关键函数**：
- `detect_changan(klines, index, kirin_context=None)`：三日确认（B1→放量长阳→分歧转一致缩半量）
- `detect_sifen_zhiyi_sanyin(klines, index)`：大阳后阴量>阳量75% = 假突破
- `detect_nana(klines, index, kirin_context=None)`：连续放量涨+无巨量阴+缩量回调+J负值
- `detect_yidong_dilian(klines, index)`：异动→缩量回调→地量买点
- `detect_pinghang(klines, index)`：平行重炮（两根放量阳夹阴）
- `detect_kengqi(klines, index)`：坑里起好货（挖坑+填坑+祖冲之目标价 2a-b）
- `detect_duichen_va(klines, index)`：对称VA（多空守恒，时间/空间对称）

---

#### [strategies/sell_signals.py](file:///workspace/modules/strategies/sell_signals.py)

**职责**：卖出/逃顶信号检测——S1/S2/S3 逃顶体系 + 砖形图信号 + 买盘枯竭 + 绿肥红瘦 + 阶梯放量下跌 + 顶部大风车。

**关键函数**：
- `detect_s1(klines, index, kirin_context=None)`：丑陋大绿帽 + MDC（派发+25%、出货五式共振+25%）
- `detect_s2(klines, index, dif_list=None)`：MACD顶背离 + 出货五式共振+15%
- `detect_s3(klines, index)`：最后逃生（S1后反弹量能不足）
- `detect_brick_signals(klines, index)`：四块砖状态变化点
- `detect_buy_exhaustion(klines, index)`：买盘枯竭
- `detect_green_fat_red_thin(klines, index)`：绿肥红瘦
- `detect_staircase_distribution(klines, index)`：阶梯放量下跌
- `detect_top_pinwheel(klines, index)`：顶部大风车

---

#### [strategies/vectorized.py](file:///workspace/modules/strategies/vectorized.py)

**职责**：Pandas/Numpy 向量化战法检测——B1/B2/B3/S1/S2 的批量向量化实现，用于全量 DataFrame 高速信号生成。

**关键函数**：
- `detect_b1_vec(df: pd.DataFrame) -> pd.Series`
- `detect_b2_vec(df) -> pd.Series`
- `detect_s1_vec(df) -> pd.Series`
- `detect_b3_vec(df) -> pd.Series`
- `detect_s2_vec(df) -> pd.Series`
- `generate_signals_from_df(df) -> list[StrategySignal]`

---

### 6.4 达尔文自优化器（self_optimizer/）

[modules/self_optimizer/](file:///workspace/modules/self_optimizer/) 是参数进化系统，通过 mutate → backtest score → ratchet 实现策略参数自动优化。

#### 架构

```
SelfOptimizer (编排入口)
    ├── phase1_baseline.py    # Phase 1: 基线评分（从 monthly_reviews_self 读数据）
    ├── phase2_hillclimb.py   # Phase 2: 爬山迭代（mutate → blacklist → score → ratchet）
    │       ├── mutator.py            # 参数变异引擎（step/random/jitter）
    │       ├── backtest_scorer.py    # 基于真实回测的评分（40%胜率+20%盈亏比+25%收益+15%回撤）
    │       └── reflex_blacklist.py   # 8 条反例安全网（强制 revert）
    └── phase3_report.py      # Phase 3: 汇总报告（results.tsv + optimization_drafts/ + improvement_log.jsonl）
```

#### [self_optimizer/param_registry.py](file:///workspace/modules/self_optimizer/param_registry.py)

**职责**：可进化参数清单注册表，定义整个系统中可被 self-optimizer 变异、回测、择优的数值参数。

**关键类与函数**：
- `@dataclass(frozen=True) ParamSpec`：name/default/min/max/step/category/description/impact/wired
- `@dataclass(frozen=True) StrategyParamGroup`：strategy_name/display_name/description/params
- `get_registry() -> dict[str, StrategyParamGroup]`
- `get_defaults() -> dict[str, dict[str, float | int]]`
- `get_active_param(strategy, name, default=None) -> Any`：策略函数读取参数（优先 override）
- `@contextlib.contextmanager using_params(params)`：临时覆盖参数上下文管理器

**注册的参数组（11 组，约 30 个参数）**：
- `b1`：j_threshold(-10)/rsi6_ceiling(25)/adx_floor(40)/green_brick_limit(4)
- `sb1`：j_negative_threshold(-5)/n_type_gap_max(10)
- `b2`：min_pct(4.0)/volume_ratio_min(1.2)/j_ceiling(55)
- `stop_loss`：stop_loss_pct(7.0)/trailing_stop_activation(8.0)/trailing_stop_distance(4.0)
- `s1_exit`：volume_surge_ratio(1.5)/upper_shadow_body_ratio(2.0)
- `position`：single_position_pct(30.0)/max_concurrent_positions(3)/consecutive_loss_cooloff(3)
- `sandglass`：5 个权重 + perfect_threshold(80)
- `centipede`：centipede_threshold(60)/lookback_days(20)
- `macd`：fast_period(12)/slow_period(26)/signal_period(9)
- `kdj`：kdj_period(9)
- `dmi`：dmi_period(14)/adx_threshold(25)
- `bull_rope`：gap_important_pct(3.0)/bull_rope_ma_period(20)

---

#### [self_optimizer/mutator.py](file:///workspace/modules/self_optimizer/mutator.py)

**职责**：参数变异引擎。

**关键类与函数**：
- `MutationStrategy = Literal["step", "random", "jitter"]`
- `@dataclass MutationRecord`：strategy/param_name/old_value/new_value/delta_pct/mutation_type/description
- `class ParamMutator`：
  - `mutate_one(current_params, strategy="step", ...) -> tuple[dict, MutationRecord]`
  - `mutate_n(current_params, n=1, strategy="step", ...) -> tuple[dict, list[MutationRecord]]`
  - `reset_to_defaults() -> dict`

**变异策略**：
- `step`：沿随机方向走一步，碰边界回弹
- `random`：合法范围内完全随机采样
- `jitter`：步长范围内微小随机（±step*0.5）

---

#### [self_optimizer/backtest_scorer.py](file:///workspace/modules/self_optimizer/backtest_scorer.py)

**职责**：基于真实回测的参数评分引擎。

**关键类与函数**：
- `@dataclass StockScore`：ts_code/win_rate/sharpe_ratio/total_return/max_drawdown/total_trades/score
- `@dataclass ScoringResult`：scores 列表 + composite_score/stock_count/traded_count/summary
- `class BacktestScorer`：
  - `DEFAULT_POOL`：13 只默认股票
  - `score(params=None) -> ScoringResult`
  - `score_vs_baseline(params) -> tuple[ScoringResult, ScoringResult]`
  - `_compute_single_score(r: BacktestResult) -> float`：**40% 胜率 + 20% 盈亏比 + 25% 平均收益 + 15% 最大回撤**

**设计要点**：通过 `using_params()` 注入 override 参数，无需修改策略函数。

---

#### [self_optimizer/reflex_blacklist.py](file:///workspace/modules/self_optimizer/reflex_blacklist.py)

**职责**：交易反射黑名单——8 条反例检测，任何触发强制 `status=revert`，防止自我优化引入回归。

**8 条反例**：
1. 胜率<-10% 仍标 good
2. stock_count<5 强行评估
3. 回撤>20% 仍未标 risky
4. LLM judge 读 harness 自身输出（PR #13 教训）
5. 异常被 swallow 而非 raise
6. 单轮改 >2 个策略
7. dry-run 比例 >30%
8. real_weight<0.6

**关键函数**：`check_all(context: dict) -> list[Violation]`

---

### 6.5 业务编排层

#### [modules/cli.py](file:///workspace/modules/cli.py) 和 [modules/cli_commands.py](file:///workspace/modules/cli_commands.py)

**职责**：v2.10.0 统一 CLI 入口。

**cli.py 子命令**：`analyze` / `screen` / `score` / `workflow` / `watchlist` / `diagnose` / `sync` / `self_optimize` / `track`

**cli_commands.py 子命令**：`backtest` / `trade` / `daily` / `monitor`

**关键设计**：
- `STRATEGY_ALIAS`：中文别名映射（如 "B1" → "b1"）
- `_analyze_core(ts_code, days, ...)`：共享分析逻辑
- `cmd_daily`：五步工作流（自选股扫描 → 选股筛选 → 持股诊断 → 信号汇总 → 总结）

---

#### [modules/screener.py](file:///workspace/modules/screener.py)

**职责**：选股与择时评分体系，提供 14 种筛选条件，支持多进程并行扫描。

**关键内容**：
- `_CRITERIA_REGISTRY: dict[str, Callable]`：注册表
- `@_register(name: str)`：装饰器，注册筛选条件
- 14 个筛选函数：`b1` / `perfect` / `oversold` / `breakout` / `super_b1` / `changan` / `b2_breakout` / `b3_consensus` / `build_wave` / `xishou` / `safe` / `bull_rope` / `sandglass_perfect` / `volume_ratio_super`
- `@dataclass StockScore`：综合评分（total/b1_score/trend_score/volume_score/risk_score/rating/reasons/warnings）
- `analyze_stock(ts_code, days=60) -> StockScore`
- `screen_stocks(criteria, ..., parallel=True) -> list[StockScore]`：多进程扫描

**设计要点**：注册表模式替代 if-elif 链；`_analyze_worker` 必须是模块顶层函数（可 pickle）。

---

#### [modules/backtest.py](file:///workspace/modules/backtest.py) 和 [modules/backtest_six_step.py](file:///workspace/modules/backtest_six_step.py)

**backtest.py 职责**：通用策略回测框架。

**关键 dataclass**：
- `@dataclass Trade`：交易记录
- `@dataclass BacktestResult`：回测结果（trades/total_pnl/total_return/max_drawdown/win_rate/...）
- `@dataclass Position`：持仓状态
- `@dataclass PortfolioBacktestResult`：组合回测结果

**关键函数**：
- `backtest_signals(signals, klines, stop_loss=0.05, take_profit=0.15) -> BacktestResult`
- `backtest_strategy(strategy_func, klines, ...) -> BacktestResult`
- `backtest_multi_strategy(strategies, klines, ...) -> list[BacktestResult]`
- `backtest_portfolio(strategy_funcs, klines_dict, weights, ...) -> PortfolioBacktestResult`

**backtest_six_step.py 职责**：少妇战法六步闭环专用回测。

**关键内容**：
- `@dataclass ShaofuBacktestResult`：六步闭环回测结果
- `backtest_shaofu_single(ts_code, klines, config: LoopConfig) -> ShaofuBacktestResult`
- `backtest_shaofu_portfolio(ts_codes, klines_dict, config: LoopConfig) -> list[ShaofuBacktestResult]`
- `summary_text(result) -> str`

---

#### [modules/loop_engine.py](file:///workspace/modules/loop_engine.py)

**职责**：少妇战法六步闭环状态机引擎，实现择时→选股→等B1→持有→离场的完整闭环。

**关键内容**：
- `class LoopState(Enum)`：TIMING/SELECTING/WAITING_B1/HOLDING/EXITED
- `@dataclass LoopConfig`：闭环配置（stop_loss_pct/take_profit_pct/lu_zhu_threshold/...）
- `@dataclass LoopTrade`：闭环交易记录
- `class ShaofuLoopEngine`：
  - `check_entry(klines) -> bool`
  - `check_stop_loss(klines, position) -> bool`
  - `check_lu_zhu(klines, position) -> bool`
  - `check_white_line_exit(klines, position) -> bool`
  - `run_stock(ts_code, klines) -> list[LoopTrade]`：主循环
  - `process_day(state, kline, position) -> tuple[LoopState, LoopTrade | None]`

**设计要点**：状态机驱动；`_apply_exit_checks` 统一处理止损/露珠/白线离场。

---

#### [modules/portfolio_diagnosis.py](file:///workspace/modules/portfolio_diagnosis.py)

**职责**：持股诊断端到端，输出包含 20+ 字段的诊断报告。

**关键内容**：
- `@dataclass DiagnosisReport`：诊断报告（含 20+ 字段）
- `diagnose_stock(ts_code, days=60) -> DiagnosisReport`：主入口
- `format_report(report) -> str`：格式化输出

**诊断维度**：风险等级/趋势/价格位置/防卖飞/麒麟会/牛绳/蜈蚣图/沙漏/止损止盈等。

---

#### [modules/watchlist.py](file:///workspace/modules/watchlist.py)

**职责**：自选股观察池管理。

**关键内容**：
- `@dataclass WatchAlert`：观察警报
- `add_watch(ts_code, name, tags=None) -> bool`
- `remove_watch(ts_code) -> bool`
- `list_watch(tag=None) -> list[dict]`
- `scan_watchlist(days=60) -> list[WatchAlert]`：批量扫描信号
- `generate_daily_report() -> str`

**五类警报**：B1（买点）/B2（确认）/EXIT（离场）/BREAK（突破）/ABNORMAL（异动）

---

#### [modules/trade_parser.py](file:///workspace/modules/trade_parser.py) / [trade_manager.py](file:///workspace/modules/trade_manager.py) / [trade_reviewer.py](file:///workspace/modules/trade_reviewer.py)

**trade_parser.py 职责**：随堂测试解析器，支持口语化/JSON/CSV 多格式输入。

**关键内容**：
- `STOCK_NAME_MAP: dict[str, str]`：股票名称映射（如 "茅台" → "贵州茅台"）
- `class TradeParser`：
  - `parse(text) -> ParseResult`：主入口，自动识别格式
  - `_parse_natural(text) -> ParseResult`：口语化解析
  - `confirm_and_fill(parse_result) -> ParseResult`：交互式补全

**trade_manager.py 职责**：交易记录 CRUD、持仓计算、盈亏统计。

**关键内容**：
- `class TradeManager`：
  - `add_trade(trade_data) -> int`
  - `get_recent_trades(limit=10) -> list[dict]`
  - `get_summary() -> dict`：盈亏统计
  - `get_stock_holding(ts_code) -> dict`：持仓计算
  - `calculate_pnl(trades) -> dict`
- 全局实例：`trade_manager = TradeManager()`

**trade_reviewer.py 职责**：交割单数据准备层，将交易记录转换为 LLM 提示词。

**关键内容**：
- `JARGON_DICT: dict[str, str]`：黑话词典
- `@dataclass ReviewContext`：`to_llm_prompt()` / `get_full_prompt()` / `get_jargon_hint()`
- `class TradeReviewer`：`parse_input` / `prepare_review_context` / `enrich_with_indicators` / `save_trade`

---

### 6.6 意图识别与 LLM 集成

#### [modules/intent_router.py](file:///workspace/modules/intent_router.py)

**职责**：意图路由，规则匹配优先（< 1ms），LLM 兜底。

**关键内容**：
- `@dataclass RouterResult`：路由结果（intent/confidence/rule_matched/system_prompt/knowledge_context/matched_keywords）
- `class IntentRouter`：
  - `process(text) -> RouterResult`：主入口
  - `_rule_match(text) -> tuple[str, float, list[str]] | None`：规则匹配
  - `_build_system_prompt(intent, keywords) -> str`

**四意图**：stock（优先级10）/ career（5）/ life（3）/ chat（0），规则定义在 [rules/intent_rules.yaml](file:///workspace/rules/intent_rules.yaml)。

---

#### [modules/intent_chat.py](file:///workspace/modules/intent_chat.py)

**职责**：LLM 聊天接口。

**关键函数**：
- `get_llm() -> LLMProvider`
- `generate_reply(text, history=None) -> str`
- `chat_once(system_prompt, user_prompt) -> str`
- `chat_interactive() -> None`：交互式聊天

---

#### [modules/knowledge_retriever.py](file:///workspace/modules/knowledge_retriever.py)

**职责**：RAG 知识检索，按意图分类加权检索知识库。

**关键内容**：
- `@dataclass KnowledgeCard`：知识卡片（title/content/source/relevance_score）
- `class KnowledgeRetriever`：
  - `CATEGORY_FILTERS: dict[str, list[str]]`：意图分类映射
  - `retrieve(query, intent=None, top_k=5) -> list[KnowledgeCard]`

---

#### [modules/llm_providers.py](file:///workspace/modules/llm_providers.py)

**职责**：LLM 提供者抽象。

**关键类**：
- `class LLMProvider`：基类（`generate` / `generate_stream`）
- `class MiniMaxProvider(LLMProvider)`：使用 OpenAI 兼容接口

---

#### [modules/commentary_service.py](file:///workspace/modules/commentary_service.py)

**职责**：Z哥点评服务，基于 SKILL.md 和知识库，调用 LLM 生成 Z哥风格的股票分析点评。

**关键函数**：
- `generate_commentary(analysis: dict) -> dict`：主入口，含 LRU 缓存 + LLM 响应耗时记录

**设计要点**：
- **mtime 缓存**：通过比较文件 mtime 决定是否重新读取 SKILL.md
- **条件注入知识**：根据指标状态动态注入相关知识片段，限制总大小 3000 字节
- **LRU 缓存**：TTL 3600s，最大 100 条
- **LLM 响应耗时记录**：记录到 `llm_response_log` 表

---

### 6.7 自我改进闭环系统

#### [modules/review_generator.py](file:///workspace/modules/review_generator.py)

**职责**：自我改进系统的复盘报告生成模块，生成月度复盘报告。

**关键类**：
- `class ReviewGenerator`：
  - `generate_monthly_review(review_month) -> dict[str, Any]`：主入口
  - `_analyze_stock_performance(ts_code, review_month) -> dict | None`
  - `_analyze_strategy_performance(review_month) -> list[dict]`
  - `save_review_to_database(review_data) -> bool`
  - `get_historical_reviews(months=12) -> list[dict]`

**设计要点**：使用 `rules: list[tuple[bool, str]]` 规则表消除同构 if-else。

---

#### [modules/harness_updater.py](file:///workspace/modules/harness_updater.py)

**职责**：Harness 层集成模块，根据复盘结果自动更新 Guardrails（策略使用建议）。

**关键类**：
- `class HarnessUpdater`：
  - `analyze_strategy_performance(review_month=None) -> dict`
  - `generate_guardrails_update(analysis_result) -> dict`
  - `apply_guardrails_updates(updates) -> dict`：目前只打印，待人工审核
  - `run_harness_update(review_month=None) -> dict`

**策略状态分级**：poor（收益<-10%）/ risky（回撤>20%）/ good（收益>10% 且准确率>50%）/ normal

---

#### [modules/improvement_logger.py](file:///workspace/modules/improvement_logger.py)

**职责**：自我改进日志记录模块，记录所有自我改进的操作和结果到 JSONL 文件。

**关键类**：
- `class ImprovementLogger`：
  - `log(action, category, details, status="success", message="") -> bool`
  - `log_signal_detection(...)` / `log_review_generation(...)` / `log_harness_update(...)` / `log_optimization(...)`
  - `get_recent_logs(limit=100) -> list`
  - `get_improvement_summary() -> dict`

**分类体系**：`signal` / `review` / `harness` / `optimization` 四类。

---

#### [modules/tracking_manager.py](file:///workspace/modules/tracking_manager.py) 和 [modules/tracking_syncer.py](file:///workspace/modules/tracking_syncer.py)

**tracking_manager.py 职责**：跟踪池管理。

**关键类**：
- `class TrackingManager`：
  - `add_stock(ts_code, name, reason, strategy_tags, notes) -> bool`
  - `remove_stock(ts_code, reason=None) -> bool`：软删除（status='removed'）
  - `list_stocks(status="active", strategy_tag=None) -> list[dict]`
  - `get_tracking_stats() -> dict`
  - `get_strategy_distribution() -> dict[str, int]`

**tracking_syncer.py 职责**：跟踪数据同步，同步跟踪股票的 K 线、指标、信号数据到 `tracking_records_self` 表。

**关键类**：
- `class TrackingSyncer`：
  - `sync_daily(ts_code, days=365) -> dict`
  - `sync_all_active(days=365) -> dict`
  - `_detect_signal(indicator_data, kline_data, prev_kline_data) -> dict`：检测 B1/B2/B3/长安/MACD金叉/量比战法

---

#### [modules/monitor.py](file:///workspace/modules/monitor.py)

**职责**：自选股监控主入口，5 步流程。

**关键函数**：
- `run_watchlist_monitor() -> dict`：获取自选股 → 同步数据 → 扫描信号 → 生成报告 → 主动推送

---

#### [modules/notifier.py](file:///workspace/modules/notifier.py)

**职责**：通知模块，支持 macOS 系统通知和飞书 webhook 推送。

**关键函数**：
- `notify_macos(title, message, subtitle="") -> bool`
- `notify_feishu(webhook, title, content) -> bool`
- `notify_all(title, message) -> dict`：同时推送所有渠道

---

#### [modules/report.py](file:///workspace/modules/report.py)

**职责**：Z哥量化评估报告生成。

**关键内容**：
- `MACRO_SECTORS: dict[str, list[str]]`：板块分类
- `@dataclass StockAssessment`：单只股票评估结果
- `assess_watchlist() -> list[StockAssessment]`
- `render_assessment(assessments) -> str`
- `write_assessment(content, path=None) -> str`

---

#### [modules/setup_wizard.py](file:///workspace/modules/setup_wizard.py)

**职责**：初始化配置向导，支持 JNB/websearch 双模式切换、API 连通性测试。

**关键函数**：
- `check_env_exists() -> bool`
- `write_env_file(config: dict) -> None`
- `test_jnb_connection(token, api_url="") -> tuple[bool, str]`
- `run_wizard() -> None`：主入口

---

## 7. REST API 层（api/）

[api/](file:///workspace/api/) 是 FastAPI REST 适配层，采用经典三层分层：Routes → Services → Models。

### 7.1 入口与配置

#### [api/main.py](file:///workspace/api/main.py)

**职责**：FastAPI 应用入口。

**关键内容**：
- `app`：FastAPI 实例（title="Z哥量化 API", version="1.0.0"）
- `lifespan(app)`：异步上下文管理器
- `global_exception_handler(request, exc)`：全局异常兜底，返回 500 JSON
- `start_web()`：用 uvicorn 启动服务（供 `zt-web` 快捷指令调用）
- CORS 中间件 + 8 个路由模块挂载，统一前缀 `/api/v1`

#### [api/config.py](file:///workspace/api/config.py)

**职责**：API 全局配置中心。

**关键类**：
- `class Settings(BaseSettings)`：db_path / data_mode / cors_origins / api_port(8000) / api_prefix("/api/v1")
- `settings`：模块级单例

### 7.2 API 端点清单

| 路由模块 | 端点 | 方法 | 说明 |
|---------|------|------|------|
| **stock** | `/api/v1/stock/analyze/{ts_code}` | GET | 全量分析（指标+战法+评分+诊断） |
| | `/api/v1/stock/analyze/{ts_code}/klines` | GET | K线图表数据（ECharts 列式） |
| | `/api/v1/stock/analyze/{ts_code}/signals` | GET | 战法信号列表 |
| | `/api/v1/stock/score/{ts_code}` | GET | 综合评分 |
| **screen** | `/api/v1/screen/strategies` | GET | 列出所有选股策略 |
| | `/api/v1/screen/run` | POST | 执行选股筛选 |
| **watchlist** | `/api/v1/watchlist/` | GET | 列出自选股（支持 tags 过滤） |
| | `/api/v1/watchlist/` | POST | 添加自选股 |
| | `/api/v1/watchlist/{ts_code}` | DELETE | 移除自选股 |
| | `/api/v1/watchlist/scan` | POST | 扫描信号 |
| | `/api/v1/watchlist/report` | GET | 生成日报 |
| **diagnosis** | `/api/v1/diagnosis/{ts_code}` | GET | 持仓诊断 |
| **backtest** | `/api/v1/backtest/shaofu` | POST | 少妇战法单股回测 |
| | `/api/v1/backtest/multi` | POST | 多策略融合回测 |
| | `/api/v1/backtest/portfolio` | POST | 多股票组合回测 |
| **trade** | `/api/v1/trade/` | GET | 分页列出交易记录 |
| | `/api/v1/trade/parse` | POST | 解析口语化描述（不保存） |
| | `/api/v1/trade/` | POST | 解析并保存交易记录 |
| | `/api/v1/trade/{trade_id}` | PUT | 更新交易记录 |
| | `/api/v1/trade/{trade_id}` | DELETE | 删除交易记录 |
| | `/api/v1/trade/stats` | GET | 获取交易统计 |
| **system** | `/api/v1/system/health` | GET | 健康检查 |
| | `/api/v1/system/sync/status` | GET | 数据同步状态 |
| | `/api/v1/system/sync/{ts_code}` | POST | 触发单股数据同步 |
| **commentary** | `/api/v1/commentary/{ts_code}` | POST | 生成 Z哥风格点评（LLM） |

### 7.3 Services 层

| 服务 | 职责 | 关键函数 |
|------|------|---------|
| [stock_service.py](file:///workspace/api/services/stock_service.py) | 股票分析核心服务 | `get_full_analysis` / `get_kline_chart_data`（最复杂，手动计算全套指标时间序列）/ `get_signals` / `get_score` |
| [screen_service.py](file:///workspace/api/services/screen_service.py) | 选股筛选服务 | `get_strategies` / `run_screen`（含 11 个策略别名映射） |
| [watchlist_service.py](file:///workspace/api/services/watchlist_service.py) | 自选股管理服务 | `list_watchlist` / `add_to_watchlist` / `scan_watchlist` / `generate_report` |
| [diagnosis_service.py](file:///workspace/api/services/diagnosis_service.py) | 持股诊断服务 | `diagnose(ts_code, days)` |
| [backtest_service.py](file:///workspace/api/services/backtest_service.py) | 策略回测服务 | `run_shaofu` / `run_multi` / `run_portfolio` |
| [trade_service.py](file:///workspace/api/services/trade_service.py) | 交易记录服务 | `list_trades` / `parse_trade` / `add_trade` / `get_stats` |

**设计要点**：所有 service 对 `modules` 的依赖均为**延迟导入**（函数内 import），避免启动时加载重模块。

### 7.4 Models 层

8 个 Pydantic 模型文件，是前后端类型对齐的"单一真相源"：

| 文件 | 职责 |
|------|------|
| [common.py](file:///workspace/api/models/common.py) | 通用响应（ErrorResponse / StatusResponse） |
| [stock.py](file:///workspace/api/models/stock.py) | 股票分析最庞大模型（KDJDetail/MACDDetail/IndicatorDetail/StockAnalysisResponse/KlineChartResponse 等） |
| [screen.py](file:///workspace/api/models/screen.py) | 选股筛选（ScreenRequest/StockScoreItem/ScreenResponse） |
| [watchlist.py](file:///workspace/api/models/watchlist.py) | 自选股管理（WatchlistAddRequest/WatchlistScanResponse） |
| [diagnosis.py](file:///workspace/api/models/diagnosis.py) | 持仓诊断（DiagnosisResponse，30+ 字段） |
| [backtest.py](file:///workspace/api/models/backtest.py) | 回测（BacktestRequest/BacktestResponse/PortfolioBacktestResponse） |
| [trade.py](file:///workspace/api/models/trade.py) | 交易记录（TradeAddRequest/TradeRecordResponse/TradeStatsResponse） |
| [commentary.py](file:///workspace/api/models/commentary.py) | Z哥点评（CommentaryResponse） |

### 7.5 Utils

[api/utils/serializers.py](file:///workspace/api/utils/serializers.py)：dataclass → dict 序列化工具，处理 Enum、None、嵌套 dataclass 的递归转换。

---

## 8. 前端 Web 看板（frontend/）

[frontend/](file:///workspace/frontend/) 是 React 19 + Vite 8 + TypeScript 6 现代栈的 Web 看板。

### 8.1 技术栈

| 层级 | 技术 |
|------|------|
| 框架 | React 19 |
| 构建 | Vite 8 |
| 语言 | TypeScript 6 |
| 路由 | react-router-dom 7 |
| 数据请求 | @tanstack/react-query 5 + axios |
| 图表 | echarts 6 + echarts-for-react |
| 样式 | Tailwind CSS 4（暗色金融主题，金/红/绿配色，A 股红涨绿跌） |
| 状态 | zustand 5（persist 中间件） |

### 8.2 应用结构

```
main.tsx (挂载入口)
    └── App.tsx (路由 + QueryClient + ErrorBoundary + AppShell)
            ├── pages/ (7 个页面)
            │   ├── Dashboard.tsx          # 首页总览
            │   ├── StockAnalysis.tsx      # 单股分析（最复杂，lazy）
            │   ├── Screener.tsx           # 选股筛选
            │   ├── Watchlist.tsx          # 自选股管理
            │   ├── Backtest.tsx           # 策略回测（lazy）
            │   ├── Trades.tsx             # 交易记录
            │   └── Settings.tsx           # 系统设置
            ├── components/
            │   ├── charts/                # KlineChart / EquityCurveChart / RadarChart
            │   ├── layout/                # AppShell / Header / Sidebar
            │   ├── stock/                 # CommentaryCard / DiagnosisCard / IndicatorPanel / ScoreCard / SignalTimeline
            │   └── ui/                    # Card / Button / Badge / LoadingSpinner / ApiErrorState / ErrorBoundary
            ├── stores/appStore.ts         # zustand 全局 UI 状态
            ├── hooks/useStockAnalysis.ts  # React Query Hooks
            └── lib/                       # constants / formatters / hooks
```

### 8.3 关键组件

#### [KlineChart.tsx](file:///workspace/frontend/src/components/charts/KlineChart.tsx)

**职责**：核心 K 线图组件，ECharts 多 grid 布局。

**特点**：
- 6 个子图纵向排列（K线+叠加指标 / 成交量 / KDJ / MACD / 砖型图 / 呼吸波），共享 xAxis dataZoom
- K线主图叠加白线/黄线/BBI/布林带，含右侧点位标签
- 买卖信号 markPoint（三角形上下）
- **背景色块**：可切换"无背景/麒麟四阶段/主力三波理论"三种 markArea 模式
- 呼吸波分呼气（正分值，红色面积）/吸气（负分值，绿色面积）
- 红涨绿跌配色（A 股习惯）

#### [CommentaryCard.tsx](file:///workspace/frontend/src/components/stock/CommentaryCard.tsx)

**职责**：Z哥点评卡片，LLM 生成文本的富文本渲染。

**特点**：
- `extractKeyQuote(text)`：提取金句（优先双引号/「」，否则匹配关键词句）
- `splitIntoSections(text)`：按"1./2./3./4."编号切段
- `renderInline(text)`：数字渲染成 inline badge（价格→金色 ¥、指标小数→紫色、百分比→蓝色）
- 503（LLM 未配置）/502（LLM 失败）特殊错误态

### 8.4 数据层

- [api/client.ts](file:///workspace/frontend/src/api/client.ts)：axios 实例（baseURL=`/api/v1`、timeout=120000）
- [api/types.ts](file:///workspace/frontend/src/api/types.ts)：全部 TypeScript 类型定义，与后端 Pydantic 模型一一对应
- 7 个域 API 模块：stock / screen / watchlist / trade / backtest + client + types

### 8.5 状态管理

- **服务端状态**：TanStack Query（staleTime/gcTime 精细控制）
- **UI 状态**：zustand persist（localStorage 持久化 sidebarCollapsed 和 searchHistory）

### 8.6 路由策略

- 轻量页（Dashboard/Screener/Watchlist/Trades/Settings）：静态导入
- 重型页（StockAnalysis/Backtest，含 ECharts）：`lazy` 动态导入 + `Suspense` + `PageFallback`

### 8.7 全局特性

- ⌘K/Ctrl+K 快捷键聚焦搜索 + 搜索历史 + 6 位代码自动补全后缀
- 响应式侧栏（窄屏自动收起）
- ErrorBoundary 兜底 + ApiErrorState 统一错误态

---

## 9. 知识层（knowledge/ 与 rules/）

### 9.1 knowledge/ 知识文档

20+ 篇交易体系文档，是 RAG 检索的知识源：

| 文档 | 内容 |
|------|------|
| [trading-core.md](file:///workspace/knowledge/trading-core.md) | 四层交易结构、少妇战法 SOP、B1/B2/B3、量比战法 |
| [indicators.md](file:///workspace/knowledge/indicators.md) | MACD 一票否决、筹码理论、麒麟会、三波理论 |
| [sell-discipline.md](file:///workspace/knowledge/sell-discipline.md) | 防卖飞 V1.4、出货五式、S1/S2/S3 逃顶 |
| [position-management.md](file:///workspace/knowledge/position-management.md) | 仓位铁律、三层防火墙 |
| [market-macro.md](file:///workspace/knowledge/market-macro.md) | 周期思维、逆向操作、四年周期 |
| [portfolio-management.md](file:///workspace/knowledge/portfolio-management.md) | 新曼城 4231、ETF 躺平、ABC 建仓 |
| [trading-psychology.md](file:///workspace/knowledge/trading-psychology.md) | 交易免疫系统、斗牛士心法、散户魔咒 |
| [stock-glossary.md](file:///workspace/knowledge/stock-glossary.md) | 60+ 个股黑话/代号 |
| [trend-lines.md](file:///workspace/knowledge/trend-lines.md) | 双线战法、三道防线、牛绳理论 |
| [exit-strategies.md](file:///workspace/knowledge/exit-strategies.md) | S1/S2/S3 逃顶、摸顶税 |
| [key-candles.md](file:///workspace/knowledge/key-candles.md) | 关键 K 理论、6 种趋势转换 |
| [advanced-patterns.md](file:///workspace/knowledge/advanced-patterns.md) | 长安战法、平行重炮、对称 VA |
| [breathing-theory.md](file:///workspace/knowledge/breathing-theory.md) | 呼吸理论 |
| [three-best-principles.md](file:///workspace/knowledge/three-best-principles.md) | 三最原则 |
| [iron-butterfly.md](file:///workspace/knowledge/iron-butterfly.md) | 铁蝴蝶识别 |
| [four-rhythms.md](file:///workspace/knowledge/four-rhythms.md) | 四大节奏 |
| [six-tracks-2026.md](file:///workspace/knowledge/six-tracks-2026.md) | 2026 赛道 |
| [life-decision.md](file:///workspace/knowledge/life-decision.md) | 人生决策框架 |
| [career-development.md](file:///workspace/knowledge/career-development.md) | 职业发展框架 |
| [business-judgment.md](file:///workspace/knowledge/business-judgment.md) | 创业/商业判断框架 |
| [heuristics.md](file:///workspace/knowledge/heuristics.md) | 44 条决策启发式 |
| [data_dictionary.md](file:///workspace/knowledge/data_dictionary.md) | 输入数据字典 |
| [signal_dictionary.md](file:///workspace/knowledge/signal_dictionary.md) | 输出信号字典 |

### 9.2 rules/ 意图识别规则

| 文件 | 职责 |
|------|------|
| [intent_rules.yaml](file:///workspace/rules/intent_rules.yaml) | 意图匹配规则（keywords + patterns），四意图优先级 stock(10) > career(5) > life(3) > chat(0) |
| [career_prompt.md](file:///workspace/rules/career_prompt.md) | Z哥职业决策框架 |
| [life_prompt.md](file:///workspace/rules/life_prompt.md) | Z哥人生决策框架 |

---

## 10. 测试体系（tests/）

[tests/](file:///workspace/tests/) 使用 pytest 框架，36 个测试文件。

### 10.1 测试基础设施

[tests/conftest.py](file:///workspace/tests/conftest.py) 提供测试基础设施：

**Fixture**：
- `mock_env_for_tests`（autouse）：所有测试自动设置 mock 环境变量到临时目录
- `temp_db`：提供初始化好的临时数据库
- `db_conn`：提供数据库连接
- `state_with_interrupted_run`：自优化器中断恢复测试
- `mock_monthly_reviews_with_poor_strategy`：mock 复盘数据

**数据工厂函数**：
- `make_kline_row()`：生成单根 K 线数据（dict 格式）
- `make_daily_data()`：生成 DailyData 对象
- `generate_uptrend_klines(n=120, ...)`：生成 n 天上升趋势 K 线
- `generate_downtrend_klines(n=120, ...)`：生成 n 天下降趋势 K 线
- `generate_b1_scenario()`：生成 B1 买点场景
- `write_klines_to_db()` / `write_stock_basic()`：写入测试数据

### 10.2 测试覆盖范围

| 测试文件 | 覆盖范围 |
|---------|---------|
| test_database.py | 路径解析、连接上下文、事务回滚、表初始化、幂等性 |
| test_indicators.py | 56+ 指标计算测试 |
| test_strategies.py | 战法识别测试、数据库集成 |
| test_screener.py / test_screener_p3.py | 选股评分、趋势/量价/风险评分 |
| test_setup_wizard.py | 环境检测、文件写入、模式切换 |
| test_exam_rules.py | B1 规则、砖型图规则、单针规则、评分标准 |
| test_trade_manager.py / test_trade_parser.py | 交易记录 CRUD、口语化解析 |
| test_portfolio_diagnosis.py | 持股检查、防卖飞、出货信号、战法匹配 |
| test_watchlist.py | 观察池增删改查、批量扫描 |
| test_wave_theory.py | 三波理论识别 |
| test_kirin_detector.py | 麒麟会四阶段 |
| test_backtest.py | 策略组合回测框架 |
| test_cli_screen.py / test_cli_subparser.py | CLI 子命令分发 |
| test_data_e2e.py | 数据层端到端读写 |
| test_data_sync_extensions.py | DataSyncer 新方法、薄壳脚本 |
| test_indicator_cache.py | 指标缓存读写 |
| test_indicators_realdata.py | 真实 Tushare 数据指标验证 |
| test_intent_router.py | 意图路由规则匹配 |
| test_quality_check.py | SKILL.md 8 项质量检查 |
| test_rate_limiter.py | _RateLimiter 多进程安全限流 |
| test_backtest_scorer.py | 自优化器回测评分 |
| test_break_signal.py | 自优化器中断信号 |
| test_bridge_client.py | Bridge 降级网关 |
| test_loop_engine.py | 六步闭环状态机 |
| test_monitor.py | 自选股监控 |
| test_mutator.py | 参数变异引擎 |
| test_notifier.py | 通知推送 |
| test_param_registry.py | 参数注册表 |
| test_reflex_blacklist.py | 反例安全网 |
| test_report.py | 量化评估报告 |
| test_scorer.py | 交易评分 |
| test_self_optimizer_e2e.py / test_self_optimizer_integration.py | 自优化器端到端/集成 |
| test_tracking_system.py | 跟踪系统 |
| test_tushare_client.py | Tushare 客户端 |

### 10.3 运行测试

```bash
# 全部测试
python -m pytest tests/ -v

# 单文件测试
python -m pytest tests/test_indicators.py -v
```

---

## 11. 工具脚本（scripts/ 与 corpus/）

### 11.1 scripts/ 工具脚本

薄壳脚本，业务逻辑在 modules/：

| 脚本 | 职责 |
|------|------|
| [_common.py](file:///workspace/scripts/_common.py) | 共享工具（`load_watchlist()` 读取自选股清单） |
| [sync_watchlist.py](file:///workspace/scripts/sync_watchlist.py) | 同步缺失的自选股 K 线 |
| [sync_and_compute.py](file:///workspace/scripts/sync_and_compute.py) | 一站式同步 + 指标计算 |
| [batch_compute_indicators.py](file:///workspace/scripts/batch_compute_indicators.py) | 批量计算指标缓存 |
| [generate_report.py](file:///workspace/scripts/generate_report.py) | 生成 Z 哥量化评估报告 |
| [eval_strategies.py](file:///workspace/scripts/eval_strategies.py) | 策略评估 |
| [e2e_data_integrity.py](file:///workspace/scripts/e2e_data_integrity.py) | 端到端数据完整性检查 |

### 11.2 corpus/ 语料采集与质检

| 脚本 | 职责 |
|------|------|
| [quality_check.py](file:///workspace/corpus/quality_check.py) | SKILL.md 质量自动检查（8 项维度） |
| [batch_download_bilibili.py](file:///workspace/corpus/batch_download_bilibili.py) | 批量下载 B 站视频 |
| [batch_transcribe.py](file:///workspace/corpus/batch_transcribe.py) | 批量音频转写 |
| [srt_to_transcript.py](file:///workspace/corpus/srt_to_transcript.py) | 字幕清洗为纯文本 |
| [merge_research.py](file:///workspace/corpus/merge_research.py) | 合并调研结果 |

---

## 12. 数据库架构

SQLite 数据库包含 12 张表（8 张核心 + 4 张 `_self` 自我改进表），定义在 [modules/database.py](file:///workspace/modules/database.py)：

### 12.1 核心表（8 张）

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `stock_basic` | 股票基本信息 | ts_code / name / industry / market |
| `daily_kline` | 日线 K 线 | open / high / low / close / vol / pct_chg / is_limit_up |
| `indicator_cache` | 技术指标缓存（每日快照） | KDJ / MACD / BBI / MA / RSI / WR / 布林带 / 双线 / 砖形图 / DMI / 量比 / 信号 |
| `moneyflow` | 资金流向 | 大小单买卖金额、净流入 |
| `financial_data` | 财务报表 | revenue / net_profit / total_assets / pe / pb / ps |
| `trade_signals` | 交易信号记录 | signal_type / signal_score / signal_price |
| `trade_records` | 随堂测试/交易记录 | action / price / quantity / reason / signal_type / zg_review |
| `watchlist` | 自选股观察池 | ts_code / name / tags / add_date |

### 12.2 扩展表

| 表名 | 用途 |
|------|------|
| `sync_log` | 数据同步日志（data_type / last_date / status） |
| `tushare_indicator_cache` | Tushare 官方指标（diff 验证用） |
| `llm_response_log` | LLM 响应耗时日志（ts_code / model / response_time_ms / success） |

### 12.3 自我改进表（4 张 `_self` 后缀）

定义在 [modules/tracking_tables.sql](file:///workspace/modules/tracking_tables.sql)：

| 表名 | 用途 |
|------|------|
| `tracking_pool_self` | 跟踪股票池 |
| `tracking_records_self` | 跟踪记录（每日指标 + 信号） |
| `monthly_reviews_self` | 月度复盘报告 |
| `strategy_performance_self` | 策略表现统计 |

### 12.4 索引策略

每张表均建立 `(ts_code, trade_date DESC)` 复合索引，优化按股票代码和时间范围查询的性能。

---

## 13. 依赖关系总览

### 13.1 Python 依赖（requirements.txt）

```
tushare>=1.4.0          # Tushare API
python-dotenv>=1.0.0    # 环境变量管理
pandas>=2.0.0           # 数据处理 + 向量化计算
requests>=2.28.0        # HTTP 请求
pyyaml>=6.0.0           # 意图规则解析
httpx>=0.24.0           # 异步 HTTP
```

**可选依赖**（pyproject.toml）：
- `corpus`：yt-dlp + faster-whisper（语料采集）
- `dev`：pytest + pytest-cov

**API 层额外依赖**：fastapi + uvicorn + pydantic-settings

### 13.2 前端依赖（package.json）

```
react@19 / react-dom@19
react-router-dom@7
@tanstack/react-query@5
axios
echarts@6 + echarts-for-react
tailwindcss@4 + @tailwindcss/vite
zustand@5
typescript@6 / vite@8 / eslint@10
```

### 13.3 模块间依赖关系

```
modules/__init__.py (统一加载 .env)
    ↓
modules/database.py (SQLite 基础)
    ↓
modules/tushare_client.py ──→ modules/data_sync.py ──→ modules/indicators/
                                                        ↓
                                                  modules/strategies/
                                                        ↓
                            ┌───────────────────────────┴───────────────────────┐
                            ↓                                                   ↓
                    modules/screener.py                              modules/backtest.py
                    modules/loop_engine.py                           modules/backtest_six_step.py
                    modules/portfolio_diagnosis.py                   modules/watchlist.py
                            ↓                                                   ↓
                            └───────────────────┬───────────────────────────────┘
                                                ↓
                                    modules/cli.py + cli_commands.py
                                                ↓
                                    api/services/ → api/routes/ → api/main.py
                                                ↓
                                    frontend/src/api/ → pages/ → components/
```

### 13.4 self_optimizer 依赖

```
self_optimizer/param_registry.py (参数注册表)
    ↓
self_optimizer/mutator.py (变异) ──→ self_optimizer/backtest_scorer.py (评分)
                                        ↓
                                self_optimizer/reflex_blacklist.py (安全网)
                                        ↓
                                self_optimizer/phase2_hillclimb.py (爬山迭代)
                                        ↓
                                self_optimizer/phase3_report.py (报告)
                                        ↓
                                self_optimizer/__init__.py (编排)
```

被 `strategies/base_strategies.py` 通过 `get_active_param()` 读取参数。

---

## 14. 项目运行方式

### 14.1 安装

```bash
git clone https://github.com/lululu811/zettaranc-skill.git
cd zettaranc-skill
pip install -r requirements.txt
# 或安装为本地包（注册 zt 命令）
pip install -e .
```

安装后注册三个命令：
- `zt`：主 CLI 工具
- `zt-web`：启动 Web 看板后端
- `zt-monitor`：启动自选股监控

### 14.2 配置

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
DATA_MODE=jnb                              # jnb=真实数据 / websearch=纯LLM
TUSHARE_TOKEN=你的56位token                 # JNB 模式必填
TUSHARE_API_URL=中转API地址                 # JNB 模式必填
DB_PATH=data/stock_data.db                 # 数据库路径
LLM_API_KEY=***                            # 可选，启用 LLM 对话
IM_PUSH_WEBHOOK=                           # 可选，飞书推送 webhook
```

### 14.3 初始化

```bash
# 创建数据库（12 张表）
python -m modules.database

# 同步股票基本信息（5525 只，只需执行一次）
python -m modules.data_sync sync

# 同步单只股票 K 线 + 指标缓存
python -m modules.data_sync sync --ts_code 600487.SH --days 120 --indicators

# 查看同步状态
python -m modules.data_sync status
```

### 14.4 CLI 使用

```bash
# 股票分析
zt analyze 600487.SH
zt analyze 600487.SH --days 60 --json

# 选股扫描
zt screen --strategy B1 --limit 20
zt screen --strategy 完美图形 --limit 10

# 持仓诊断
zt diagnose 600487.SH --json

# 策略回测
zt backtest shaofu 600487.SH --days 250
zt backtest multi 600487.SH --strategy b1,b2
zt backtest portfolio 600487.SH,601318.SH

# 观察池管理
zt watchlist add 600487.SH --tags 波段,通信
zt watchlist list
zt watchlist scan

# 交易记录
zt trade add "4月25号买了100股茅台，1800块"
zt trade list
zt trade review

# 每日工作流（五步）
zt daily
zt daily --json

# 数据同步
python -m modules.data_sync sync --ts_code 600487.SH --days 120 --indicators

# 自优化器
zt self_optimize

# 意图聊天
python -m modules.intent_chat "B1 买点怎么判断"
```

### 14.5 Python API

```python
# 分析单只股票
from modules.indicators import analyze_stock
result = analyze_stock("600487.SH", days=60)
print(f"J={result.j:.1f}, MACD DIF={result.dif:.2f}")

# 战法识别
from modules.strategies import detect_all_strategies
signals = detect_all_strategies("600487.SH", days=60)

# 策略回测
from modules.backtest import backtest_multi_strategy
result = backtest_multi_strategy(
    ts_code="600487.SH", days=120, strategies=["b1", "b2"], position_pct=0.3
)

# 少妇战法六步回测
from modules.backtest_six_step import backtest_shaofu_single
result = backtest_shaofu_single("600487.SH", days=250)

# 选股
from modules.screener import screen_stocks
results = screen_stocks(criteria="b1", max_stocks=50)

# 持股诊断
from modules.portfolio_diagnosis import diagnose_stock, format_report
report = diagnose_stock("600487.SH", days=100)
print(format_report(report))
```

### 14.6 Web 看板

```bash
# 启动后端 API（端口 8000）
zt-web
# 或
python -m api.main

# 启动前端（端口 5173）
cd frontend
npm install
npm run dev
```

前端通过 Vite proxy 将 `/api` 请求转发到 `http://localhost:8000`。

### 14.7 测试

```bash
# 全部测试
python -m pytest tests/ -v

# 单文件测试
python -m pytest tests/test_indicators.py -v

# 质量检查
python corpus/quality_check.py SKILL.md
```

---

## 15. CI/CD 与质量门

### 15.1 GitHub Actions（.github/workflows/）

#### [test.yml](file:///workspace/.github/workflows/test.yml)

5 个 job：

| Job | 职责 | 触发条件 |
|-----|------|---------|
| **test** | 运行全部 pytest 测试 | push/PR |
| **lint** | ruff check + ruff format check | push/PR |
| **quality-gate** | SKILL.md 8 项质量检查 | push/PR |
| **e2e-realdata** | 真实 Tushare 数据回归测试（600519.SH × MACD/KDJ/RSI vs stk_factor） | push/PR（需 secrets） |
| **pre-commit** | pre-commit 全量钩子 | push/PR |

#### [e2e-cron.yml](file:///workspace/.github/workflows/e2e-cron.yml)

定时端到端测试。

### 15.2 pre-commit 钩子（.pre-commit-config.yaml）

| 钩子 | 职责 |
|------|------|
| **ruff** | lint + format（仅 modules/ 和 tests/） |
| **ruff-format** | 格式化检查 |
| **mypy** | 类型检查（限关键模块：screener/cli/data_sync/indicators/core/strategies/*） |
| **skill-quality-check** | SKILL.md 12 项质量门（仅 SKILL.md 或 quality_check.py 改动时触发） |
| **check-merge-conflict** | 合并冲突检查 |
| **check-yaml** | YAML 语法检查 |
| **end-of-file-fixer** | 文件结尾换行 |
| **trailing-whitespace** | 行尾空格 |

### 15.3 代码风格

- Python：ruff（line-length=120, target-version=py310）
- TypeScript：ESLint
- 编辑器配置（.editorconfig）：Python 4 空格缩进，Markdown 2 空格缩进，UTF-8 LF 换行

---

## 16. 关键设计原则

### 16.1 数据准备与 LLM 分离

**Python 层只做数据准备，所有点评由 LLM 用 Z哥角色生成。**

这是项目最核心的设计原则。Python 层负责指标计算、信号检测、报告生成等数据准备工作，所有需要"Z哥口吻"的话术由 LLM 基于 SKILL.md 角色协议生成，避免"AI味"。

### 16.2 双模式架构

通过 `DATA_MODE` 环境变量在 JNB（真实数据）和 websearch（纯 LLM）模式间切换，同一套代码支持两种使用场景。

### 16.3 降级网关

`bridge_client.py` 实现 bridge 优先、本地 SQLite 回退的降级策略，保证可用性。

### 16.4 注册表模式

`screener.py` 用 `_CRITERIA_REGISTRY` + `@_register` 装饰器替代 if-elif 链，新增筛选条件只需装饰即可。

### 16.5 管道模式

`indicators/data_layer.py` 的 `_PIPELINE` 30 步指标计算管道，每步含最小 K 线数阈值，不足则跳过。

### 16.6 状态机驱动

`loop_engine.py` 用 `LoopState` 枚举明确划分六步闭环的各个阶段。

### 16.7 多进程安全

`_RateLimiter` 使用 `multiprocessing.Lock` 保证多进程环境下正确限流。

### 16.8 缓存策略

- **内存 + DB 双层缓存**：`indicators/data_layer.py` 的 `_indicator_memory_cache`
- **属性缓存**：`strategies/core.py` 的 `_get_kdj/_get_bbi/_get_macd_dif` 缓存到 DailyData 属性（O(1)）
- **mtime 缓存**：`commentary_service.py` 通过比较文件 mtime 决定是否重新读取 SKILL.md
- **LRU 缓存**：`commentary_service.py` 的 `generate_commentary`（TTL 3600s，最大 100 条）

### 16.9 自我改进闭环

`tracking_manager` → `tracking_syncer` → `review_generator` → `harness_updater` 形成完整的"跟踪→复盘→改进"闭环，所有操作通过 `improvement_logger` 记录到 JSONL 日志。

### 16.10 参数化与可进化

通过 `self_optimizer/param_registry` 定义可调参数，`self_optimizer` 通过 mutate → backtest score → ratchet 实现参数自动优化，`reflex_blacklist` 8 条反例防止回归。

### 16.11 安全与合规

- **免责声明**：SKILL.md 和 README.md 均包含明确免责声明——不构成任何投资建议
- **版权边界**：原始语料不提交到仓库，只保留粉丝整理的 Markdown 提炼文件
- **敏感信息**：Tushare Token 和 API URL 通过 `.env` 文件管理，绝不硬编码
- **信息偏差标注**：SKILL.md 的「诚实边界」一节明确标注公开表达与真实想法的差异

---

## 附录：版本规范

遵循语义化版本，但含义针对本项目定制：

| 位 | 含义 | 示例 |
|----|------|------|
| MAJOR | 心智模型级别的重构 | v1.3.0：将 6 个心智模型重组为 5 个 |
| MINOR | 新增战术/启发式/语料/模块 | v2.0.0：新增 Tushare 数据层和 8 个 Python 模块 |
| PATCH | 排版修正、安全修复、数字更新 | v2.1.1：移除 URL 硬编码 |

---

> **免责声明**：本项目用于理解 zettaranc（万千）的思维模式，**不构成任何投资建议**。金融市场风险极高，任何基于历史信息的交易框架都可能失效。
>
> Love and Share 🖤
