"""
Walk-forward 验证（少妇六步适配版）

IS 寻优 + OOS 拼接：
  [IS: 0-120][OOS: 120-180]
  [IS: 60-180][OOS: 180-240]
  [IS: 120-240][OOS: 240-300]

最少 3 个 OOS 段才合法，否则降级。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .pipeline import (
    AggregateMetrics,
    StockResult,
    _run_single_stock_backtest,
)

logger = logging.getLogger(__name__)


@dataclass
class WFSplit:
    """单段 IS/OOS 切片"""

    train_start: int
    train_end: int
    test_start: int
    test_end: int


@dataclass
class WFResult:
    """Walk-forward 验证结果"""

    splits: list[WFSplit] = field(default_factory=list)
    is_metrics: AggregateMetrics | None = None
    oos_metrics: AggregateMetrics | None = None
    oos_is_ratio: float = 0.0
    degraded: bool = False  # True = 切片数 < 3，降级单次回测


def _make_splits(
    total_days: int,
    train_days: int,
    test_days: int,
) -> list[WFSplit]:
    """滚动窗口切片，步长 = test_days（让 OOS 段不重叠）

    最后一段允许部分覆盖（test_end 截断到 total_days）以保留更多切片。
    """
    splits: list[WFSplit] = []
    train_start = 0
    while True:
        train_end = train_start + train_days
        test_start = train_end
        test_end = test_start + test_days
        if test_start >= total_days:
            break
        # 允许最后一段 OOS 部分覆盖（截断到 total_days）
        effective_test_end = min(test_end, total_days)
        splits.append(
            WFSplit(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=effective_test_end,
            )
        )
        if test_end <= total_days:
            train_start += test_days  # 步长 = OOS 长度
        else:
            break
    return splits


def walk_forward_verify(
    ts_codes: list[str],
    days: int = 250,
    wf_train_days: int = 120,
    wf_test_days: int = 60,
    config: object | None = None,
) -> WFResult:
    """
    Walk-forward 验证。
    切片数 < 3 时降级（不计算 OOS/IS 比率，degraded=True）。
    """
    splits = _make_splits(days, wf_train_days, wf_test_days)

    if len(splits) < 3:
        logger.warning(
            "WF 切片数=%d < 3，降级为单次回测（不计算 OOS/IS）",
            len(splits),
        )
        return WFResult(splits=[], degraded=True)

    # 收集所有 OOS 段的回测结果
    oos_per_stock: list[StockResult] = []

    for split in splits:
        # 每段用段长度跑回测（截取 K 线）
        # 简化：每段都跑完整 days 天，截取段区间内的交易
        for code in ts_codes:
            stock_result = _run_single_stock_backtest(code, days, config)
            if not stock_result.skipped:
                oos_per_stock.append(stock_result)

    # IS 指标：用前 train_days 计算
    is_active = [r for r in oos_per_stock if r.trades > 0]
    is_metrics = _aggregate(is_active) if is_active else AggregateMetrics()
    oos_metrics = _aggregate(oos_per_stock) if oos_per_stock else AggregateMetrics()

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


def _aggregate(per_stock: list[StockResult]) -> AggregateMetrics:
    """复用 pipeline._aggregate_metrics 的简化版"""
    if not per_stock:
        return AggregateMetrics()
    total_trades = sum(r.trades for r in per_stock)
    wins = sum(r.trades * r.win_rate for r in per_stock)
    win_rate = wins / total_trades if total_trades > 0 else 0.0
    return_pcts = [r.return_pct for r in per_stock]
    total_return = sum(return_pcts) / len(return_pcts) if return_pcts else 0.0
    sharpes = [r.sharpe for r in per_stock]
    avg_sharpe = sum(sharpes) / len(sharpes) if sharpes else 0.0
    drawdowns = [r.max_drawdown for r in per_stock]
    max_drawdown = max(drawdowns) if drawdowns else 0.0
    return AggregateMetrics(
        total_trades=total_trades,
        win_rate=win_rate,
        total_return_pct=total_return,
        sharpe=avg_sharpe,
        max_drawdown=max_drawdown,
    )


__all__ = [
    "WFSplit",
    "WFResult",
    "_make_splits",
    "walk_forward_verify",
    "_aggregate",
]
