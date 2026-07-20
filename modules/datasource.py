"""
统一数据源抽象层

定义 DataSource Protocol，并封装 BaoStock、AkShare、Bridge、SQLite 以及自动回退的 Composite 数据源。
"""

import logging
import os
import sqlite3
from typing import Protocol, runtime_checkable

import pandas as pd
import requests

from .akshare_client import get_client as get_akshare_client
from .bridge_client import (
    BridgeConfig,
    get_all_stocks_bridge_first,
    get_daily_klines,
    is_bridge_available,
    set_bridge_config,
)
from .baostock_client import get_client as get_baostock_client
from .database import get_connection, save_klines
from modules.core.errors import ErrorCode, ZettarancError

logger = logging.getLogger(__name__)

# get_kline_dicts 的固定返回列（与 SELECT 顺序一致，用于元组转 dict）
_KLINE_COLUMNS = ("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount", "pct_chg")


@runtime_checkable
class DataSource(Protocol):
    """统一数据源协议，所有数据源实现必须满足此接口。"""

    @property
    def name(self) -> str:
        """数据源标识名（bridge / sqlite / composite 之一）"""
        ...

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        ...

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        ...

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        ...

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        ...

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        ...

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        ...

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        ...

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        ...

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        ...

    def get_limit_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取涨跌停股票列表"""
        ...

    def get_top_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取龙虎榜数据"""
        ...

    def get_financial_indicator(self, ts_code: str, start_year: str = "2020") -> pd.DataFrame | None:
        """获取财务分析指标（ROE/ROA/毛利率/净利率等）"""
        ...

    def get_valuation(self, ts_code: str) -> pd.DataFrame | None:
        """获取个股估值分析（PE/PB/股息率等）"""
        ...

    def get_northbound_flow(self, days: int = 30) -> pd.DataFrame | None:
        """获取北向资金历史流向"""
        ...

    def get_margin_data(self, date: str = "") -> pd.DataFrame | None:
        """获取融资融券汇总数据"""
        ...

    def get_industry_board(self) -> pd.DataFrame | None:
        """获取行业板块实时行情"""
        ...

    def get_concept_board(self) -> pd.DataFrame | None:
        """获取概念板块实时行情"""
        ...

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（含缓存与回退）"""
        ...


class AkShareDataSource:
    """AkShare 数据源封装（免费数据源，无需 token）。

    用于补充 BaoStock 不支持的数据：
    - 资金流向（get_moneyflow）
    - 实时行情（get_realtime_quote）
    - 涨跌停列表（get_limit_list）
    - 龙虎榜（get_top_list）
    """

    def __init__(self) -> None:
        self._client = get_akshare_client()

    @property
    def name(self) -> str:
        return "akshare"

    def health_check(self) -> bool:
        return self._client.check_connection()

    def get_daily(
        self, ts_code: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame | None:
        """AkShare 日线（未实现，由 BaoStock 处理）"""
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """AkShare 指数日线（未实现，由 BaoStock 处理）"""
        return None

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照"""
        return self._client.get_realtime_quote(ts_codes)

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向"""
        return self._client.get_moneyflow(ts_code, trade_date)

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """AkShare 不直接提供 daily_basic，返回 None 由 BaoStock 处理"""
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """AkShare 股票基础信息（未实现，由 BaoStock 处理）"""
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """AkShare 交易日历（未实现，由 BaoStock 处理）"""
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """AkShare 股票列表（未实现，由 BaoStock 处理）"""
        return []

    def get_limit_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取涨跌停股票列表"""
        return self._client.get_limit_list(trade_date)

    def get_top_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取龙虎榜数据"""
        return self._client.get_top_list(trade_date)

    def get_financial_indicator(self, ts_code: str, start_year: str = "2020") -> pd.DataFrame | None:
        """获取财务分析指标"""
        return self._client.get_financial_indicator(ts_code, start_year)

    def get_valuation(self, ts_code: str) -> pd.DataFrame | None:
        """获取个股估值分析"""
        return self._client.get_valuation(ts_code)

    def get_northbound_flow(self, days: int = 30) -> pd.DataFrame | None:
        """获取北向资金历史流向"""
        return self._client.get_northbound_flow(days)

    def get_margin_data(self, date: str = "") -> pd.DataFrame | None:
        """获取融资融券汇总数据"""
        return self._client.get_margin_data(date)

    def get_industry_board(self) -> pd.DataFrame | None:
        """获取行业板块实时行情"""
        return self._client.get_industry_board()

    def get_concept_board(self) -> pd.DataFrame | None:
        """获取概念板块实时行情"""
        return self._client.get_concept_board()

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """AkShare K 线（未实现，由 BaoStock 处理）"""
        return []


class BaoStockDataSource:
    """BaoStock 数据源封装（免费数据源，无需注册）。

    作为主力数据源，提供：
    - 日线/周线/月线/分钟线行情（含 PE/PB/PS/换手率）
    - 指数行情
    - 股票列表（含行业分类）
    - 交易日历
    """

    def __init__(self) -> None:
        self._client = get_baostock_client()

    @property
    def name(self) -> str:
        return "baostock"

    def health_check(self) -> bool:
        return self._client.check_connection()

    def get_daily(
        self, ts_code: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame | None:
        return self._client.get_daily(ts_code, start_date or "", end_date or "")

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        return self._client.get_index_daily(ts_code, start_date, end_date)

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """BaoStock 不支持实时行情，返回 None 由 AkShare 处理"""
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """BaoStock 不支持资金流向，返回 None 由 AkShare 处理"""
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        return self._client.get_daily_basic(ts_code, start_date, end_date)

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        return self._client.get_stock_basic(ts_code, name)

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        return self._client.get_trade_cal(exchange, start_date, end_date)

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        return self._client.get_stock_list(exchange)

    def get_limit_list(self, trade_date: str) -> pd.DataFrame | None:
        """BaoStock 不支持涨跌停列表，返回 None 由 AkShare 处理"""
        return None

    def get_top_list(self, trade_date: str) -> pd.DataFrame | None:
        """BaoStock 不支持龙虎榜，返回 None 由 AkShare 处理"""
        return None

    def get_financial_indicator(self, ts_code: str, start_year: str = "2020") -> pd.DataFrame | None:
        """获取财务分析指标（BaoStock 提供基础财务数据）"""
        return self._client.get_financial_data(ts_code, start_year)

    def get_valuation(self, ts_code: str) -> pd.DataFrame | None:
        """BaoStock 不提供个股估值分析，返回 None 由 AkShare 处理"""
        return None

    def get_northbound_flow(self, days: int = 30) -> pd.DataFrame | None:
        """BaoStock 不支持北向资金，返回 None 由 AkShare 处理"""
        return None

    def get_margin_data(self, date: str = "") -> pd.DataFrame | None:
        """BaoStock 不支持融资融券，返回 None 由 AkShare 处理"""
        return None

    def get_industry_board(self) -> pd.DataFrame | None:
        """BaoStock 不提供板块行情，返回 None 由 AkShare 处理"""
        return None

    def get_concept_board(self) -> pd.DataFrame | None:
        """BaoStock 不提供概念板块，返回 None 由 AkShare 处理"""
        return None

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        return self._client.get_kline_dicts(ts_code, days, start_date, end_date)


class BridgeDataSource:
    """Data Bridge HTTP API 数据源封装。

    支持传入实例级 ``BridgeConfig``，不会修改全局 bridge 配置。
    若未传 config，则使用当前全局配置。
    """

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self._config = config

    @property
    def name(self) -> str:
        """数据源标识名（bridge / sqlite / composite 之一）"""
        return "bridge"

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        return is_bridge_available(self._config)

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        return None

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        return get_all_stocks_bridge_first(exchange, config=self._config)

    def get_limit_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取涨跌停股票列表"""
        return None

    def get_top_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取龙虎榜数据"""
        return None

    def get_financial_indicator(self, ts_code: str, start_year: str = "2020") -> pd.DataFrame | None:
        """获取财务分析指标"""
        return None

    def get_valuation(self, ts_code: str) -> pd.DataFrame | None:
        """获取个股估值分析"""
        return None

    def get_northbound_flow(self, days: int = 30) -> pd.DataFrame | None:
        """获取北向资金历史流向"""
        return None

    def get_margin_data(self, date: str = "") -> pd.DataFrame | None:
        """获取融资融券汇总数据"""
        return None

    def get_industry_board(self) -> pd.DataFrame | None:
        """获取行业板块实时行情"""
        return None

    def get_concept_board(self) -> pd.DataFrame | None:
        """获取概念板块实时行情"""
        return None

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（含缓存与回退）"""
        return get_daily_klines(ts_code, days=days, start_date=start_date, end_date=end_date, config=self._config)


class SqliteDataSource:
    """本地 SQLite 数据源封装。"""

    @property
    def name(self) -> str:
        """数据源标识名（bridge / sqlite / composite 之一）"""
        return "sqlite"

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        try:
            with get_connection() as conn:
                conn.execute("SELECT 1")
            return True
        except (sqlite3.Error, OSError) as e:
            # 窄化：仅捕获 DB / OS 异常，健康检查返回 False 让上层选择其他源
            logger.warning("[datasource] SqliteDataSource.health_check 失败: %s", e)
            return False

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        return None

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        return None

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        return None

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        return None

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        with get_connection() as conn:
            cursor = conn.cursor()
            sql = "SELECT ts_code, name, industry, market FROM stock_basic"
            params: list = []
            if exchange:
                sql += " WHERE exchange = ?"
                params.append(exchange)
            sql += " ORDER BY ts_code"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_limit_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取涨跌停股票列表"""
        return None

    def get_top_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取龙虎榜数据"""
        return None

    def get_financial_indicator(self, ts_code: str, start_year: str = "2020") -> pd.DataFrame | None:
        """获取财务分析指标"""
        return None

    def get_valuation(self, ts_code: str) -> pd.DataFrame | None:
        """获取个股估值分析"""
        return None

    def get_northbound_flow(self, days: int = 30) -> pd.DataFrame | None:
        """获取北向资金历史流向"""
        return None

    def get_margin_data(self, date: str = "") -> pd.DataFrame | None:
        """获取融资融券汇总数据"""
        return None

    def get_industry_board(self) -> pd.DataFrame | None:
        """获取行业板块实时行情"""
        return None

    def get_concept_board(self) -> pd.DataFrame | None:
        """获取概念板块实时行情"""
        return None

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（含缓存与回退）"""
        with get_connection() as conn:
            # sqlite3.Row 构造开销大，批量逐股调用场景下用裸元组 + zip 转 dict 更快
            conn.row_factory = None
            cursor = conn.cursor()
            params: list = [ts_code]
            sql = """
                SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
                FROM daily_kline
                WHERE ts_code = ?
            """
            if start_date:
                sql += " AND trade_date >= ?"
                params.append(start_date)
            if end_date:
                sql += " AND trade_date <= ?"
                params.append(end_date)
            sql += " ORDER BY trade_date DESC"
            if not start_date and days > 0:
                sql += " LIMIT ?"
                params.append(days)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [dict(zip(_KLINE_COLUMNS, row)) for row in reversed(rows)]

    def get_kline_dicts_batch(
        self,
        ts_codes: list[str],
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, list[dict]]:
        """批量获取多只股票的 K 线：共享一个连接逐股查询，省去逐股开关连接的开销。

        每只股票的 SQL 与 get_kline_dicts 完全一致（行为不变），只是复用连接。
        返回 {ts_code: [K 线 dict 升序]}，无数据的股票对应空列表。
        """
        result: dict[str, list[dict]] = {code: [] for code in ts_codes}
        if not ts_codes:
            return result
        with get_connection() as conn:
            # sqlite3.Row 构造开销大，批量场景下用裸元组 + zip 转 dict 更快
            conn.row_factory = None
            cursor = conn.cursor()
            for ts_code in ts_codes:
                params: list = [ts_code]
                sql = """
                    SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
                    FROM daily_kline
                    WHERE ts_code = ?
                """
                if start_date:
                    sql += " AND trade_date >= ?"
                    params.append(start_date)
                if end_date:
                    sql += " AND trade_date <= ?"
                    params.append(end_date)
                sql += " ORDER BY trade_date DESC"
                if not start_date and days > 0:
                    sql += " LIMIT ?"
                    params.append(days)
                cursor.execute(sql, params)
                result[ts_code] = [dict(zip(_KLINE_COLUMNS, row)) for row in reversed(cursor.fetchall())]
        return result


class CompositeDataSource:
    """组合数据源：按配置优先级自动回退。

    数据源优先级（auto 模式）：
    BaoStock（主力：日线/指数/股票列表/交易日历/基础指标）
      → AkShare（补充：资金流向/实时行情/涨跌停/龙虎榜）
      → Bridge（HTTP 缓存）
      → SQLite（离线兜底）
    """

    VALID_PREFERRED = ("auto", "bridge", "sqlite", "akshare", "baostock")

    def __init__(self, preferred: str = "auto") -> None:
        if preferred not in self.VALID_PREFERRED:
            raise ZettarancError(
                ErrorCode.INVALID_PARAM,
                f"不支持的数据源: {preferred}，仅支持 {' / '.join(self.VALID_PREFERRED)}",
            )
        self._preferred = preferred
        self._baostock = BaoStockDataSource()
        self._akshare = AkShareDataSource()
        self._bridge = BridgeDataSource()
        self._sqlite = SqliteDataSource()

    @property
    def name(self) -> str:
        return f"composite({self._preferred})"

    def health_check(self) -> bool:
        """检查数据源连通性；返回 True 表示可用"""
        if self._preferred == "bridge":
            return self._bridge.health_check()
        if self._preferred == "sqlite":
            return self._sqlite.health_check()
        if self._preferred == "akshare":
            return self._akshare.health_check()
        if self._preferred == "baostock":
            return self._baostock.health_check()
        return (
            self._baostock.health_check()
            or self._akshare.health_check()
            or self._bridge.health_check()
            or self._sqlite.health_check()
        )

    def get_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股日线行情（OHLCV + 涨跌幅）"""
        if self._preferred == "baostock":
            return self._baostock.get_daily(ts_code, start_date, end_date)
        if self._preferred == "akshare":
            return self._akshare.get_daily(ts_code, start_date, end_date)
        # auto 模式：优先 BaoStock
        result = self._baostock.get_daily(ts_code, start_date, end_date)
        if result is not None:
            return result
        return self._akshare.get_daily(ts_code, start_date, end_date)

    def get_index_daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取指数日线行情"""
        if self._preferred == "baostock":
            return self._baostock.get_index_daily(ts_code, start_date, end_date)
        if self._preferred == "akshare":
            return self._akshare.get_index_daily(ts_code, start_date, end_date)
        result = self._baostock.get_index_daily(ts_code, start_date, end_date)
        if result is not None:
            return result
        return self._akshare.get_index_daily(ts_code, start_date, end_date)

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取实时行情快照（多只股票批量查询）"""
        if self._preferred == "baostock":
            return self._akshare.get_realtime_quote(ts_codes)
        if self._preferred == "akshare":
            return self._akshare.get_realtime_quote(ts_codes)
        # auto 模式：优先 AkShare
        result = self._akshare.get_realtime_quote(ts_codes)
        if result is not None:
            return result
        return None

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（特大单 / 大单 / 中单 / 小单）"""
        if self._preferred == "baostock":
            return self._akshare.get_moneyflow(ts_code, trade_date)
        if self._preferred == "akshare":
            return self._akshare.get_moneyflow(ts_code, trade_date)
        # auto 模式：优先 AkShare
        result = self._akshare.get_moneyflow(ts_code, trade_date)
        if result is not None:
            return result
        return None

    def get_daily_basic(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取个股每日基础指标（换手率 / PE / PB / 总市值等）"""
        if self._preferred == "baostock":
            return self._baostock.get_daily_basic(ts_code, start_date, end_date)
        if self._preferred == "akshare":
            return self._akshare.get_daily_basic(ts_code, start_date, end_date)
        # auto 模式：优先 BaoStock
        result = self._baostock.get_daily_basic(ts_code, start_date, end_date)
        if result is not None:
            return result
        return self._akshare.get_daily_basic(ts_code, start_date, end_date)

    def get_stock_basic(self, ts_code: str | None = None, name: str | None = None) -> pd.DataFrame | None:
        """获取股票基础信息（行业 / 上市日期 / 股本等）"""
        if self._preferred == "baostock":
            return self._baostock.get_stock_basic(ts_code, name)
        if self._preferred == "akshare":
            return self._akshare.get_stock_basic(ts_code, name)
        result = self._baostock.get_stock_basic(ts_code, name)
        if result is not None:
            return result
        return self._akshare.get_stock_basic(ts_code, name)

    def get_trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame | None:
        """获取交易日历（指定交易所）"""
        if self._preferred == "baostock":
            return self._baostock.get_trade_cal(exchange, start_date, end_date)
        if self._preferred == "akshare":
            return self._akshare.get_trade_cal(exchange, start_date, end_date)
        result = self._baostock.get_trade_cal(exchange, start_date, end_date)
        if result is not None:
            return result
        return self._akshare.get_trade_cal(exchange, start_date, end_date)

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表（按交易所）"""
        sources: list[DataSource] = []
        if self._preferred == "auto":
            sources = [self._baostock, self._akshare, self._bridge, self._sqlite]
        elif self._preferred == "bridge":
            sources = [self._bridge]
        elif self._preferred == "sqlite":
            sources = [self._sqlite]
        elif self._preferred == "akshare":
            sources = [self._akshare]
        elif self._preferred == "baostock":
            sources = [self._baostock]

        for source in sources:
            try:
                data = source.get_stock_list(exchange)
                if data:
                    return data
            except (
                requests.RequestException,
                sqlite3.Error,
                OSError,
                ValueError,
                KeyError,
                ZettarancError,
            ) as e:
                logger.warning(
                    "[datasource] CompositeDataSource.get_stock_list 源 %s 失败: %s",
                    getattr(source, "name", source.__class__.__name__),
                    e,
                )
                continue
        return []

    def get_limit_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取涨跌停股票列表（优先 AkShare）"""
        if self._preferred == "baostock":
            return self._akshare.get_limit_list(trade_date)
        if self._preferred == "akshare":
            return self._akshare.get_limit_list(trade_date)
        return self._akshare.get_limit_list(trade_date)

    def get_top_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取龙虎榜数据（优先 AkShare）"""
        if self._preferred == "baostock":
            return self._akshare.get_top_list(trade_date)
        if self._preferred == "akshare":
            return self._akshare.get_top_list(trade_date)
        return self._akshare.get_top_list(trade_date)

    def get_financial_indicator(self, ts_code: str, start_year: str = "2020") -> pd.DataFrame | None:
        """获取财务分析指标（优先 AkShare，BaoStock 补充）"""
        if self._preferred == "baostock":
            return self._baostock.get_financial_indicator(ts_code, start_year)
        if self._preferred == "akshare":
            return self._akshare.get_financial_indicator(ts_code, start_year)
        result = self._akshare.get_financial_indicator(ts_code, start_year)
        if result is not None:
            return result
        return self._baostock.get_financial_indicator(ts_code, start_year)

    def get_valuation(self, ts_code: str) -> pd.DataFrame | None:
        """获取个股估值分析（优先 AkShare）"""
        if self._preferred == "baostock":
            return self._baostock.get_valuation(ts_code)
        if self._preferred == "akshare":
            return self._akshare.get_valuation(ts_code)
        return self._akshare.get_valuation(ts_code)

    def get_northbound_flow(self, days: int = 30) -> pd.DataFrame | None:
        """获取北向资金历史流向（仅 AkShare）"""
        return self._akshare.get_northbound_flow(days)

    def get_margin_data(self, date: str = "") -> pd.DataFrame | None:
        """获取融资融券汇总数据（仅 AkShare）"""
        return self._akshare.get_margin_data(date)

    def get_industry_board(self) -> pd.DataFrame | None:
        """获取行业板块实时行情（仅 AkShare）"""
        return self._akshare.get_industry_board()

    def get_concept_board(self) -> pd.DataFrame | None:
        """获取概念板块实时行情（仅 AkShare）"""
        return self._akshare.get_concept_board()

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线数据，优先从 DB 读取，DB 没有时调 API 并缓存"""
        # 1. 先查 DB
        with get_connection() as conn:
            conn.row_factory = None
            cursor = conn.cursor()
            sql = """
                SELECT ts_code, trade_date, open, high, low, close, vol, amount, pct_chg
                FROM daily_kline
                WHERE ts_code = ?
            """
            params: list = [ts_code]

            if start_date:
                sql += " AND trade_date >= ?"
                params.append(start_date)
            if end_date:
                sql += " AND trade_date <= ?"
                params.append(end_date)

            sql += " ORDER BY trade_date DESC"

            if not start_date and days > 0:
                sql += " LIMIT ?"
                params.append(days)

            cursor.execute(sql, params)
            rows = cursor.fetchall()

        if rows:
            records = [dict(zip(_KLINE_COLUMNS, row)) for row in rows]
            records.reverse()
            return records

        # 2. DB 没有数据，调 API
        sources: list[DataSource] = []
        if self._preferred == "auto":
            sources = [self._baostock, self._akshare, self._bridge, self._sqlite]
        elif self._preferred == "bridge":
            sources = [self._bridge]
        elif self._preferred == "sqlite":
            sources = [self._sqlite]
        elif self._preferred == "akshare":
            sources = [self._akshare]
        elif self._preferred == "baostock":
            sources = [self._baostock]

        for source in sources:
            try:
                data = source.get_kline_dicts(ts_code, days=days, start_date=start_date, end_date=end_date)
                if data:
                    save_klines(data)
                    return data
            except (
                requests.RequestException,
                sqlite3.Error,
                OSError,
                ValueError,
                KeyError,
                ZettarancError,
            ) as e:
                logger.warning(
                    "[datasource] CompositeDataSource.get_kline_dicts 源 %s 失败 %s: %s",
                    getattr(source, "name", source.__class__.__name__),
                    ts_code,
                    e,
                )
                continue
        return []

    def get_kline_dicts_batch(
        self,
        ts_codes: list[str],
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, list[dict]]:
        """批量获取多只股票的 K 线：DB 共享连接批量查询优先，缺失的股票逐只回退外部源。"""
        result = self._sqlite.get_kline_dicts_batch(ts_codes, days=days, start_date=start_date, end_date=end_date)
        for code in ts_codes:
            if not result.get(code):
                result[code] = self.get_kline_dicts(code, days=days, start_date=start_date, end_date=end_date)
        return result


# ---------------------------------------------------------------------------
# dict ↔ DailyData 转换工具
# ---------------------------------------------------------------------------


def dict_to_daily(klines: list[dict] | list) -> list:
    """将 dict 格式 K 线列表转换为 ``DailyData`` 列表。

    若输入已是 ``DailyData`` 列表则直接返回副本。
    同时映射基础字段与派生形态字段（is_rise / is_beidou 等），
    供 strategies / screener / portfolio_diagnosis 等模块统一使用。
    """
    from .indicators import DailyData

    if not klines:
        return []
    if isinstance(klines[0], DailyData):
        return list(klines)

    result = []
    for i, row in enumerate(klines):
        prev_close = float(klines[i - 1]["close"]) if i > 0 else float(row["close"])
        close = float(row["close"])
        vol = float(row["vol"])
        prev_vol = float(klines[i - 1]["vol"]) if i > 0 else vol
        result.append(
            DailyData(
                ts_code=str(row["ts_code"]),
                trade_date=str(row["trade_date"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=close,
                vol=vol,
                amount=float(row.get("amount", close * vol)),
                pct_chg=float(row.get("pct_chg", 0.0)),
                prev_close=prev_close,
                is_rise=row.get("is_rise", close > prev_close),
                is_beidou=row.get("is_beidou", vol >= prev_vol * 2 if prev_vol > 0 else False),
                is_suoliang=row.get("is_suoliang", vol <= prev_vol * 0.5 if prev_vol > 0 else False),
                is_jiayin=row.get("is_jiayin", close < float(row["open"]) and close > prev_close),
                is_yinxian=row.get("is_yinxian", close < prev_close),
                is_fangliang_yinxian=row.get(
                    "is_fangliang_yinxian",
                    close < prev_close and vol > prev_vol * 1.5 if prev_vol > 0 else False,
                ),
            )
        )
    return result


def daily_to_dict(klines: list) -> list[dict]:
    """将 ``DailyData`` 列表转为符合战法检测需要的 dict 格式列表。"""
    result = []
    for i, k in enumerate(klines):
        prev_close = klines[i - 1].close if i > 0 else k.close
        prev_vol = klines[i - 1].vol if i > 0 else k.vol

        result.append(
            {
                "ts_code": k.ts_code,
                "trade_date": k.trade_date,
                "open": k.open,
                "high": k.high,
                "low": k.low,
                "close": k.close,
                "vol": k.vol,
                "amount": k.amount,
                "pct_chg": k.pct_chg,
                "prev_close": prev_close,
                "prev_vol": prev_vol,
                "is_rise": k.close > prev_close,
                "is_beidou": k.vol >= prev_vol * 2 if prev_vol > 0 else False,
                "is_suoliang": k.vol <= prev_vol * 0.5 if prev_vol > 0 else False,
                "is_jiayin": k.close < k.open and k.close > prev_close,
                "is_yinxian": k.close < prev_close,
                "is_fangliang_yinxian": k.close < prev_close and k.vol > prev_vol * 1.5 if prev_vol > 0 else False,
            }
        )
    return result


def get_datasource(preferred: str = "auto") -> DataSource:
    """数据源工厂函数。

    默认策略：auto 模式下优先使用 BaoStock（免费数据源），
    其次是 AkShare/Bridge/SQLite。
    """
    if preferred == "bridge":
        return BridgeDataSource()
    if preferred == "sqlite":
        return SqliteDataSource()
    if preferred == "akshare":
        return AkShareDataSource()
    if preferred == "baostock":
        return BaoStockDataSource()
    return CompositeDataSource("auto")
