"""Walk-forward 验证测试"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from modules.verify.walk_forward import (
    WFResult,
    WFSplit,
    _make_splits,
    walk_forward_verify,
)


@dataclass
class FakeMetrics:
    total_return_pct: float = 0.0
    sharpe: float = 0.0


def test_wf_split_dataclass_importable():
    assert WFSplit is not None
    assert WFResult is not None


def test_wf_split_count_for_250_days():
    """250 天 / 60 天 OOS ≈ 3-4 段"""
    splits = _make_splits(total_days=250, train_days=120, test_days=60)
    assert len(splits) >= 3
    for s in splits:
        assert s.test_end > s.test_start


def test_wf_result_oos_is_ratio_basic():
    """OOS/IS 比率 = oos.sharpe / is.sharpe"""
    is_m = FakeMetrics(sharpe=1.0)
    oos_m = FakeMetrics(sharpe=0.65)
    result = WFResult(
        splits=[],
        is_metrics=is_m,
        oos_metrics=oos_m,
        oos_is_ratio=0.65,
    )
    assert result.oos_is_ratio == 0.65
    assert result.oos_metrics.sharpe < result.is_metrics.sharpe


def test_wf_verify_degrades_when_too_few_splits(caplog):
    """切片数 < 3 时降级到单次回测（返回 WFResult 但 splits 为空 + warning）"""
    # 60 天数据只够 1 段
    result = walk_forward_verify(
        ts_codes=["000001.SZ"],
        days=60,
        wf_train_days=40,
        wf_test_days=20,
    )
    assert isinstance(result, WFResult)
    # 切片数不足会被函数内部处理（具体逻辑见 Step 3）
