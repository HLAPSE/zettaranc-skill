"""v1.0 验收适配的达尔文可调评分器

封装 verify_v10_pipeline 作为 fitness，方便 V2 hill-climb 寻优。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from modules.loop_engine import LoopConfig

logger = logging.getLogger(__name__)

# LoopConfig 的可调字段（与 v3.7.0 验收一致）
LOOP_CONFIG_FIELDS = (
    "j_threshold",
    "stop_loss_pct",
    "vol_shrink_threshold",
    "bbi_break_days",
    "min_holding_days",
    "lu_half",
    "position_pct",
)

# 留出模块属性，便于单元测试 patch；实际函数在 score() 内懒加载，避免循环 import。
verify_v10_pipeline = None


@dataclass
class V10ScoreResult:
    """单次评分的结果"""

    passed_count: int = 0
    total_count: int = 5
    sharpe: float = 0.0
    fit: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class V10VerifyScorer:
    """达尔文友好的 v1.0 验收适配器

    接口形态与 modules.self_optimizer.BacktestScorer 对齐：
      - 构造时接收 stock_pool / days / wf 等配置
      - score(params) 返回 V10ScoreResult（fit 为爬山适应度）
    """

    def __init__(
        self,
        stock_pool: list[str],
        days: int = 250,
        walk_forward: bool = True,
        wf_train_days: int = 120,
        wf_test_days: int = 60,
    ):
        self.stock_pool = stock_pool
        self.days = days
        self.walk_forward = walk_forward
        self.wf_train_days = wf_train_days
        self.wf_test_days = wf_test_days

    def score(self, params: dict[str, Any]) -> V10ScoreResult:
        """用 params（LoopConfig 字段子集）跑 verify_v10_pipeline，返回 V10ScoreResult。

        适应度公式：fit = passed_count + max(0, 0.1 * sharpe)
          - passed_count ∈ [0, 5] 是核心目标
          - sharpe 小幅保序（同等 passed_count 下 sharpe 高的赢）

        任何 verify 异常都被捕获，返回 fit=0 + error 文本，不阻断寻优。
        """
        global verify_v10_pipeline

        try:
            # 局部 import 避免循环；若测试已 patch 模块属性，则直接使用 patch 后对象。
            if verify_v10_pipeline is None:
                from modules.verify.pipeline import verify_v10_pipeline

            config = LoopConfig(**{k: v for k, v in params.items() if k in LOOP_CONFIG_FIELDS})
            result = verify_v10_pipeline(
                ts_codes=self.stock_pool,
                days=self.days,
                config=config,
                walk_forward=self.walk_forward,
                wf_train_days=self.wf_train_days,
                wf_test_days=self.wf_test_days,
            )

            gates = result.gates or {}
            passed_count = sum(1 for g in gates.values() if g.passed)
            total_count = len(gates)
            sharpe_gate = gates.get("sharpe")
            sharpe_value = sharpe_gate.value if sharpe_gate else 0.0
            fit = passed_count + max(0.0, 0.1 * sharpe_value)

            return V10ScoreResult(
                passed_count=passed_count,
                total_count=total_count,
                sharpe=sharpe_value,
                fit=fit,
                params=dict(params),
            )
        except Exception as e:  # noqa: BLE001 - 单次评分失败不应中断爬山
            logger.warning("V10VerifyScorer 评分异常: %s", e)
            return V10ScoreResult(
                passed_count=0,
                total_count=5,
                fit=0.0,
                params=dict(params),
                error=f"{type(e).__name__}: {e!s:.80}",
            )
