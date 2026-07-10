"""
v1.0 验收统一管线

调用现有 backtest_shaofu_portfolio / metrics / param_registry，
不修改任何现有模块的内部逻辑。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from modules.backtest_six_step import backtest_shaofu_single
from modules.datasource import get_datasource
from modules.loop_engine import LoopConfig

logger = logging.getLogger(__name__)

MIN_KLINE_DAYS = 60  # 少于这个天数视为数据不足


@dataclass
class StockResult:
    """单股回测结果"""
    ts_code: str
    name: str
    trades: int
    win_rate: float
    return_pct: float
    sharpe: float
    max_drawdown: float
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class AggregateMetrics:
    """组合级聚合指标"""
    total_trades: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    annual_return_pct: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0


@dataclass
class GateResult:
    """单项硬指标判定结果"""
    name: str
    value: float
    threshold: float
    passed: bool
    message: str = ""


@dataclass
class VerifyResult:
    """v1.0 验收聚合结果"""
    per_stock: list[StockResult] = field(default_factory=list)
    aggregate: AggregateMetrics = field(default_factory=AggregateMetrics)
    gates: dict[str, GateResult] = field(default_factory=dict)
    config_used: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


def _load_klines_with_precheck(
    ts_codes: list[str],
    days: int,
) -> list[StockResult]:
    """
    加载 K 线 + 数据预检。
    返回 list[StockResult]，数据不足的股票标记 skipped=True。
    """
    ds = get_datasource(preferred="auto")
    results: list[StockResult] = []

    for code in ts_codes:
        try:
            klines = ds.get_kline_dicts(code, days=days)
            if not klines or len(klines) < MIN_KLINE_DAYS:
                results.append(
                    StockResult(
                        ts_code=code,
                        name="",
                        trades=0,
                        win_rate=0.0,
                        return_pct=0.0,
                        sharpe=0.0,
                        max_drawdown=0.0,
                        skipped=True,
                        skip_reason=f"K线<{MIN_KLINE_DAYS}天",
                    )
                )
                continue
            results.append(
                StockResult(
                    ts_code=code,
                    name="",
                    trades=0,
                    win_rate=0.0,
                    return_pct=0.0,
                    sharpe=0.0,
                    max_drawdown=0.0,
                    skipped=False,
                )
            )
        except Exception as e:  # noqa: BLE001 - 单股加载失败不应中断整个组合
            logger.warning("加载 %s 失败: %s", code, e)
            results.append(
                StockResult(
                    ts_code=code,
                    name="",
                    trades=0,
                    win_rate=0.0,
                    return_pct=0.0,
                    sharpe=0.0,
                    max_drawdown=0.0,
                    skipped=True,
                    skip_reason=f"加载异常: {e!s:.50}",
                )
            )

    return results


def _run_single_stock_backtest(
    ts_code: str,
    days: int,
    config: LoopConfig | None = None,
) -> StockResult:
    """调 backtest_shaofu_single 返回 StockResult

    任何回测异常都不抛出，整体捕获后返回 skipped=True 的 StockResult，
    保证组合回测中单股失败不会中断整个流水线。
    """
    try:
        # backtest_shaofu_single 返回 ShaofuBacktestResult（dataclass）
        result = backtest_shaofu_single(ts_code, days=days, config=config)
        # ShaofuBacktestResult 字段：total_trades, win_count, win_rate,
        # total_return, sharpe_ratio, max_drawdown, equity_curve
        return StockResult(
            ts_code=ts_code,
            name=getattr(result, "name", ""),
            trades=result.total_trades,
            win_rate=result.win_rate,
            return_pct=result.total_return,
            sharpe=result.sharpe_ratio,
            max_drawdown=result.max_drawdown,
            skipped=False,
        )
    except Exception as e:  # noqa: BLE001 - 单股回测失败不应中断整个组合
        logger.warning("回测 %s 失败: %s", ts_code, e)
        return StockResult(
            ts_code=ts_code,
            name="",
            trades=0,
            win_rate=0.0,
            return_pct=0.0,
            sharpe=0.0,
            max_drawdown=0.0,
            skipped=True,
            skip_reason=f"回测异常: {e!s:.50}",
        )


def verify_v10_pipeline(
    ts_codes: list[str],
    days: int = 250,
    config: LoopConfig | None = None,
    walk_forward: bool = False,  # Task 6 实现
    wf_train_days: int = 120,
    wf_test_days: int = 60,
) -> VerifyResult:
    """
    v1.0 验收流水线（完整版）：
    1. 加载 K 线（带数据预检）
    2. 逐股回测（调 backtest_shaofu_single）
    3. 聚合组合级指标
    4. （Task 5 加入 gates 判定）
    5. （Task 6 加入 walk_forward 分支）
    """
    logger.info(
        "verify_v10_pipeline 启动: stocks=%d, days=%d, wf=%s",
        len(ts_codes),
        days,
        walk_forward,
    )
    meta = {
        "ts_codes_count": len(ts_codes),
        "days": days,
        "walk_forward": walk_forward,
        "skipped_count": 0,
    }

    if not ts_codes:
        return VerifyResult(meta={**meta, "empty_input": True})

    # 1. 数据预检
    prechecked = _load_klines_with_precheck(ts_codes, days)
    skipped_count = sum(1 for r in prechecked if r.skipped)
    meta["skipped_count"] = skipped_count

    # 2. 逐股回测
    per_stock: list[StockResult] = []
    for pre in prechecked:
        if pre.skipped:
            per_stock.append(pre)
            continue
        result = _run_single_stock_backtest(pre.ts_code, days, config)
        per_stock.append(result)

    # 3. 聚合
    aggregate = _aggregate_metrics(per_stock, days)

    # 4. Gates 判定（Task 5）
    # 4.5 Walk-forward（如果启用，Task 6）
    wf_result = None
    if walk_forward and not meta.get("empty_input"):
        from .walk_forward import walk_forward_verify
        wf_result = walk_forward_verify(
            ts_codes=ts_codes,
            days=days,
            wf_train_days=wf_train_days,
            wf_test_days=wf_test_days,
            config=config,
        )
        meta["wf_degraded"] = wf_result.degraded
        meta["wf_splits"] = len(wf_result.splits)

    from .gates import check_gates
    gates = check_gates(aggregate, wf=wf_result)

    return VerifyResult(
        per_stock=per_stock,
        aggregate=aggregate,
        gates=gates,
        config_used=_config_to_dict(config),
        meta=meta,
    )


def _config_to_dict(config: LoopConfig | None) -> dict:
    """把 LoopConfig 序列化为 dict（便于 JSON 输出）"""
    if config is None:
        return {}
    return {
        "j_threshold": config.j_threshold,
        "stop_loss_pct": config.stop_loss_pct,
        "vol_shrink_threshold": config.vol_shrink_threshold,
        "bbi_break_days": config.bbi_break_days,
        "min_holding_days": config.min_holding_days,
        "lu_half": config.lu_half,
        "position_pct": config.position_pct,
    }


def _aggregate_metrics(per_stock: list[StockResult], days: int) -> AggregateMetrics:
    """从单股结果聚合到组合级 AggregateMetrics"""
    active = [r for r in per_stock if not r.skipped and r.trades > 0]
    if not active:
        return AggregateMetrics()

    total_trades = sum(r.trades for r in active)
    wins = sum(r.trades * r.win_rate for r in active)
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    # 加权平均收益（按交易数加权）
    return_pcts = [r.return_pct for r in active if r.trades > 0]
    total_return = sum(return_pcts) / len(return_pcts) if return_pcts else 0.0

    sharpes = [r.sharpe for r in active]
    avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0

    drawdowns = [r.max_drawdown for r in active]
    max_drawdown = max(drawdowns) if drawdowns else 0.0

    # 年化（粗略：days/250 折算）
    annual_return = total_return * (250 / max(days, 1))

    # Calmar = 年化收益 / 最大回撤
    calmar = annual_return / max_drawdown if max_drawdown > 0.001 else 0.0

    return AggregateMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_return_pct=total_return,
        annual_return_pct=annual_return,
        sharpe=avg_sharpe,
        calmar=calmar,
        max_drawdown=max_drawdown,
    )
