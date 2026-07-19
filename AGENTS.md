# zettaranc-skill · Agent 指南

> 本文件面向 AI 编程 Agent。阅读前请确认你已通读本文件，再操作代码或文档。
> 本文所有事实（版本号、测试数、命令、文件清单）均已对照仓库实际内容核实（v4.0.3，2026-07-19）。

---

## 项目概述

本项目是一个 **AI Skill（思维框架蒸馏包）+ 真实数据量化工具** 的混合体。

核心目标：将 B 站 UP 主 / 前阳光私募冠军基金经理 zettaranc（万千）的投资思维框架、决策启发式和表达 DNA，封装为可供 Claude Code / Cursor 等 AI 工具调用的 Skill 文件（`SKILL.md`），同时提供基于真实 Tushare 行情数据的 Python 数据层 + Rust 内核支撑。

- **核心交付物**：`SKILL.md`（可直接被 AI 工具加载的角色扮演协议，Skill-Schema-V2 合规）
- **计算内核**：Rust workspace（6 crate，PyO3 + Polars + Rayon）→ `_core_compute` 原生扩展
- **数据层**：Python 模块 + SQLite 数据库 + Tushare/Indevs/Bridge 数据源（JNB 模式）
- **Web 看板**：`api/`（FastAPI 后端）+ `frontend/`（React + Vite + Tailwind 前端），可选
- **语料基础**：约 467 篇直播/付费课整理文章（~200 万字）+ 13 个 ztalk 视频 transcript（~12.7 万字）+ 9 篇交易心理系列（~3.3 万字）+ 后续新增文章
- **许可证**：MIT
- **当前版本**：**v4.0.3**（以 `pyproject.toml` 与 `docs/CHANGELOG.md` 为准）

### 双模式架构

| 模式 | 环境变量 | 说明 |
|------|---------|------|
| **JNB 模式** | `DATA_MODE=jnb` | 接入 Tushare 真实行情，具备实时数据查询、技术指标计算、战法识别能力 |
| **普通小万** | `DATA_MODE=websearch` | 纯 LLM 对话，不走任何外部数据接口 |

### Rust 内核开关（v4.0.0+）

| 环境变量 | 取值 | 说明 |
|---------|------|------|
| `ZETTARANC_BACKTEST_IMPL` | `rust`（默认） | 强制使用 Rust `_core_compute`，缺失时抛 `RuntimeError` |
| | `python` | 强制使用纯 Python 实现，跳过 `_core_compute` 导入 |
| | `auto` | 优先 Rust，导入失败 silent fallback 到 Python |

控制点：`modules/core/_rust_compat.py`（模块级 + 函数级双层缓存），桥接层 `modules/backtest/_rust_bridge.py`。

### 数据源优先级与降级路径

`modules/datasource.py` 的 `CompositeDataSource` 在 `auto` 模式下按以下优先级选源：

```
Indevs（配置 INDEVS_API_KEY 时优先，v3.8.1 新增）
  → tushare-data-bridge（HTTP 缓存代理，TUSHARE_BRIDGE_ENABLED=auto/always）
  → 本地 SQLite（data/stock_data.db，离线兜底）
```

> **重要**：`auto` 模式的回退链**不包含 Tushare Pro**。`TushareDataSource` 仅在两种情况下被使用：
> 1. 显式指定 `preferred="tushare"`
> 2. 在 `DataSyncer`（`modules/data_sync/syncer.py`）中，当 `INDEVS_API_KEY` 未配置且 `DATA_MODE=jnb` 时直接实例化（绕过 CompositeDataSource）

自 **v3.8.2** 起，K 线读取统一走 **DB 优先** 策略：先查 `daily_kline` 表，DB 没有时才调 API 并写回 DB 缓存。即使处于降级路径，工具也**不会编造价格或信号**，而是明确告知当前数据状态。

### 架构分层

```
Rust 内核（rust/crates/，6 crate）         Python 数据层（modules/）          LLM 角色层（SKILL.md）
├─ core_types    共享类型/Schema/Error      ├─ core/             公共模块      ├─ 角色扮演规则
├─ indicators    技术指标（ATR）             │  ├─ _rust_compat.py Rust 桥接   ├─ Agentic Protocol
├─ screener      选股评分（polars）          │  ├─ errors.py       50 错误码   ├─ 9 个核心心智模型
├─ backtest_engine 单/组合回测（rayon）      │  ├─ metrics.py      绩效指标    ├─ 决策启发式
├─ grid_search   Walk-forward 寻优           │  ├─ paths.py        路径常量    ├─ 表达 DNA
└─ bindings      PyO3 绑定 → _core_compute   │  ├─ walk_forward.py  窗口切分    └─ 诚实边界
                                              │  ├─ market_context.py 市场环境
Python 桥接（modules/）                       │  ├─ atr.py          ATR 计算
├─ backtest/_rust_bridge.py  CLI↔Rust 桥      │  └─ net.py          网络工具
├─ datasource.py   统一数据源协议             ├─ tushare_client.py  Tushare API
│                  （Indevs/Bridge/SQLite）    ├─ bridge_client.py   Bridge HTTP 客户端
├─ data_sync/      数据同步子包               ├─ indevs_client.py   Indevs 客户端
├─ indicators/     60+ 技术指标               ├─ database.py        SQLite（15 张表）
├─ strategies/     30+ 战法识别               ├─ constants.py       28+ 命名常量（v4.0.2）
├─ screener/       选股评分子包               ├─ simulator/         交易模拟器
├─ simulator/      少女/少妇模拟器             ├─ verify/            v1.0 验收工程化
├─ backtest/       回测子包（含 Rust 桥）     ├─ self_optimizer/    Darwin 自优化管线
├─ verify/         v1.0 验收工程化             ├─ statistics/        统计检验框架
└─ cli.py          15 个顶层子命令             └─ ...                其他业务模块
```

**关键设计原则**：Python 层负责 **数据准备与业务编排**，计算密集域（指标 / 回测 / 网格搜索 / 选股）走 Rust `_core_compute`，所有点评、分析话术由 LLM 用 Z 哥角色生成，避免"AI 味"。宿主通过 CLI `--json` 或 Web API 获取结构化数据。

**自优化与寻优管线说明**（三者互补，防止过拟合）：
- `self_optimizer/`（Darwin 管线）：LLM 驱动的参数自优化，通过变异 + 评分 + 反射黑名单迭代策略参数组合。做探索性优化。
- `simulator/walk_forward` + `verify/`：滚动窗口样本内训练 + 样本外验证（真切片，v3.7.3 修复了假切片 bug）；`verify/` 提供一键 `zt verify v1.0` 与五项硬指标判定。做验证性优化。
- `modules/verify/portfolio_walk_forward.py::portfolio_grid_search_optimize()`（v3.10.2）：组合回测参数 IS 网格搜索自动寻优（默认 4 维参数空间约 81 组合，IS = 前 60% 交易日，剩余 40% 留 OOS）。Rust 加速版本在 `rust/crates/grid_search`。
- 典型流程：Darwin 产出候选参数集 → walk-forward / verify 验证其样本外稳定性 → 通过者写回 `param_registry`。

---

## 技术栈与运行时架构

### 核心技术栈

| 层级 | 技术 |
|------|------|
| Rust 内核 | Rust 1.78+（stable）、PyO3 0.23、Polars 0.54、Rayon 1.10、Arrow 59、proptest 1.5 |
| 构建工具 | maturin ≥1.5（Rust → Python 扩展） |
| 数据管道 | Python 3.12+（标准库 + `sqlite3`、`pathlib`、`dataclasses`、`enum`、`StrEnum`） |
| 外部数据 | `tushare`（Pro API，支持中转 URL）、`pandas` ≥3.0,<4、`requests`、`httpx`、`pyyaml` |
| 可选数据源 | Indevs Tushare Replay API（需 `INDEVS_API_KEY`） |
| 环境配置 | `python-dotenv`（`.env` 文件） |
| 数据库 | SQLite（本地文件，15 张表 = 11 张核心表 + 4 张自我改进跟踪表） |
| 接口协议 | CLI（`zt` 入口）、可选 FastAPI Web 服务（`zt-web`） |
| 前端看板 | React 19 + Vite 8 + TypeScript 6 + Tailwind CSS 4 + ECharts 6 |
| 状态管理 | Zustand 5 + TanStack React Query 5 + axios + react-router-dom 7 |
| 测试框架 | `pytest`（v4.0.3 实测 **1318 passed, 15 skipped**，98 个 .py 文件 + 1 个 .md）、`cargo test`（73 个测试） |
| 代码质量 | `ruff`（lint + format）、`mypy`（strict=false 起步，返回注解 100%）、pre-commit |
| 视频下载 | `yt-dlp`（语料采集，可选） |
| 语音转写 | `faster-whisper`（语料采集，可选） |
| 文档格式 | Markdown（全部文档与语料） |
| 版本控制 | Git |

### 关键配置文件

| 文件 | 作用 |
|------|------|
| `pyproject.toml` | 包定义、`zt` / `zt-web` / `zt-monitor` 命令入口、pytest/ruff/mypy/coverage 配置、`[tool.maturin]` Rust 扩展配置、可选依赖分组 |
| `requirements.txt` | 核心 Python 依赖（tushare / python-dotenv / pandas / requests / pyyaml / httpx） |
| `.env.example` | 环境变量模板（`.env` 不入库） |
| `rust/Cargo.toml` | Rust workspace 配置（6 members、workspace dependencies、release profile） |
| `rust/rust-toolchain.toml` | Rust 工具链（stable + rustfmt + clippy + rust-src） |
| `rust/.cargo/config.toml` | macOS aarch64 lld 链接器配置（规避 LINKEDIT 8 字节对齐 bug） |
| `frontend/package.json` | 前端依赖与脚本 |
| `frontend/vite.config.ts` | Vite 配置（端口 5173，代理 `/api` 到 localhost:8000） |
| `.editorconfig` | 编辑器格式统一配置 |
| `.pre-commit-config.yaml` | 提交前 ruff（v0.15.15）、部分 mypy（v1.10.0）、SKILL.md 12 项质量门、双轴评审（手动）、merge/yaml/行尾空白检查 |
| `.github/workflows/test.yml` | CI：test / lint / type-check / quality-gate / e2e-realdata / pre-commit 六个 job |
| `.github/workflows/rust-ci.yml` | Rust CI：cargo fmt/clippy/test + maturin smoke（Ubuntu + macOS 矩阵） |
| `.github/workflows/release.yml` | 发布 CI/CD：test / pypi-publish / github-release / clawhub-publish 四个 job |
| `.github/workflows/e2e-cron.yml` | 每周一 02:00 UTC 真实数据回归 cron（支持手动触发） |

### 环境变量说明（`.env.example`）

```ini
DATA_MODE=jnb                       # jnb(真实数据) 或 websearch(纯对话)
TUSHARE_TOKEN=你的token
TUSHARE_API_URL=                    # 中转 API 地址（JNB 模式必填）
# TUSHARE_VERIFY_TOKEN_URL=***      # 可选，实时行情验证地址

# Tushare Bridge 配置（可选，用于数据降级）
# 默认值与 modules/bridge_client.py 中 _BRIDGE_* 保持一致
# TUSHARE_BRIDGE_HOST=127.0.0.1
# TUSHARE_BRIDGE_PORT=8765
# TUSHARE_BRIDGE_TIMEOUT=10
# TUSHARE_BRIDGE_ENABLED=auto       # auto/always/never

# 限流配置（可选）
# TUSHARE_RPM=120  # 每分钟请求数

# Indevs Tushare Replay API（可选，配置后数据同步优先走该源）
# INDEVS_API_KEY=your_api_key
# INDEVS_API_URL=https://ai-tool.indevs.in/tushare/pro

DATA_DIR=data
DB_PATH=data/stock_data.db
LLM_API_KEY=***                     # 可选，LLM 回答生成
# LLM_BASE_URL=https://api.openai.com/v1
# LLM_MODEL=gpt-4o-mini
# ANTHROPIC_API_KEY=***             # 可选，Anthropic Claude API

# KB_ENABLED=true                   # 可选，向量知识库
# KB_API_URL=http://localhost:8000
IM_PUSH_WEBHOOK=                    # 可选，飞书 webhook

# 缓存配置（可选）
# COMMENTARY_CACHE_TTL=3600
# SIMULATION_NARRATE_CACHE_TTL=3600

# ZETTARANC_ENV=/path/to/.env       # 可选，自定义 .env 路径
# ZETTARANC_BACKTEST_IMPL=rust      # 可选，rust/python/auto（v4.0.0+）
```

> v2.1.1 之后，所有 Tushare URL 均从环境变量读取，代码中不再硬编码任何内部域名。

---

## Rust 工作区（v4.0.0+）

`rust/` 是一个 Cargo workspace，包含 **6 个 crate**，通过 PyO3 + maturin 编译为 Python 原生扩展模块 `_core_compute`。

### workspace 配置

- **`rust/Cargo.toml`**：`resolver = "2"`，6 members，`edition = "2021"`，`rust-version = "1.78"`
- **workspace.dependencies**：`thiserror`、`anyhow`、`tracing`、`polars = "0.54"`、`arrow-array/arrow-schema = "59"`、`rayon = "1.10"`、`proptest = "1.5"`、`pyo3 = { version = "0.23", features = ["extension-module", "abi3-py312"] }`
- **profile.release**：`opt-level = 3`、`lto = "thin"`、`codegen-units = 1`、`strip = "symbols"`
- **`rust/Cargo.lock`** 实际解析：`pyo3 0.23.5`

### 6 个 crate 职责

| Crate | 包名 | 职责 | 关键文件 |
|-------|------|------|---------|
| `core_types` | `zt_core_types` | 共享类型根：`KLine`/`KLineSeries` 结构体、12 字段 Arrow schema、`CoreError` 枚举（9 变体） | `src/{lib,kline,schema,error}.rs` |
| `indicators` | `zt_indicators` | 技术指标（当前 ATR，`compute_atr`/`compute_atr_default`，DEFAULT_WINDOW=14） | `src/{lib,atr}.rs` |
| `screener` | `zt_screener` | 选股评分引擎（polars DataFrame + 3 内置规则：`close_vs_sma20`/`volume_breakout`/`trend_strength`） | `src/{lib,scoring}.rs` |
| `backtest_engine` | `zt_backtest_engine` | 回测引擎：`run_single_strategy_backtest` + `run_portfolio_backtest`（rayon 并行多股，`final_value = initial + Σ(trades.pnl)` 不变式） | `src/{lib,single,portfolio}.rs` |
| `grid_search` | `zt_grid_search` | 参数网格搜索 + Walk-forward 验证（`run_grid_search` + `make_walk_forward_splits`，rayon 并行 splits × params 笛卡尔积） | `src/{lib,walk_forward}.rs` |
| `bindings` | `zt_bindings`（模块名 `_core_compute`） | PyO3 绑定层：`core.rs`（pure-Rust，cargo 可测） + `lib.rs`/`backtest_bindings.rs`/`error.rs`（PyO3 wrapper，feature-gated） | `src/{lib,core,backtest_bindings,error}.rs` |

### `_core_compute` Python 模块暴露的 7 个函数

1. `rust_smoke() -> &'static str` — 返回 `"ok from rust"`，烟雾测试
2. `raise_value_error() / raise_key_error()` — 错误映射测试
3. `compute_atr_py(klines, window=14) -> Vec<f64>` — ATR 计算
4. `run_single_strategy_backtest_py(config, klines) -> dict` — 单股回测
5. `run_portfolio_backtest_py(config, klines_by_code) -> dict` — 组合回测
6. `run_grid_search_py(base_config, param_grid, splits, klines) -> dict` — 网格搜索

### bindings 双模式架构

- **`core.rs`（pure-Rust，无 PyO3）**：6 个 View 结构体 + 4 个 public 入口函数（`core_compute_atr` / `core_run_single_strategy_backtest` / `core_run_portfolio_backtest` / `core_run_grid_search`），cargo 可直接测试
- **`lib.rs` + `backtest_bindings.rs` + `error.rs`（PyO3 wrapper，`#[cfg(feature = "pyo3")]`）**：Python 对象 ↔ serde_json::Value 转换层，`CoreError → PyErr` 映射
- **features**：`default = ["pyo3"]`、`pyo3 = ["dep:pyo3"]`
- **crate-type**：`["cdylib", "rlib"]`（cdylib 给 maturin，rlib 让 `cargo test --no-default-features` 能链 `[[test]]`）

### Rust 测试（共约 73 个）

| Crate | 单元测试 | proptest/集成测试 | 合计 |
|-------|---------|------------------|------|
| `core_types` | 1（schema_has_12_fields） | 2（smoke.rs） | 3 |
| `indicators` | 4（atr.rs） | 8（proptest.rs） | 12 |
| `screener` | 5（scoring.rs） | 8（proptest.rs） | 13 |
| `backtest_engine` | 6（single+portfolio） | 11（proptest）+ 4（test_force_close.rs） | 21 |
| `grid_search` | 5（lib+walk_forward） | 8（proptest.rs） | 13 |
| `bindings` | — | 1（atr_golden.rs，Python golden file byte-equal）+ 10（test_core_rust.rs） | 11 |
| **合计** | | | **73** |

### 构建路径

- **macOS**：`rust/scripts/build_macos.sh`（maturin develop --release + `fix_linkedit_alignment.py` 修复 LINKEDIT 8 字节对齐 + codesign 重签名）
- **Linux**：`rust/scripts/build-linux.sh`（`maturin build --release --interpreter python3.11` 产出 wheel）
- **容器**：`rust/Dockerfile.test`（python:3.11-slim 基础镜像）

### force-close 不变式

`backtest_engine::single` 末尾强制平仓，通过 `final_value = cash + position * last_price` 保证 `sum(trades.pnl) == final_value - initial_cash`，由 `tests/test_force_close.rs` 4 个回归测试守护（v4.0.3 Bug #51 修复）。

---

## 项目结构

```
zettaranc-skill/
├── SKILL.md / README.md / AGENTS.md / pyproject.toml / .env.example / skill.json
├── rust/                # Rust workspace（v4.0.0+）
│   ├── Cargo.toml / Cargo.lock / rust-toolchain.toml
│   ├── .cargo/config.toml  # macOS aarch64 lld 配置
│   ├── Dockerfile.test
│   ├── scripts/         # build_macos.sh / build-linux.sh / fix_linkedit_alignment.py
│   └── crates/          # 6 crate：core_types / indicators / screener / backtest_engine / grid_search / bindings
├── python/_core_compute/  # maturin 编译产物（Python 包入口）
├── data/                # SQLite 数据库与报告（不入库）
│   └── registry/        # param_registry 跨进程持久化（JSON）
├── docs/                # 文档（CHANGELOG, TODO, USER_GUIDE, ROADMAP, CONFIG_GUIDE 等）
├── modules/             # Python 数据层与业务逻辑（详见架构分层）
├── api/                 # FastAPI REST API（可选）
│   ├── routes/          # 9 个路由模块
│   ├── services/        # 7 个服务层
│   ├── models/          # 请求/响应模型
│   ├── config.py        # 应用配置
│   └── main.py          # 入口 + start_web() 函数
├── frontend/            # React 前端看板（可选）
├── knowledge/           # 29 篇顶层交易体系知识文档 + 3 个子目录文档
├── tests/               # pytest 测试（98 个 .py 文件 + 1 个 .md）
├── scripts/             # 薄壳工具脚本（业务逻辑在 modules/）
├── corpus/              # 语料采集与质检工具
├── rules/               # 意图规则与决策框架
└── references/          # 调研提炼文件（原始语料不入库）
```

### modules/ 子包结构

```
modules/
├─ core/                 公共模块（v3.8+，v3.9.0 大幅扩充，v4.0.x 加 Rust 桥接）
│  ├─ __init__.py           包入口（导出 16+ 公开符号）
│  ├─ atr.py                ATR 公共计算（v3.10.1）
│  ├─ errors.py             ErrorCode（50 成员）+ ZettarancError（v3.10.4，v4.0.3 扩充）
│  ├─ market_context.py     MarketRegime 枚举唯一来源（v3.9.0）
│  ├─ metrics.py            PerformanceMetrics（20 字段）+ TRADING_DAYS_PER_YEAR=252
│  ├─ net.py                disable_proxy()
│  ├─ paths.py              DATA_DIR/REGISTRY_DIR/REPORTS_DIR（v3.9.0）
│  ├─ walk_forward.py       WalkForwardSplit + make_walk_forward_splits（v3.9.0）
│  └─ _rust_compat.py       Rust/Python 切换 compat shim（v4.0.x，双层缓存）
├─ backtest/             回测子包（v3.8+，v3.10.0 多策略融合，v4.0.2 加 Rust 桥）
│  ├─ single.py             单策略回测
│  ├─ portfolio.py          组合回测（B1/B2/SB1/长安多策略并行、共振评分、环境权重、StrategyStats）
│  └─ _rust_bridge.py       CLI ↔ Rust PyO3 回测桥（v4.0.2，silent fallback）
├─ indicators/           60+ 技术指标
│  ├─ core.py           基础/数学/核心指标（KDJ/BBI 唯一实现处）
│  ├─ price_patterns/   价格形态识别子包（base/brick/bull_rope/complex_patterns/key_candles/sandglass/screener_helper）
│  ├─ volume_patterns.py 量价信号
│  ├─ wave_theory.py    三波理论识别
│  ├─ kirin_detector.py 麒麟会四阶段
│  └─ data_layer.py     数据接入/缓存/可视化
├─ screener/             选股评分子包（含蜈蚣图/沙漏/牛绳过滤）
│  ├─ models.py / data.py / criteria.py / scoring.py / engine.py
│  ├─ market.py / format.py / workflow.py / cli.py
├─ simulator/            少女/少妇模拟器（v3.4-v3.6）
│  ├─ simulator.py          主入口
│  ├─ market_context.py     市场环境判定
│  ├─ signal_filter.py      信号过滤（simple / resonance 双模式）
│  ├─ position_sizer.py     ATR 动态仓位
│  ├─ execution_engine.py   撮合执行引擎
│  ├─ execution_constraints.py  A 股约束（T+1/涨跌停/ST/停牌）
│  ├─ cost_model.py         真实成本模型
│  ├─ slippage_model.py     动态滑点
│  ├─ exit_manager.py       止盈止损管理
│  ├─ metrics.py            绩效指标（薄包装 → core/metrics.py）
│  ├─ strategy_adapter.py   战法信号标准化
│  ├─ resonance_scorer.py   多战法共振评分
│  ├─ environment_weights.py 环境权重动态调整
│  ├─ param_space.py        参数空间与网格生成
│  ├─ walk_forward.py       滚动窗口 OOS 验证
│  ├─ optimizer_report.py   walk-forward 报告输出
│  └─ narrator.py           Z 哥风格回测叙事
├─ strategies/           30+ 战法识别（5 子模块）
│  ├─ core.py / base_strategies.py / compound_strategies.py / sell_signals.py / vectorized.py
├─ statistics/           统计检验框架
│  ├─ __init__.py / criteria.py / sensitivity.py / ensemble.py
├─ verify/               少妇战法 v1.0 验收工程化（v3.7.0+）
│  ├─ pipeline.py / gates.py / walk_forward.py / scorer.py / pool.py
│  ├─ registry_writer.py / report.py / portfolio_engine.py / portfolio_walk_forward.py / cli.py
├─ data_sync/            数据同步子包
│  ├─ rate_limiter.py / indicator_cache.py / fetcher.py / syncer.py / cli.py / __main__.py
├─ self_optimizer/       Darwin 自优化管线
│  ├─ param_registry.py / mutator.py / scorer.py / backtest_scorer.py
│  ├─ llm_judge.py / reflex_blacklist.py / phase1_baseline.py / phase2_hillclimb.py / phase3_report.py
├─ constants.py          28+ 命名常量（v4.0.2，仓位档/止损档/环境权重/涨跌停等）
├─ datasource.py         统一数据源协议（Indevs/Bridge/SQLite Composite）
├─ tushare_client.py / bridge_client.py / indevs_client.py
├─ database.py           SQLite 管理（15 张表）
├─ data_sync.py / screener.py  兼容 shim
├─ backtest_six_step.py  少妇战法六步闭环
├─ loop_engine.py        六步闭环状态机（v3.10.1 起支持 ATR 动态/移动止损）
├─ loop_engine_enhanced.py 增强版多策略共振闭环
├─ portfolio_diagnosis.py / watchlist.py
├─ cli.py / cli_commands.py 命令行统一入口（15 个顶层子命令）
├─ trade_parser.py / trade_manager.py / trade_reviewer.py
├─ intent_router.py / intent_chat.py / knowledge_retriever.py / llm_providers.py
├─ setup_wizard.py / report.py / commentary_service.py / review_generator.py
├─ monitor.py / notifier.py / tracking_manager.py / tracking_syncer.py
├─ improvement_logger.py / harness_updater.py / dynamic_config.py
├─ market_regime.py / position_manager.py / industry_filter.py
└─ __init__.py           .env 一次性加载（支持 ZETTARANC_ENV，override=False）

knowledge/（知识文件，29 篇顶层文档 + 3 个子目录补充文档）
├─ trading-core.md / indicators.md / sell-discipline.md / position-management.md
├─ market-macro.md / stock-glossary.md / trend-lines.md / exit-strategies.md
├─ key-candles.md / advanced-patterns.md / portfolio-management.md / trading-psychology.md
├─ breathing-theory.md / three-best-principles.md / iron-butterfly.md / four-rhythms.md
├─ six-tracks-2026.md / life-decision.md / life-decision-research.md
├─ career-development.md / business-judgment.md / business-judgment-research.md
├─ heuristics.md / framework-extraction.md / workflow.md / harness.md
├─ improvement-system.md / data_dictionary.md / signal_dictionary.md
├─ macro/etf-strategy.md         宏观研究子目录
├─ reference/thresholds.md       参考资料子目录
└─ strategies/choppy-market-sop.md 策略研究子目录

rules/
├─ intent_rules.yaml     意图匹配规则
├─ career_prompt.md      职业决策框架
└─ life_prompt.md        人生决策框架

references/research/（11 份调研提炼文件）
├─ 01-writings.md / 02-conversations.md / 03-expression-dna.md
├─ 04-external-views.md / 05-decisions.md / 06-timeline.md
└─ 07-11-*.md（小菜鸟、大富翁、tangoo、复盘、课代表等系列）
```

---

## 数据库架构

`modules/database.py` 中 `init_database()` 创建 11 张核心表，`init_tracking_tables()` 创建 4 张自我改进表，共 15 张：

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `stock_basic` | 股票基本信息 | ts_code, name, industry, market, list_date |
| `daily_kline` | 日线 K 线 | open, high, low, close, vol, amount, pct_chg |
| `indicator_cache` | 技术指标缓存（每日快照） | KDJ/MACD/BBI/MA/RSI/WR/布林带/双线/砖形图/DMI/量比/信号 |
| `moneyflow` | 资金流向 | 大小单买卖金额、净流入 |
| `financial_data` | 财务报表 | revenue, net_profit, total_assets, pe, pb, ps |
| `trade_signals` | 交易信号记录 | signal_type, signal_score, signal_price |
| `trade_records` | 随堂测试/交易记录 | action, price, quantity, reason, signal_type, zg_review |
| `sync_log` | 数据同步日志 | data_type, last_date, status |
| `watchlist` | 自选股观察池 | ts_code, name, tags, add_date, alert_enabled |
| `tushare_indicator_cache` | Tushare 官方指标（diff 验证） | macd_dif, rsi_6, kdj_k, boll_mid 等 |
| `llm_response_log` | LLM 响应耗时日志 | ts_code, request_date, model, response_time_ms, success |
| `tracking_pool_self` | 自我改进跟踪池 | ts_code, add_date, status, strategy_tags |
| `tracking_records_self` | 跟踪记录表 | 行情 + 指标 + 信号每日快照 |
| `monthly_reviews_self` | 月度复盘表 | review_month, monthly_return, max_drawdown 等 |
| `strategy_performance_self` | 策略表现统计表 | strategy_name, review_month, accuracy_rate, sharpe_ratio |

每张表均建立合适的复合索引（如 `ts_code + trade_date DESC`）。另有 `modules/tracking_tables.sql` 保存跟踪表 DDL。

---

## 构建、测试与常用命令

### 安装依赖

```bash
# 核心 Python 依赖
pip install -r requirements.txt
# 或安装为本地可编辑包（推荐，会注册 zt / zt-web / zt-monitor 命令）
pip install -e .

# 语料处理可选依赖
pip install -e ".[corpus]"

# 开发测试依赖（含 maturin）
pip install -e ".[dev]"

# 构建 Rust 内核（v4.0.0+，JNB 模式回测加速必需）
cd rust/crates/bindings && maturin develop --release
# 验证
python -c "import _core_compute; print(_core_compute.__version__)"
```

> 本机开发环境使用项目根目录的 `.venv`；系统 `python` 命令可能不存在。

安装后可使用 `zt` 命令：

```bash
zt analyze 600487.SH
zt screen --strategy B1 --limit 20
zt watchlist scan
zt backtest shaofu 600487.SH --days 250
zt verify v1.0 --limit 50 --days 300 --walk-forward
```

### 运行测试

```bash
# Python 全部测试（当前实测：1318 passed, 15 skipped，约 30s）
python -m pytest tests/ -v

# 单文件测试
python -m pytest tests/test_indicators.py -v

# 慢速端到端测试（默认不跑）
python -m pytest tests/ -m slow -v

# 真实数据回归（需 TUSHARE_TOKEN + RUN_REALDATA=true）
python -m pytest tests/test_indicators_realdata.py -v

# Rust 全 workspace 测试（73 个）
cd rust && cargo test --workspace --exclude zt_bindings
# pure-Rust bindings 测试（无需 Python 解释器）
cargo test -p zt_bindings --no-default-features

# Rust 桥接 Python 测试
python -m pytest tests/test_rust_compat.py tests/test_cli_uses_rust.py -v
```

> `test_indicators_realdata.py` 等真实数据测试会在无 `TUSHARE_TOKEN` 时自动 skip。

### 数据库初始化与数据同步

```bash
# 初始化数据库（创建 15 张表）
python -m modules.database
# 或
zt sync init

# 同步股票基本信息（全量 5525 只）
python -m modules.data_sync sync
# 或
zt sync sync

# 同步单只股票 K 线 + 指标缓存
python -m modules.data_sync sync --ts_code 600487.SH --days 365 --indicators
# 或
zt sync sync --ts_code 600487.SH --days 365 --indicators

# 查看同步状态
zt sync status

# 同步 Tushare 官方指标（diff 验证）
zt sync stk-factor --ts_code 600487.SH --days 365
```

### CLI 主要命令

`zt` 共 **15 个顶层子命令**：`analyze / screen / score / workflow / diagnose / watchlist / sync / track / self-optimize / backtest / trade / daily / monitor / simulate / verify`。所有命令支持 `--json`，宿主可直接解析。

```bash
zt analyze <ts_code> [--days N] [--json]          # 分析单只股票
zt screen --strategy <策略> [--limit N] [--json]   # 批量选股（11 种策略别名：
                                                  #   B1/B2/B3/完美图形/超级B1/长安战法/建仓波/吸筹/
                                                  #   安全/超跌/突破/牵牛/牛绳/沙漏/沙漏评分/量比战法）
zt score <ts_code> [--json]                        # 综合评分
zt diagnose <ts_code> [--days N] [--json]          # 持仓诊断
zt workflow                                          # 每日五步工作流（等价 daily）
zt watchlist add <ts_code> --tags <标签>           # 添加自选股
zt watchlist list                                  # 查看观察池
zt watchlist scan [--json]                         # 批量扫描信号
zt watchlist remove <ts_code>                      # 移除自选股
zt backtest shaofu <ts_code> [--days N] [--json]   # 少妇战法回测（默认走 Rust）
zt backtest multi <ts_code> [--days N] [--json]    # 多策略融合回测
zt backtest portfolio <c1,c2,...> [--days N]       # 组合回测（多策略融合引擎）
zt simulate [codes] --days N --capital N --max-positions N --risk R --score S --signals N --json  # 交易模拟器
zt simulate [codes] --strategy-mode resonance --strategy-lookback N --min-resonance-score S --json  # 战法共振模式
zt simulate [codes] --walk-forward --wf-train-days N --wf-test-days N --wf-objective calmar --json  # Walk-forward 寻优
zt verify v1.0 [--limit N] [--days N] [--walk-forward] [--json]  # 少妇战法 v1.0 五项硬指标验收
zt trade add "口语化交易描述"                       # 记录交易
zt trade list / review / stats                     # 交易记录管理
zt daily [--json]                                  # 每日五步工作流
zt monitor [--json] [--no-push]                    # 自选股主动监控
zt track add/list/info/status/stats                # 自我改进跟踪池
zt self-optimize run/status/reset                  # Darwin 自优化
zt sync init/sync/status/stk-factor                # 数据同步
```

### CLI ↔ Rust 实现切换矩阵（v4.0.2+）

| 子命令 | 默认实现 | Rust 入口 | fallback |
|--------|----------|-----------|----------|
| `zt backtest shaofu` | Rust | `run_single_strategy_backtest_py` | Python `backtest_shaofu_single` |
| `zt backtest portfolio`（单股） | Rust | 同上 | 同上 |
| `zt backtest multi` | Python | — | — |
| `zt backtest portfolio`（多股） | Python | — | — |
| `zt verify v1.0` | Rust | 同上（per-stock bridge） | Python `_run_single_stock_backtest` |
| `zt screen` | Python | （v4.1+） | — |
| `zt analyze` / `zt diagnose` / `zt watchlist` / `zt trade` | Python | — | — |

### 启动 Web 看板

> `api/` 依赖 `fastapi`、`uvicorn`、`pydantic-settings`，当前未写入 `requirements.txt`，运行前请单独安装：

```bash
pip install fastapi uvicorn pydantic-settings

# 启动后端
zt-web
# 或 python -m api.main

# 启动前端（另开终端）
cd frontend
npm install
npm run dev        # 默认 http://localhost:5173
npm run build      # 生产构建（tsc -b && vite build）
npm run lint       # ESLint 检查
```

### 质量检查

```bash
# 验证 SKILL.md 是否通过 12 项质量标准（当前 12/12 通过，100/100）
python corpus/quality_check.py SKILL.md

# strict 模式（任一不通过则 exit 1）
python corpus/quality_check.py SKILL.md --strict

# 双轴评审（轴 A 确定性 + 轴 B LLM 深度，--skip-llm 可跳过 LLM）
python corpus/dual_axis_review.py SKILL.md --skip-llm

# Lint + 类型检查
ruff check modules tests
ruff format --check modules tests
mypy modules/ --ignore-missing-imports

# Rust 质量检查
cd rust && cargo fmt --all -- --check
cargo clippy --workspace --all-targets --no-deps --exclude zt_bindings -- -D warnings
```

### 语料采集脚本

| 脚本 | 用法 | 说明 |
|------|------|------|
| `corpus/batch_download_bilibili.py` | `python corpus/batch_download_bilibili.py` | 下载 B 站 ztalk 音频 |
| `corpus/batch_transcribe.py` | `python corpus/batch_transcribe.py` | 音频转写文本 |
| `corpus/srt_to_transcript.py` | `python corpus/srt_to_transcript.py input.srt` | 字幕清洗为纯文本 |
| `corpus/merge_research.py` | `python corpus/merge_research.py` | 合并调研结果 |
| `scripts/generate_atr_golden.py` | `python scripts/generate_atr_golden.py` | 生成 ATR golden file（Rust 对照基准） |
| `scripts/snapshot_python_tests.sh` | `bash scripts/snapshot_python_tests.sh` | M0 基线测试快照（含 test_rust_compat.py） |
| `scripts/benchmark_perf.py` | `python scripts/benchmark_perf.py [--save/--check]` | Python 热点性能基准 + 行为指纹校验 |

**路径约定**：部分脚本使用硬编码相对路径，请在项目根目录执行，并注意 `references/sources/` 中的原始语料不入库。

---

## 代码风格与开发规范

### 通用规范

- 所有脚本文件头包含 `#!/usr/bin/env python3`
- 使用 **中文** 编写文档字符串和注释
- 使用标准库为主，避免引入不必要的第三方依赖
- 每个模块文件末尾包含 `if __name__ == "__main__":` 命令行入口

### 编辑器配置（`.editorconfig`）

| 文件类型 | 缩进 | 大小 |
|---------|------|------|
| `*.py` | space | 4 |
| `*.sh` | space | 4 |
| `*.md` | space | 2（不裁剪行尾空格） |
| `*.json` | space | 2 |
| `*.rs` | space | 4（rustfmt 默认） |
| 全部 | UTF-8 | LF 换行 |

### Python 模块规范

- **数据库路径**：统一从 `os.getenv("DB_PATH", "data/stock_data.db")` 读取，支持相对路径和绝对路径
- **环境变量加载**：统一由 `modules/__init__.py` 在包首次 import 时一次性加载 `.env`（支持 `ZETTARANC_ENV` 自定义路径，`override=False` 保证测试 fixture 隔离）；各子模块不再重复加载
- **模块间 DB 路径解析**：`modules/*.py` 使用 `Path(__file__).parent.parent`（项目根目录）；`modules/indicators/*.py` 使用 `Path(__file__).parent.parent.parent`
- **路径常量**：`DATA_DIR` / `REGISTRY_DIR` / `REPORTS_DIR` 从 `modules/core/paths.py` 导入；`TRADING_DAYS_PER_YEAR` 从 `modules/core/metrics.py` 导入（注意：不在 paths.py）；`ZETTARANC_BACKTEST_IMPL` 从 `modules/core/_rust_compat.py` 读取
- **限流控制**：所有 Tushare/Indevs API 调用必须带 `_rate_limit()`，控制 120 次/分钟
- **事务管理**：数据库操作统一使用 `get_connection()` 上下文管理器（自动 commit/rollback，默认 WAL 模式）
- **错误处理**：API 调用用 try/except 包裹具体异常类型（v4.0.3 M4 已收窄全部 `except Exception`），记录 error log，返回空 DataFrame/None 而非抛异常中断；必要时 raise `ZettarancError`
- **类型统一**（v3.9.0 起）：`PerformanceMetrics`（20 字段）以 `modules/core/metrics.py` 为准；`MarketRegime` 枚举以 `modules/core/market_context.py` 为唯一来源；收益率字段统一命名 `annualized_return`；`equity_curve` 统一为 `list[float]`；ATR 计算统一用 `modules/core/atr.py`
- **错误码统一**（v3.10.4 起，v4.0.3 扩充）：`ErrorCode`（StrEnum，50 成员）+ `ZettarancError`（继承 `ValueError` 保持向后兼容）以 `modules/core/errors.py` 为准
- **包安装**：使用 `pip install -e .` 安装后，可通过 `zt` 命令或 `python -m modules.cli` 调用

### Rust 模块规范（v4.0.0+）

- 所有 crate 顶层 `#![forbid(unsafe_code)]` + `#![warn(missing_debug_implementations)]`
- **分层架构**：`core_types`（共享类型）← `indicators` / `screener` / `backtest_engine` ← `grid_search`（依赖 backtest_engine）← `bindings`（聚合所有，暴露 PyO3）
- **bindings 双模式**：`core.rs` 是 pure-Rust（cargo 可直接测试，无需 Python），`lib.rs` + `backtest_bindings.rs` + `error.rs` 是 PyO3 wrapper（feature-gated）
- **并行策略**：`backtest_engine::portfolio` 和 `grid_search` 都用 `rayon` 做 `par_iter`
- **错误映射**：`CoreError` → `PyErr`，业务可恢复 → `PyValueError`/`PyKeyError`；基础设施 → `PyRuntimeError`
- **Python 模块名**：`_core_compute`（由 `[lib].name` 指定）

### Lint / Format / Type（`pyproject.toml` 配置）

- **ruff**：`line-length = 120`，`target-version = py312`，扩展排除 `data/`、`logs/`、`knowledge/`
  - lint 选择：`F, E, W, UP`
  - 忽略：`E501, F401, F403`
  - 测试文件额外忽略 `F811`
  - format：`quote-style = "double"`，`indent-style = "space"`
- **mypy**：`python_version = "3.12"`，`ignore_missing_imports = true`，`strict = false`（起步，v4.0.3 返回注解 100%）；排除 `data/`、`logs/`、`knowledge/`、`tests/`；pre-commit 中限于 `modules/(screener|cli|data_sync|indicators/core|strategies/*.py)`
- **pre-commit**（9 个 hooks）：ruff + ruff-format + mypy + SKILL.md 12 项质量门 + 双轴评审（manual）+ check-merge-conflict + check-yaml + end-of-file-fixer + trailing-whitespace
- **Rust CI**：`cargo fmt --check` + `cargo clippy --workspace --all-targets --no-deps --exclude zt_bindings -- -D warnings` + `cargo test --workspace --exclude zt_bindings`（zt_bindings 有 PyO3 0.23→0.24 迁移遗留）

### 版本规则

严格遵循语义化版本（Semantic Versioning）：`MAJOR.MINOR.PATCH`

| 位 | 含义 | 示例 |
|----|------|------|
| MAJOR | 不兼容的 API 变更 | SKILL.md 心智模型重构、CLI API 不兼容变更、引入 Rust 内核（v4.0.0） |
| MINOR | 向后兼容的功能新增 | 新增战法/指标、新增 CLI 子命令、新增数据源 |
| PATCH | 向后兼容的 bug 修复和内部重构 | bug 修复、性能优化、技术债清理、文档更新 |

**版本发布策略**：
- **PATCH**：随时发布（bug 修复、小改进）
- **MINOR**：功能积累到一定程度后发布（每月/每季度）
- **MAJOR**：重大架构变更时发布（每年/每两年）

**注意**：技术债清理、内部重构属于 PATCH，不是 MINOR。避免版本号增长过快。

**近期版本脉络**（详见 `docs/CHANGELOG.md`）：
- **v4.0.3**：收尾技术债（版本号五处统一、USER_GUIDE 追平、性能优化 6.3x/2.4x、`core/errors.py` 统一错误码扩充至 50 个、`except Exception` 全部收窄、返回类型注解 100%、pandas 3.x spec 锁齐、PyO3 0.23 升级）
- **v4.0.2**：CLI ↔ Rust PyO3 桥（`_rust_bridge.py`、`_rust_compat.py::compute_func`、silent fallback）+ H2/H3/M1/M2/L5/L6 技术债清偿
- **v4.0.1**：PyO3 运行时打通（macOS LINKEDIT 修复、3 个 backtest binding、35 个 proptest）
- **v4.0.0**：核心计算链路迁至 Rust（PyO3 + Polars + Rayon，6 crate workspace）
- **v3.10.4**：发布前止血（版本号统一、文档追平、性能优化、统一错误码最小版）
- **v3.10.3**：组合回测策略权重按市场环境动态调整 + 各策略贡献度统计（`StrategyStats`）
- **v3.10.2**：组合回测参数 IS 网格搜索自动寻优（`portfolio_grid_search_optimize()`）
- **v3.10.1**：ATR 动态止损 + 移动止损（`core/atr.py`、`LoopConfig.atr_stop_*` / `trailing_stop_*`）
- **v3.10.0**：组合回测引擎多策略融合（B1/B2/SB1/长安并行 + 共振评分，`EntrySignal`）
- **v3.9.0**：技术债务清理（统一 `PerformanceMetrics` / `MarketRegime` / 路径与常量，新增 `core/paths.py`、`core/net.py`）
- **v3.8.2**：数据层统一 DB 优先读取
- **v3.8.1**：接入 Indevs 数据源
- **v3.7.x**：少妇战法 v1.0 验收工程化（含 walk_forward 真切片修复）

---

## 测试策略

### 测试架构

- **框架**：pytest（Python）+ cargo test（Rust）
- **配置**：`pyproject.toml` 中 `testpaths = ["tests"]`，默认 `-v --tb=short`
- **标记**：
  - `@pytest.mark.slow` 用于慢速端到端测试（如 self_optimizer 多轮），默认不跑
  - `@pytest.mark.realdata` 用于真实数据回归测试（需 `TUSHARE_TOKEN` + `RUN_REALDATA=true`），默认 skip
- **Fixture**：`tests/conftest.py` 提供
  - `mock_env_for_tests`：autouse，自动将环境变量 mock 到临时目录
  - `temp_db`：初始化好的临时数据库
  - `db_conn`：数据库连接
  - 另有 `state_with_interrupted_run`、`mock_monthly_reviews_with_poor_strategy` 等场景 fixture
- **数据工厂**：`make_kline_row()`、`make_daily_data()`、`generate_uptrend_klines()`、`generate_downtrend_klines()`、`generate_b1_scenario()`、`write_klines_to_db()`、`write_stock_basic()` 等
- **数据库隔离**：所有测试使用临时 SQLite 文件，互不干扰

### 测试覆盖范围（当前 98 个 .py 文件 + 1 个 .md）

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_database.py` | 路径解析、连接上下文、事务回滚、表初始化、幂等性 |
| `test_indicators.py` | 60+ 指标计算（MA/EMA/KDJ/MACD/背离/BBI/RSI/WR/布林带/量比/双线/单针/砖形图/B1B2/呼吸结构/SB1/沙漏/牛绳/蜈蚣图等） |
| `test_strategies.py` | B1/B2/B3/SB1/长安/四分之三阴量/娜娜/异动地量/出货五式等 |
| `test_screener.py` / `test_screener_p3.py` / `test_screener_data.py` / `test_screener_errors.py` | 选股评分、P3 指标接入评分、数据层、异常路径 |
| `test_backtest.py` / `test_backtest_errors.py` / `test_loop_engine.py` / `test_backtest_six_step.py` / `test_backtest_scorer.py` / `test_backtest_multistrategy.py` / `test_backtest_portfolio.py` / `test_e2e_multistrategy.py` | 回测框架、异常路径、六步闭环、多策略融合引擎（含策略贡献度统计） |
| `test_dynamic_stop_loss.py` | ATR 动态止损 + 移动止损（v3.10.1） |
| `test_portfolio_grid_search.py` | 组合参数网格寻优（v3.10.2） |
| `test_portfolio_diagnosis.py` | 持股检查、防卖飞、出货信号、战法匹配 |
| `test_watchlist.py` | 观察池增删改查、批量扫描 |
| `test_wave_theory.py` | 三波理论识别 |
| `test_kirin_detector.py` | 麒麟会四阶段 |
| `test_cli_screen.py` / `test_cli_subparser.py` / `test_cli_simulate.py` | CLI 子命令分发与参数解析 |
| `test_cli_uses_rust.py` | **CLI ↔ Rust PyO3 桥接测试（v4.0.2）**：Rust 可用/不可用/强制 Python/抛错降级/缓存行为 |
| `test_rust_compat.py` | **compat shim 单元测试**：`ZETTARANC_BACKTEST_IMPL` 切换逻辑 |
| `test_core.py` / `test_errors.py` | 公共模块（metrics/walk_forward/market_context/net/errors 50 个错误码） |
| `test_market_regime.py` | 市场状态机 |
| `test_data_sync.py` / `test_data_sync_extensions.py` / `test_datasource.py` / `test_indicator_cache.py` / `test_indevs_datasource.py` / `test_indevs_client_errors.py` | 数据层端到端、同步、数据源、指标缓存、Indevs 数据源与异常 |
| `test_trade_manager.py` / `test_trade_parser.py` | 交易记录 CRUD、口语化解析 |
| `test_intent_router.py` | 意图路由规则匹配 |
| `test_quality_check.py` | SKILL.md 12 项质量检查 |
| `test_rate_limiter.py` | 120次/分钟限流器 |
| `test_bridge_client.py` / `test_tushare_client.py` | Tushare 客户端与 bridge 降级网关 |
| `test_monitor.py` / `test_notifier.py` | 自选股监控与推送 |
| `test_tracking_system.py` | 自我改进跟踪池 |
| `test_self_optimizer_*.py` / `test_param_registry.py` / `test_mutator.py` / `test_scorer.py` / `test_break_signal.py` / `test_reflex_blacklist.py` / `test_backtest_scorer.py` | Darwin 自优化管线 |
| `test_setup_wizard.py` / `test_report.py` / `test_exam_rules.py` | 初始化向导、报告、考试规则 |
| `test_simulator*.py`（14 个文件） | 模拟器主入口、约束、成本、环境权重、指标、参数空间、共振、strategy_adapter、仓位、walk_forward、optimizer_report、narrator、errors |
| `test_statistics.py` | 统计检验框架 |
| `test_verify_*.py`（10 个文件） | v1.0 验收 CLI / gates / pipeline / pool / portfolio_engine / portfolio_walk_forward / registry_writer / report / scorer / walk_forward |
| `test_silent_except.py` | H3 静默 except 收敛验证（5 个 hot file） |
| `test_llm_providers_errors.py` | LLM 提供者异常路径 |
| `test_m4_*.py`（16 个文件） | **M4 异常收窄回归测试（v4.0.3）**：覆盖 16 个模块/子包的 `except Exception` → 具体异常类型收窄行为 |
| `test_indicators_realdata.py` | 真实 Tushare 数据指标回归（无 token 时 skip） |
| `test_routing.md` | 路由规则文档（非 .py，不被 pytest 收集） |

### 运行预期

```bash
$ python -m pytest tests/ -v
# 当前实测结果：1318 passed, 15 skipped（约 30 秒）

$ cd rust && cargo test --workspace --exclude zt_bindings
# 62/62 passed

$ cargo test -p zt_bindings --no-default-features
# 11/11 passed（pure-Rust 路径）
```

### CI 流水线（4 个 workflow）

| Workflow | 触发 | Jobs |
|---------|------|------|
| `test.yml` | push/PR 到 main | test（Python 3.12/3.13 矩阵）/ lint / type-check / quality-gate / e2e-realdata / pre-commit |
| `rust-ci.yml` | PR 改 rust/python/pyproject.toml | test-rust（cargo fmt/clippy/test，Ubuntu+macOS）/ test-python（maturin develop + smoke import） |
| `release.yml` | push `v*.*.*` tag | test（矩阵 + maturin build wheel）/ pypi-publish（OIDC Trusted Publishing）/ github-release / clawhub-publish |
| `e2e-cron.yml` | 每周一 02:00 UTC + 手动 | realdata-weekly（真实数据回归 + artifact 保留 30 天） |

---

## 文件修改优先级

1. **`SKILL.md`** —— 直接影响 Skill 表现，任何改动都需语料支撑
2. **`knowledge/*.md`** —— 知识文档，补充新语料或修正旧发现时更新
3. **`modules/*.py`** 与 **`rust/crates/`** —— 数据层/计算内核代码改动需同步更新测试
4. **`references/research/*.md`** —— 调研档案，新增语料源时更新
5. **`README.md` / `docs/CHANGELOG.md` / `AGENTS.md`** —— 项目对外文档，版本发布时同步更新
6. **`api/` / `frontend/`** —— Web 看板，仅在交互层需要改进时修改
7. **`scripts/`** —— 工具脚本，仅在数据管道或检查逻辑需要修改时修改

---

## 内容修改原则

1. **最小改动原则**：只改确实不准确的部分
2. **有依据**：任何改动都需要语料支撑，不能凭印象。优先来源：
   - zettaranc 本人直接产出（视频、直播、付费课、雪球专栏）
   - 权威媒体报道（澎湃新闻等）
   - 证券业协会公示资料
   - **不应作为主要依据**：知乎回答、非本人微信公众号、股吧/雪球帖子（除本人账号外）
3. **保持角色一致性**：修改后的回答仍需符合 zettaranc 的表达 DNA

### 风格验证清单

修改 `SKILL.md` 后，用以下问题自检：

- [ ] 是否用「我」而非「Z 哥认为...」？
- [ ] 是否包含职业背书开场？
- [ ] 是否分 1/2/3/4 点拆解？
- [ ] 是否用了具体数字或案例？
- [ ] 是否以金句或反问收尾？
- [ ] 是否避免跳出角色的表述？
- [ ] 交易建议是否包含具体的进场/止损/止盈规则？

---

## 安全与合规考虑

1. **免责声明**：`SKILL.md` 和 `README.md` 均包含明确免责声明——**不构成任何投资建议**。
2. **版权边界**：原始语料不提交到仓库。仓库中只保留粉丝整理的 Markdown 提炼文件和转写文本。
3. **敏感信息**：Tushare Token、API URL、LLM API Key、飞书 webhook 通过 `.env` 文件管理，**绝不硬编码**；`.env` 已加入 `.gitignore`。
4. **信息偏差标注**：`SKILL.md` 的「诚实边界」一节明确标注了公开表达与真实想法的差异。
5. **高风险动作**：Skill 不会代下单、转账或处理内幕信息；给出买卖建议时必须附加免责声明。
6. **语料截止期**：信息截止到调研时间（2026-04-18 及后续更新）。

---

## 常见任务速查

| 任务 | 操作 |
|------|------|
| 更新心智模型或交易规则 | 先查 `references/research/01-writings.md` 和 `05-decisions.md` → 修改 `SKILL.md` 与对应 `knowledge/*.md` → 运行 `corpus/quality_check.py SKILL.md` |
| 补充新语料 | 将新文章放入 `references/sources/articles/` → 更新对应 `references/research/*.md` → **不要**将原始语料加入 git |
| 新增 B 站视频 transcript | `python corpus/batch_download_bilibili.py && python corpus/batch_transcribe.py` |
| 发布新版本 | 更新 `SKILL.md` → 更新 `docs/CHANGELOG.md` → 同步 `README.md` 版本 badge → 同步 `pyproject.toml` 版本号 → 打 git tag（`release.yml` 自动发布 PyPI + GitHub Release） |
| 验证风格一致性 | 对照「风格验证清单」逐项检查 |
| 修复数据层 bug | 修改 `modules/*.py` → 补充/更新 `tests/test_*.py` → `pytest tests/ -v` |
| 修复 Rust 内核 bug | 修改 `rust/crates/**/*.rs` → 补充/更新 `rust/crates/*/tests/*.rs` → `cargo test --workspace --exclude zt_bindings` → `maturin develop --release` 重建 `_core_compute` |
| 接入新 Tushare 接口 | 修改 `modules/tushare_client.py` 或 `modules/data_sync.py` → 确认 `modules/database.py` 表结构支持 → 补充保存逻辑与测试 |
| 初始化全新环境 | `cp .env.example .env` → 填入 Token → `python -m modules.database` → `python -m modules.data_sync sync` → （可选）`cd rust/crates/bindings && maturin develop --release` → `pytest tests/ -v` |
| 运行 Web 看板 | 安装 `fastapi uvicorn pydantic-settings` → `zt-web` → `cd frontend && npm install && npm run dev` |
| 跑 Darwin 自优化 | `zt self-optimize run --target trading --rounds 3` |
| 跑少妇战法 v1.0 验收 | `zt verify v1.0 --limit 50 --days 300 --walk-forward` |
| 跑参数寻优（v1.0） | `python scripts/optimize_for_v10_verify.py --rounds 5 --stocks 100 --days 300` |
| 组合参数网格寻优（v3.10.2） | 调用 `modules/verify/portfolio_walk_forward.py::portfolio_grid_search_optimize()`（IS 网格搜索，OOS 验证；Rust 加速版在 `rust/crates/grid_search`） |
| 切换 Rust/Python 回测实现 | `export ZETTARANC_BACKTEST_IMPL=python`（强制 Python）或 `rust`（强制 Rust）或 `auto`（默认，自动降级） |

---

> Love and Share 🖤
