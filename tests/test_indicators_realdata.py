"""
P2-1 真实数据回归测试：自研指标 vs BaoStock 真实数据

策略：拉 600519.SH 最近 120 天的 K 线，验证自研指标计算不报错且结果合理。

- skipif：未设置 RUN_REALDATA=true 时跳过
- 验证：指标计算不抛异常，结果在合理范围内
"""

import os
from datetime import datetime, timedelta
import pandas as pd
import pytest
from dotenv import load_dotenv

load_dotenv()


# 整文件 skipif：未设置 RUN_REALDATA=true 时跳过
_RUN_REALDATA = os.environ.get("RUN_REALDATA", "").lower() == "true"
pytestmark = pytest.mark.skipif(
    not _RUN_REALDATA,
    reason="需设置 RUN_REALDATA=true 才能跑真实数据回归",
)

# 测试范围
REALDATA_TS_CODE = "600519.SH"
LOOKBACK_DAYS = 365


# ==================== Fixtures ====================


@pytest.fixture(scope="module")
def baostock_client():
    """获取 BaoStock 客户端"""
    from modules.baostock_client import get_client
    return get_client()


@pytest.fixture(scope="module")
def trade_dates() -> tuple:
    """返回 (start_date, end_date) YYYYMMDD 字符串"""
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=LOOKBACK_DAYS)
    return (
        start_dt.strftime("%Y%m%d"),
        end_dt.strftime("%Y%m%d"),
    )


@pytest.fixture(scope="module")
def kline_df(baostock_client, trade_dates) -> pd.DataFrame:
    """拉 600519.SH K 线"""
    start_date, end_date = trade_dates
    df = baostock_client.get_daily(REALDATA_TS_CODE, start_date, end_date)
    assert df is not None and len(df) > 0, f"无法拉取 {REALDATA_TS_CODE} K 线"
    df = df.sort_values("trade_date").reset_index(drop=True)
    return df


@pytest.fixture(scope="module")
def daily_data_list(kline_df):
    """将 DataFrame 转为 DailyData 列表"""
    from modules.indicators.data_layer import DailyData

    return [
        DailyData(
            ts_code=row["ts_code"],
            trade_date=row["trade_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            vol=row["vol"],
            amount=row.get("amount", 0),
            pct_chg=row.get("pct_chg", 0),
        )
        for _, row in kline_df.iterrows()
    ]


# ==================== 指标计算验证 ====================


def test_macd_computation_no_error(daily_data_list):
    """MACD 计算不抛异常"""
    from modules.indicators import calculate_macd

    difs, deas, hists = calculate_macd(daily_data_list)
    assert len(difs) == len(daily_data_list)
    assert len(deas) == len(daily_data_list)
    assert len(hists) == len(daily_data_list)


def test_macd_values_reasonable(daily_data_list):
    """MACD 值在合理范围内"""
    from modules.indicators import calculate_macd

    difs, deas, hists = calculate_macd(daily_data_list)
    # MACD DIF 应在价格的 ±10% 范围内
    max_close = max(d.close for d in daily_data_list)
    assert all(abs(d) < max_close * 0.1 for d in difs[-10:]), "MACD DIF 值异常"


def test_kdj_computation_no_error(daily_data_list):
    """KDJ 计算不抛异常"""
    from modules.indicators import calculate_kdj

    k_vals, d_vals, j_vals = calculate_kdj(daily_data_list)
    assert len(k_vals) == len(daily_data_list)
    assert len(d_vals) == len(daily_data_list)
    assert len(j_vals) == len(daily_data_list)


def test_kdj_values_in_range(daily_data_list):
    """KDJ K/D 值在 0-100 范围内"""
    from modules.indicators import calculate_kdj

    k_vals, d_vals, j_vals = calculate_kdj(daily_data_list)
    # K 和 D 应在 0-100 范围内（J 可以超出）
    assert all(0 <= k <= 100 for k in k_vals[-10:]), "KDJ K 值超出 0-100"
    assert all(0 <= d <= 100 for d in d_vals[-10:]), "KDJ D 值超出 0-100"


def test_rsi_computation_no_error(daily_data_list):
    """RSI 计算不抛异常"""
    from modules.indicators import calculate_rsi

    rsi6 = calculate_rsi(daily_data_list, period=6)
    rsi12 = calculate_rsi(daily_data_list, period=12)
    rsi24 = calculate_rsi(daily_data_list, period=24)
    assert len(rsi6) == len(daily_data_list)
    assert len(rsi12) == len(daily_data_list)
    assert len(rsi24) == len(daily_data_list)


def test_rsi_values_in_range(daily_data_list):
    """RSI 值在 0-100 范围内"""
    from modules.indicators import calculate_rsi

    rsi6 = calculate_rsi(daily_data_list, period=6)
    assert all(0 <= r <= 100 for r in rsi6[-10:]), "RSI 值超出 0-100"


def test_boll_computation_no_error(daily_data_list):
    """布林带计算不抛异常"""
    from modules.indicators import calculate_boll

    upper, mid, lower = calculate_boll(daily_data_list)
    assert len(upper) == len(daily_data_list)
    assert len(mid) == len(daily_data_list)
    assert len(lower) == len(daily_data_list)


def test_boll_values_ordering(daily_data_list):
    """布林带 upper > mid > lower"""
    from modules.indicators import calculate_boll

    upper, mid, lower = calculate_boll(daily_data_list)
    for u, m, l in zip(upper[-10:], mid[-10:], lower[-10:]):
        assert u >= m >= l, "布林带顺序异常: upper < mid 或 mid < lower"


def test_ma_computation_no_error(daily_data_list):
    """MA 计算不抛异常"""
    from modules.indicators import calculate_ma

    ma5 = calculate_ma(daily_data_list, period=5)
    ma10 = calculate_ma(daily_data_list, period=10)
    ma20 = calculate_ma(daily_data_list, period=20)
    assert len(ma5) == len(daily_data_list)
    assert len(ma10) == len(daily_data_list)
    assert len(ma20) == len(daily_data_list)
