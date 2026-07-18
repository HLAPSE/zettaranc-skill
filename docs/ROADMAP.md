# 产品路线图

> 最后更新：2026-07-18  
> 当前版本：v4.0.0（Rust 内核）

## 版本号规定

- **MAJOR**：不兼容 API 变更（心智模型重构、CLI 不兼容变更）
- **MINOR**：向后兼容的功能新增（新战法/指标/CLI 子命令/数据源）
- **PATCH**：bug 修复、技术债清理、内部重构

> 严格遵循语义化版本（Semantic Versioning）。技术债清理属于 PATCH，不是 MINOR。

---

## 2026-07-16 重排说明

本次按代码现状重排迭代路线，原因：

1. **版本号不一致是发布阻塞**：`pyproject.toml` / `skill.json` / `SKILL.md` / README badge 四处版本互相打架，ClawHub 上架与一切正式发布都受影响 → 最先修（v3.10.4）
2. **告警基础设施已存在**：`modules/monitor.py` + `modules/notifier.py` 已实现自选股信号扫描与飞书推送，监控告警是"收尾"而非"新建"，成本低价值直接 → 先于分钟级数据
3. **分钟级数据有外部依赖不确定**：Tushare 分钟线接口需要高权限 token，能否可用未验证 → 先 spike 再排期
4. **传播产物依赖功能稳定 + 版本一致** → 与 v3.11.x 并行推进
5. **原「v4.0.0 Web 看板增强」非破坏性变更**，按 semver 规则应为 MINOR → 重编号为 v3.13.0；v4.0.0 保留给真正 MAJOR 的自动化交易接口

---

## 近期（0–2 个月）

### v4.0.0 Rust 内核（MAJOR）✅

**目标**：核心计算链路迁至 Rust（PyO3 + Polars + Rayon），预期提速 5–50×

**已完成**（本次会话）：
- [x] Rust workspace（6 crate）全部编译通过
- [x] `compute_atr` Rust 实现 + golden file byte-equal 验证（epsilon=1e-9）
- [x] 单策略回测引擎 + 3/3 单元测试
- [x] 组合回测引擎（rayon 并行）+ 3/3 单元测试
- [x] Walk-forward + 网格搜索（rayon 并行）+ 5/5 单元测试
- [x] 选股引擎（polars）+ 5/5 单元测试
- [x] compat shim（env-var `ZETTARANC_BACKTEST_IMPL` 切换）
- [x] GitHub Actions CI（macOS + Linux）
- [x] 测试基线快照（313 通过）

**待完成**（环境修复后）：
- [ ] PyO3 binding 运行时验证（macOS 15+ Mach-O 链接器 bug 修复后）
- [ ] 接入现有 CLI（`zt backtest` / `zt verify` / `zt screen`）
- [ ] benchmark 实测（计划 ≥8× / ≥10× / ≥30× / ≥5×）
- [ ] `_core_compute` dlopen 修复后立即可用，无需改 Rust 代码

详见 `docs/superpowers/specs/2026-07-18-rust-refactor-design.md`

### v3.10.4 技术债与文档收尾（PATCH）✅

**目标**：发布前止血——版本一致、文档追平、热点路径提速、错误处理有最小骨架

**功能清单**：
- [x] 版本号五处统一（pyproject / skill.json / SKILL.md×2 / README badge）+ 发布 Checklist（`docs/CONTRIBUTING.md`）
- [x] `docs/USER_GUIDE.md` 追平 v3.8–v3.10 功能
- [x] 性能优化：`precompute_market_contexts()` ~6.3x + `get_kline_dicts_batch()` ~2.2–2.4x（benchmark 指纹校验逐位一致）
- [x] 统一错误码最小版（`modules/core/errors.py`，试点 tushare_client / datasource）
- [x] 鲁班 P0 复核 + knowledge 索引修正

**实际工期**：1 天

---

### v3.11.0 监控告警闭环（MINOR）

**目标**：在现有 monitor/notifier 基础上收尾告警能力

**功能清单**：
- [ ] 止损/止盈触发告警（`trade_records` 持仓成本 + 最新价比对）
- [ ] 市场环境变化告警（regime 切换检测，STRONG → WEAK 等）
- [ ] 告警频率控制（冷却窗口 + 按级别去重）
- [ ] 邮件推送通道（`notifier.py` 扩展 SMTP）
- [ ] 自选股 B1/B2 信号监控（已有，补测试与文档）

**预计工期**：1 周

---

### v3.11.1 数据质量检查（MINOR）

**目标**：自动检测数据缺失、异常值

**功能清单**：
- [ ] 交易日数据缺失检测
- [ ] 价格跳变/成交量异常检测
- [ ] 自动重新拉取修复

**预计工期**：1 周

---

### 里程碑 M1：传播产物（与 v3.11.x 并行，非版本发布）

**目标**：把"独一份"的内在优势变成"看得见"的传播资产（鲁班打磨报告方案 B）

**功能清单**：
- [ ] 3 个展示产物：`zt analyze` 输出、`zt screen` 结果、`zt backtest` 资金曲线（GIF/截图，入 `assets/`）
- [ ] 一张可截图分享的「结果卡片」
- [ ] `test-prompts.json`（10 个典型场景，降低新用户开口成本）
- [ ] README 首屏重排：钩子 → 30 秒 websearch 体验 → 效果截图 → 完整安装

**预计工期**：3–5 天

---

## 中期（3–6 个月）

### v3.12.0 分钟级实时数据（MINOR）

**目标**：接入分钟级 K 线（1/5/15/30/60 分钟）

**前置 spike（2 天）**：
- [ ] 验证 Tushare 分钟线接口在当前 token 权限下是否可用
- [ ] 验证 Indevs Replay API 是否支持分钟级
- [ ] 结论不可行则降级为"盘中快照轮询"方案或取消（标注 ❌ 并说明原因）

**功能清单**：
- [ ] `minute_kline` 表设计 + 5 种分钟级别数据写入 DB
- [ ] 盘中信号检测

**预计工期**：spike 2 天 + 1–2 周

---

### 里程碑 M2：生态上架（非版本发布）

**功能清单**：
- [ ] ClawHub / skills.sh 上架（`skill.json` 元数据已随 v3.10.4 修正）
- [ ] 社区入口：issue 模板、联系方式

**预计工期**：2–3 天

---

### v3.13.0 Web 看板增强（MINOR，原"v4.0.0"重编号）

**目标**：`frontend/` 增加完整功能

**功能清单**：
- [ ] 策略回测可视化（资金曲线、交易记录）
- [ ] 持仓管理（当前持仓、历史交易）
- [ ] 信号实时推送
- [ ] 自定义策略参数 + 市场环境展示

**预计工期**：3–4 周

---

## 长期（6–12 个月）

### v4.0.0 自动化交易接口（MAJOR，合规前置）

**功能清单**：
- [ ] 券商 API 对接
- [ ] 风控检查（仓位、资金、黑名单）
- [ ] 下单前确认 + 交易日志

**风险提示**：⚠️ 需合规审查 · ⚠️ 需用户授权 · ⚠️ 需资金安全保障

**预计工期**：4–6 周

---

### v4.1.0 策略市场

**功能清单**：
- [ ] 策略上传/分享/评分/排名
- [ ] 一键导入 + 回测对比

**预计工期**：3–4 周

---

## 技术债务

### 高优先级

1. ~~文档完善~~ ✅ v3.10.4 完成（USER_GUIDE 追平、发布 Checklist）
2. ~~性能优化~~ ✅ v3.10.4 完成（precompute_market_contexts、批量查询）

### 中优先级

3. **类型注解** ⏳
   - 部分模块缺少类型注解
   - mypy 未全量开启
4. **错误处理** ⏳（v3.10.4 已建最小骨架）
   - 其余模块接入统一错误码
   - API 调用失败时静默返回 None 的收敛

### 低优先级

5. **依赖升级** ⏳
   - Python 3.10 → 3.12
   - pandas 版本升级
6. **CI/CD 优化** ⏳
   - 缺少自动化部署

---

## 历史阶段归档

### 阶段一：多策略融合（v3.10.x）✅ 已全部完成

- **v3.10.0 多策略融合引擎** ✅：`PortfolioBacktestEngine` 从 B1-only 改造为 B1 + B2 + SB1 + 长安并行检测
- **v3.10.1 动态止损策略** ✅：固定百分比止损 → ATR 动态止损 + 移动止损（`core/atr.py`）
- **v3.10.2 市场环境自适应参数** ✅：Walk-forward IS/OOS 网格搜索自动寻优（81 组合）
- **v3.10.3 验收补齐** ✅：`regime_strategy_weights` 环境动态调权 + `StrategyStats` 策略贡献度统计

---

## 版本发布记录

### v3.10.4 (2026-07-16) ✅
- 技术债与文档收尾：版本号五处统一、USER_GUIDE 追平（1388 行）、precompute_market_contexts ~6.3x + get_kline_dicts_batch ~2.2–2.4x、统一错误码最小版、鲁班 P0 复核
- 12 个新测试，全量 1179 passed

### v3.10.3 (2026-07-15) ✅
- 多策略融合引擎验收补齐：regime_strategy_weights 按环境动态调权
- LoopTrade.strategy_source 记录触发策略（支持多策略共振）
- StrategyStats + PortfolioBacktestResult.strategy_stats 贡献度统计
- 13 个新测试，全量 1167 passed

### v3.10.2 (2026-07-11) ✅
- 组合回测 IS/OOS 自动寻优（grid search 81 组合）

### v3.10.1 (2026-07-11) ✅
- ATR 动态止损 + 移动止损（trailing stop）

### v3.10.0 (2026-07-11) ✅
- 多策略融合引擎（B1/B2/SB1/长安 并行检测 + 综合评分排序）

### v3.9.0 (2026-07-11) ✅
- 技术债清理（地基工程）
- 统一 PerformanceMetrics / MarketRegime / 常量 / 路径
- 修复 backtest 架构问题
- 测试 1097 passed, 15 skipped

### v3.8.2 (2026-07-11) ✅
- 数据层 DB 优先读取架构改造

### v3.8.1 (2026-07-11) ✅
- Indevs Tushare Replay API 数据源接入

### v3.8.0 (2026-07-11) ✅
- 市场环境自适应择时（最小可用版）

### v3.7.7 (2026-07-11) ✅
- 组合级 Walk-forward 真切片

### v3.7.6 (2026-07-11) ✅
- 多指标分组选股池 + 组合回测引擎

---

## 维护说明

1. **更新频率**：每完成一个版本，更新「版本发布记录」
2. **状态更新**：开始开发时 ⏳ → 🚧；完成时 → ✅
3. **优先级调整**：根据用户反馈和市场变化调整
4. **新增需求**：在对应阶段添加，标注 ⏳
5. **取消功能**：标注 ❌ 并说明原因

---

> 💡 **提示**：这份路线图是活文档，会随着项目进展不断更新。
