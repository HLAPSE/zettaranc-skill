"""
核心公共模块（v3.9.0 技术债务清理）

提取各模块的公共逻辑，避免重复代码。

包含：
- walk_forward: 统一的 walk-forward 窗口切分逻辑
- market_context: 统一的市场环境判断
- metrics: 统一的绩效指标计算
"""

from .walk_forward import (
    WalkForwardSplit,
    make_walk_forward_splits,
)
from .market_context import (
    MarketRegime,
    MarketContext,
    classify_market_regime,
)
from .metrics import (
    PerformanceMetrics,
    calculate_metrics,
    calculate_performance_metrics,
    daily_returns,
    compute_drawdown,
    compute_sharpe,
    TRADING_DAYS_PER_YEAR,
)
from .net import disable_proxy
from .paths import DATA_DIR, REGISTRY_DIR, REPORTS_DIR

__all__ = [
    # walk_forward
    "WalkForwardSplit",
    "make_walk_forward_splits",
    # market_context
    "MarketRegime",
    "MarketContext",
    "classify_market_regime",
    # metrics
    "PerformanceMetrics",
    "calculate_metrics",
    "calculate_performance_metrics",
    "daily_returns",
    "compute_drawdown",
    "compute_sharpe",
    "TRADING_DAYS_PER_YEAR",
    # net
    "disable_proxy",
    # paths
    "DATA_DIR",
    "REGISTRY_DIR",
    "REPORTS_DIR",
]
