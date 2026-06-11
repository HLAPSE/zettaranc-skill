"""Phase 2 hill-climbing: ratchet + break_signal.

V1 范围: 仅实现 break_signal + RoundResult 数据类 + run_round 签名.
完整 ratchet 逻辑在 Task 7 实现.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class RoundResult:
    """单轮迭代结果."""

    round: int
    old_score: float
    new_score: float
    delta: float
    status: Literal["keep", "revert", "break"]
    violations: list[str]
    proposed_diff: str
    timestamp: str


def check_break_signal(history: list[RoundResult], threshold: float = 2.0) -> bool:
    """连续 2 轮 delta < threshold → True (触发 break)."""
    if len(history) < 2:
        return False
    return abs(history[-1].delta) < threshold and abs(history[-2].delta) < threshold


def run_round(
    round_n: int,
    old_score: float,
    target: str,
    history: list[RoundResult],
) -> RoundResult:
    """单轮迭代. V1 stub: 总是返回 break 避免误操作.

    Task 7 将实现完整逻辑.
    """
    return RoundResult(
        round=round_n,
        old_score=old_score,
        new_score=old_score,
        delta=0.0,
        status="break",
        violations=["v1_stub"],
        proposed_diff="(V1 stub - 完整实现在 Task 7)",
        timestamp=datetime.now().isoformat(),
    )
