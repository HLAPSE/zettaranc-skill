"""
DataSource 协议与实现测试
"""

import pandas as pd
import pytest

from modules.bridge_client import BridgeConfig, get_bridge_config, is_bridge_available
from modules.datasource import (
    AkShareDataSource,
    BaoStockDataSource,
    BridgeDataSource,
    CompositeDataSource,
    DataSource,
    SqliteDataSource,
    get_datasource,
)


class FakeDataSource:
    """用于验证 Protocol 运行时检查的最小实现。"""

    @property
    def name(self) -> str:
        return "fake"

    def health_check(self) -> bool:
        return True

    def get_daily(self, ts_code: str, start_date: str | None = None, end_date: str | None = None):
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str):
        return None

    def get_realtime_quote(self, ts_codes: list[str]):
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str):
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str):
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None):
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str):
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        return []

    def get_limit_list(self, trade_date: str):
        return None

    def get_top_list(self, trade_date: str):
        return None

    def get_financial_indicator(self, ts_code: str, start_year: str = "2020"):
        return None

    def get_valuation(self, ts_code: str):
        return None

    def get_northbound_flow(self, days: int = 30):
        return None

    def get_margin_data(self, date: str = ""):
        return None

    def get_industry_board(self):
        return None

    def get_concept_board(self):
        return None

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        return []


def test_datasource_protocol_runtime_checkable():
    """Protocol 应支持运行时 isinstance 检查。"""
    assert isinstance(SqliteDataSource(), DataSource)
    assert isinstance(FakeDataSource(), DataSource)


def test_baostock_datasource_name():
    assert BaoStockDataSource().name == "baostock"


def test_akshare_datasource_name():
    assert AkShareDataSource().name == "akshare"


def test_bridge_datasource_name():
    assert BridgeDataSource().name == "bridge"


def test_sqlite_datasource_name():
    assert SqliteDataSource().name == "sqlite"


def test_composite_prefers_bridge_when_available(monkeypatch):
    monkeypatch.setattr("modules.datasource.is_bridge_available", lambda config=None: True)
    ds = CompositeDataSource()
    assert ds.health_check() is True


def test_composite_falls_back_to_sqlite(monkeypatch, temp_db, db_conn):
    from tests.conftest import write_klines_to_db, write_stock_basic

    monkeypatch.setattr("modules.bridge_client.is_bridge_available", lambda: False)
    # 使用唯一 ts_code 避免与已有数据冲突
    test_ts_code = "TEST0001.SH"
    write_stock_basic(db_conn, ts_code=test_ts_code, name="测试股票", industry="测试", market="主板")
    rows = [
        {
            "ts_code": test_ts_code,
            "trade_date": "20260101",
            "open": 1500.0,
            "high": 1520.0,
            "low": 1490.0,
            "close": 1510.0,
            "vol": 10000.0,
            "amount": 15100000.0,
            "pct_chg": 0.5,
        },
        {
            "ts_code": test_ts_code,
            "trade_date": "20260102",
            "open": 1510.0,
            "high": 1530.0,
            "low": 1500.0,
            "close": 1520.0,
            "vol": 11000.0,
            "amount": 16720000.0,
            "pct_chg": 0.6,
        },
    ]
    write_klines_to_db(db_conn, rows)

    ds = CompositeDataSource()
    data = ds.get_kline_dicts(test_ts_code, days=60)
    assert len(data) == 2
    assert data[0]["trade_date"] == "20260101"
    assert data[1]["trade_date"] == "20260102"


def test_get_datasource_factory():
    ds = get_datasource("sqlite")
    assert isinstance(ds, SqliteDataSource)
    assert ds.name == "sqlite"


def test_bridge_datasource_with_custom_config_does_not_mutate_global(monkeypatch):
    """传入自定义 BridgeConfig 不应修改全局 bridge 配置，且实例方法使用自身配置。"""
    from modules.bridge_client import set_bridge_config

    # 重置全局配置到已知状态
    set_bridge_config(host="127.0.0.1", port=8765, timeout=10, enabled="auto")
    custom = BridgeConfig(host="10.0.0.1", port=9999, timeout=3, enabled="never")

    captured: list[BridgeConfig | None] = []

    def capture_is_available(config=None):
        captured.append(config)
        return False  # 统一返回不可用，避免真实 HTTP 请求

    monkeypatch.setattr("modules.datasource.is_bridge_available", capture_is_available)

    ds = BridgeDataSource(config=custom)
    assert ds._config == custom

    # 健康检查应把实例配置透传下去
    ds.health_check()
    assert captured == [custom]

    # 全局配置保持不变
    cfg = get_bridge_config()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    assert cfg.timeout == 10
    assert cfg.enabled == "auto"


def test_bridge_datasource_default_uses_global_config(monkeypatch):
    """未传 config 时，BridgeDataSource 使用全局 bridge 配置。"""
    captured: list[BridgeConfig | None] = []

    def capture_is_available(config=None):
        captured.append(config)
        return False

    monkeypatch.setattr("modules.datasource.is_bridge_available", capture_is_available)
    ds = BridgeDataSource()
    ds.health_check()
    assert captured == [None]


def test_composite_auto_falls_back_to_sqlite(monkeypatch, temp_db, db_conn):
    """auto 策略在 bridge 不可用时回退到 SQLite。"""
    from tests.conftest import write_klines_to_db, write_stock_basic

    # bridge 不可用
    monkeypatch.setattr("modules.bridge_client.is_bridge_available", lambda config=None: False)

    # 使用唯一 ts_code 避免与已有数据冲突
    test_ts_code = "TEST0002.SH"
    write_stock_basic(db_conn, ts_code=test_ts_code, name="测试股票", industry="测试", market="主板")
    rows = [
        {
            "ts_code": test_ts_code,
            "trade_date": "20260101",
            "open": 1500.0,
            "high": 1520.0,
            "low": 1490.0,
            "close": 1510.0,
            "vol": 10000.0,
            "amount": 15100000.0,
            "pct_chg": 0.5,
        },
    ]
    write_klines_to_db(db_conn, rows)

    ds = CompositeDataSource(preferred="auto")
    data = ds.get_kline_dicts(test_ts_code, days=60)
    assert len(data) == 1
    assert data[0]["trade_date"] == "20260101"
