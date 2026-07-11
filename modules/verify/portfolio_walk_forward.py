"""
组合级 Walk-forward 验证（v3.7.7）

基于 PortfolioBacktestEngine 的组合净值序列做真切片：
  - IS 段：用训练窗口内的交易日跑组合回测
  - OOS 段：用测试窗口内的交易日跑组合回测
  - OOS/IS 比率 = OOS Sharpe / IS Sharpe

与单股 walk_forward_verify 的区别：
  - 单股版：每段对每只股票独立跑 backtest_shaofu_single，再平均 Sharpe
  - 组合版：每段跑整个 PortfolioBacktestEngine，从组合净值曲线计算指标
"""
from __future__ import annotations

import logging

from .pipeline import AggregateMetrics
from .portfolio_engine import PortfolioBacktestEngine, PortfolioBacktestResult, PortfolioConfig
from .walk_forward import WFResult, _make_splits

logger = logging.getLogger(__name__)


def portfolio_walk_forward_verify(
    ts_codes: list[str],
    days: int = 250,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    config: object | None = None,
    portfolio_config: PortfolioConfig | None = None,
) -> WFResult:
    """组合级 Walk-forward 验证

    Args:
        ts_codes: 候选股票池
        days: 总回测天数
        wf_train_days: IS 窗口长度
        wf_test_days: OOS 窗口长度
        config: LoopConfig（少妇战法参数）
        portfolio_config: PortfolioConfig（组合账户参数）

    Returns:
        WFResult（is_metrics / oos_metrics / oos_is_ratio / degraded）
    """
    engine = PortfolioBacktestEngine(
        portfolio_config=portfolio_config,
        loop_config=config,
    )

    klines_map, all_dates = engine.load_data(ts_codes, days)
    if not all_dates:
        logger.warning("组合 WF：无交易日数据，降级")
        return WFResult(splits=[], degraded=True)

    total_days = len(all_dates)
    splits = _make_splits(total_days, wf_train_days, wf_test_days)

    if len(splits) < 3:
        logger.warning(
            "组合 WF 切片数=%d < 3，降级为单次回测（不计算 OOS/IS）",
            len(splits),
        )
        return WFResult(splits=[], degraded=True)

    is_results: list[PortfolioBacktestResult] = []
    oos_results: list[PortfolioBacktestResult] = []

    for split in splits:
        is_start = all_dates[split.train_start]
        is_end = all_dates[split.train_end - 1]
        oos_start = all_dates[split.test_start]
        oos_end = all_dates[split.test_end - 1]

        logger.debug(
            "组合 WF 切片: IS[%s-%s] OOS[%s-%s]",
            is_start,
            is_end,
            oos_start,
            oos_end,
        )

        try:
            is_result = engine.run_with_data(
                klines_map,
                all_dates,
                start_date=is_start,
                end_date=is_end,
            )
            oos_result = engine.run_with_data(
                klines_map,
                all_dates,
                start_date=oos_start,
                end_date=oos_end,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("组合 WF 切片运行失败: %s", e)
            continue

        # 仅当段内有足够交易时才计入 Sharpe 等统计，避免 0 分母
        if is_result.total_trades >= 3:
            is_results.append(is_result)
        if oos_result.total_trades >= 3:
            oos_results.append(oos_result)

    is_metrics = _aggregate_portfolio_results(is_results)
    oos_metrics = _aggregate_portfolio_results(oos_results)

    oos_is_ratio = 0.0
    if is_metrics.sharpe > 0.001:
        oos_is_ratio = oos_metrics.sharpe / is_metrics.sharpe

    return WFResult(
        splits=splits,
        is_metrics=is_metrics,
        oos_metrics=oos_metrics,
        oos_is_ratio=oos_is_ratio,
        degraded=False,
    )


def _aggregate_portfolio_results(
    results: list[PortfolioBacktestResult],
) -> AggregateMetrics:
    """把多段组合回测结果聚合为 AggregateMetrics"""
    if not results:
        return AggregateMetrics()

    total_trades = sum(r.total_trades for r in results)
    wins = sum(r.win_count for r in results)
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    n = len(results)
    total_return = sum(r.total_return for r in results) / n
    annualized_return = sum(r.annualized_return for r in results) / n
    sharpe = sum(r.sharpe_ratio for r in results) / n
    calmar = sum(r.calmar for r in results) / n
    max_drawdown = max(r.max_drawdown for r in results) if results else 0.0

    return AggregateMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_return_pct=total_return,
        annualized_return=annualized_return,
        sharpe=sharpe,
        calmar=calmar,
        max_drawdown=max_drawdown,
    )


__all__ = [
    "portfolio_walk_forward_verify",
    "_aggregate_portfolio_results",
]
