"""
BaoStock 数据源客户端封装

BaoStock 是一个免费、开源的证券数据平台，无需注册即可获取大量准确、完整的证券历史行情数据和上市公司财务数据。

接口文档：http://baostock.com/baostock/index.php/Python_API%E6%96%87%E6%A1%A3

注意：BaoStock 不支持实时行情和资金流向，这些功能由 AkShare 补充。
"""

from __future__ import annotations

import atexit
import logging
import threading
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


class BaoStockClient:
    """BaoStock API 客户端封装。

    使用时通过 ``get_client()`` 获取单例，客户端会自动登录并保持连接，
    程序退出时自动登出。

    **线程安全**：``_ensure_login`` 使用 ``threading.Lock`` 保护，
    避免多线程并发登录导致 ``Connection reset by peer``。

    支持的数据：
    - 日线/周线/月线行情（含 PE/PB/PS/换手率等基础指标）
    - 指数行情
    - 股票列表（含行业分类）
    - 交易日历
    - 分钟线（5/15/30/60 分钟）
    """

    def __init__(self) -> None:
        self._login_lock = threading.Lock()
        try:
            import baostock as bs
            self._bs = bs
            self._available = True
            self._logged_in = False
        except ImportError:
            logger.warning("[baostock] baostock 未安装，BaoStockClient 将不可用")
            self._available = False
            self._bs = None
            self._logged_in = False

    def _ensure_login(self) -> bool:
        """确保已登录，如果未登录则执行登录（线程安全）"""
        if not self._available:
            return False
        if self._logged_in:
            return True
        with self._login_lock:
            # 双重检查：可能在等锁期间已被其他线程登录
            if self._logged_in:
                return True
            try:
                lg = self._bs.login()
                self._logged_in = lg.error_code == "0"
                return self._logged_in
            except (
                ConnectionError,
                TimeoutError,
                OSError,
                ValueError,
                KeyError,
                AttributeError,
                TypeError,
                RuntimeError,
            ) as e:
                logger.warning("[baostock] login 失败: %s", e)
                self._logged_in = False
                return False

    def check_connection(self) -> bool:
        """检查 BaoStock 是否可用"""
        if not self._available:
            return False
        try:
            if self._ensure_login():
                rs = self._bs.query_all_stock(datetime.now().strftime("%Y-%m-%d"))
                return rs.error_code == "0"
            return False
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] 连通性检查失败: %s", e)
            return False

    # ------------------------------------------------------------------
    # 代码格式转换
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_ts_code(ts_code: str) -> str:
        """将股票代码转换为 BaoStock 格式（600487.SH → sh.600487）"""
        if "." in ts_code:
            code, exchange = ts_code.split(".")
            return f"{exchange.lower()}.{code}"
        return ts_code

    @staticmethod
    def _convert_ts_code_full(ts_code_baostock: str) -> str:
        """将 BaoStock 格式转换为项目完整格式（sh.600487 → 600487.SH）"""
        if "." in ts_code_baostock:
            exchange, code = ts_code_baostock.split(".")
            return f"{code}.{exchange.upper()}"
        return ts_code_baostock

    @staticmethod
    def _fetch_result(rs) -> pd.DataFrame | None:
        """手动处理 ResultSet（兼容 pandas 3.x）"""
        if rs is None or rs.error_code != "0":
            return None
        data_list = []
        while rs.next():
            data_list.append(rs.get_row_data())
        if not data_list:
            return None
        return pd.DataFrame(data_list, columns=rs.fields)

    # ------------------------------------------------------------------
    # 最近交易日
    # ------------------------------------------------------------------

    def _get_last_trade_date(self) -> str:
        """获取最近的交易日期（YYYY-MM-DD 格式）

        使用 ``query_trade_dates`` 查询近 10 天的交易日历，
        取倒数第二个 ``is_trading_day=1`` 的日期（即上一个已完成的交易日）。
        避免使用 ``query_all_stock`` 探测（会消耗 ResultSet）。
        
        **重要**：返回上一个已完成的交易日，而非当天。
        因为 ``query_all_stock()`` 需要传入一个已经完成的交易日，
        当天的数据可能还未完全同步到 BaoStock。
        """
        try:
            if not self._ensure_login():
                return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
            rs = self._bs.query_trade_dates(start_date=start, end_date=end)
            if rs.error_code != "0":
                return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            trade_dates = []
            while rs.next():
                row = rs.get_row_data()
                # row: [calendar_date, is_trading_day]
                if len(row) >= 2 and row[1] == "1":
                    trade_dates.append(row[0])
            
            # 返回倒数第二个交易日（上一个已完成的交易日）
            if len(trade_dates) >= 2:
                return trade_dates[-2]
            elif trade_dates:
                return trade_dates[-1]
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[baostock] _get_last_trade_date 失败: %s", e)

        # 兜底：昨天
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # K 线数据（含基础指标）
    # ------------------------------------------------------------------

    def get_daily(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
        frequency: str = "d",
        adjustflag: str = "2",
    ) -> pd.DataFrame | None:
        """获取 K 线数据（含 PE/PB/PS/换手率等基础指标）

        Args:
            ts_code: 股票代码，如 '600487.SH'
            start_date: 开始日期，如 '20260701' 或 '2026-07-01'
            end_date: 结束日期
            frequency: 频率，d=日线, w=周线, m=月线, 5/15/30/60=分钟线
            adjustflag: 复权类型，2=前复权, 1=后复权, 3=不复权

        Returns:
            K 线 DataFrame，包含 ohLCV + peTTM/pbMRQ/psTTM/turn 等字段
        """
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None

            code = self._convert_ts_code(ts_code)
            # 统一日期格式（支持 YYYYMMDD 和 YYYY-MM-DD）
            if len(start_date) == 8:
                start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
            if len(end_date) == 8:
                end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

            # 根据频率选择字段
            if frequency == "d":
                fields = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
            else:
                fields = "date,code,open,high,low,close,volume,amount,adjustflag,turn,pctChg"

            rs = self._bs.query_history_k_data_plus(
                code,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                adjustflag=adjustflag,
            )
            df = self._fetch_result(rs)
            if df is None or df.empty:
                return None

            # 过滤停牌
            if "tradestatus" in df.columns:
                df = df[df["tradestatus"] == "1"]
                if df.empty:
                    return None

            # 字段映射
            df = df.rename(columns={
                "date": "trade_date",
                "code": "ts_code",
                "volume": "vol",
                "pctChg": "pct_chg",
                "preclose": "pre_close",
                "adjustflag": "adjust_flag",
                "turn": "turnover_rate",
                "peTTM": "pe_ttm",
                "pbMRQ": "pb",
                "psTTM": "ps_ttm",
                "pcfNcfTTM": "pcf_ncf_ttm",
            })
            df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")

            # 数值类型转换
            numeric_cols = [
                "open", "high", "low", "close", "vol", "amount", "pct_chg",
                "pre_close", "turnover_rate", "pe_ttm", "pb", "ps_ttm", "pcf_ncf_ttm",
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 单位转换：匹配数据库格式
            # vol: BaoStock 返回股 → 数据库存手（÷100）
            # amount: BaoStock 返回元 → 数据库存千元（÷1000）
            if "vol" in df.columns:
                df["vol"] = df["vol"] / 100
            if "amount" in df.columns:
                df["amount"] = df["amount"] / 1000

            return df

        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_daily 失败 %s: %s", ts_code, e)
            return None

    def get_index_daily(
        self, ts_code: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        """获取指数日线行情

        Args:
            ts_code: 指数代码，如 '000001.SH'（上证指数）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            指数 K 线 DataFrame
        """
        if not self._available:
            return None
        try:
            return self.get_daily(ts_code, start_date, end_date, adjustflag="3")
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_index_daily 失败 %s: %s", ts_code, e)
            return None

    def get_all_stocks_daily(self, date: str) -> pd.DataFrame | None:
        """获取全市场某天的股票列表（仅元数据，无 OHLCV）

        .. deprecated::
            BaoStock 不支持批量获取全市场某天的 K 线数据。
            此方法现仅返回 ``query_all_stock(day)`` 的结果（code/tradeStatus/isST/code_name），
            用于"今天有哪些股票交易"的元数据查询。

            对于全市场 K 线同步：
            - 当天数据：使用 ``AkShareClient.get_all_stocks_spot()`` 实时快照
            - 历史日期：使用 ``DataSyncer.sync_all_daily_kline()`` 逐股并发查询

        Args:
            date: 交易日期，格式 YYYY-MM-DD

        Returns:
            包含 code/tradeStatus/isST/code_name 的 DataFrame
        """
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None

            rs = self._bs.query_all_stock(day=date)
            df = self._fetch_result(rs)
            if df is None or df.empty:
                return None

            # 字段映射
            df = df.rename(columns={
                "code": "ts_code",
                "tradeStatus": "trade_status",
                "code_name": "name",
            })
            df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
            return df

        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_all_stocks_daily 失败 %s: %s", date, e)
            return None

    def get_kline_dicts(
        self,
        ts_code: str,
        days: int = 60,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """获取 K 线 dict 列表（兼容项目格式）

        Args:
            ts_code: 股票代码
            days: 获取天数
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            K 线 dict 列表，按日期升序
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")

        df = self.get_daily(ts_code, start_date, end_date)
        if df is None or df.empty:
            return []

        records = df.to_dict("records")
        records.sort(key=lambda x: x.get("trade_date", ""))
        if days > 0:
            records = records[-days:]
        return records

    # ------------------------------------------------------------------
    # 股票列表
    # ------------------------------------------------------------------

    def get_stock_basic(
        self, ts_code: str | None = None, name: str | None = None,
    ) -> pd.DataFrame | None:
        """获取股票基础信息（含行业分类）

        Args:
            ts_code: 股票代码（可选）
            name: 股票名称（可选）

        Returns:
            股票基础信息 DataFrame
        """
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None

            trade_date = self._get_last_trade_date()
            rs = self._bs.query_all_stock(trade_date)
            df = self._fetch_result(rs)
            if df is None or df.empty:
                return None

            df = df.rename(columns={"code": "ts_code", "code_name": "name"})
            df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
            df["market"] = df["ts_code"].apply(
                lambda x: "SH" if x.endswith(".SH") else ("BJ" if x.endswith(".BJ") else "SZ")
            )
            df["industry"] = ""
            df["list_date"] = ""
            df["area"] = ""
            df["is_hs"] = ""

            # 获取行业分类
            try:
                rs = self._bs.query_stock_industry()
                industry_df = self._fetch_result(rs)
                if industry_df is not None and not industry_df.empty:
                    industry_df = industry_df.rename(columns={"code": "code_raw", "industry": "industry"})
                    industry_df["ts_code"] = industry_df["code_raw"].apply(self._convert_ts_code_full)
                    industry_map = industry_df.set_index("ts_code")["industry"].to_dict()
                    df["industry"] = df["ts_code"].map(industry_map).fillna("")
            except (
                ConnectionError,
                TimeoutError,
                OSError,
                ValueError,
                KeyError,
                AttributeError,
                TypeError,
                RuntimeError,
            ) as e:
                logger.debug("[baostock] 获取行业信息失败: %s", e)

            if ts_code:
                df = df[df["ts_code"] == ts_code]
            if name:
                df = df[df["name"].str.contains(name)]

            return df[["ts_code", "name", "area", "industry", "market", "list_date", "is_hs"]]

        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_stock_basic 失败: %s", e)
            return None

    def get_stock_list(self, exchange: str | None = None) -> list[dict]:
        """获取股票列表

        Args:
            exchange: 交易所代码，如 'SH'、'SZ'（可选）

        Returns:
            股票列表 dict
        """
        df = self.get_stock_basic()
        if df is None or df.empty:
            return []

        if exchange:
            df = df[df["market"] == exchange.upper()]

        return df.to_dict("records")

    # ------------------------------------------------------------------
    # 交易日历
    # ------------------------------------------------------------------

    def get_trade_cal(
        self, exchange: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        """获取交易日历

        Args:
            exchange: 交易所代码（如 'SSE'、'SZSE'，BaoStock 不区分）
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            交易日历 DataFrame
        """
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None

            # 日期格式转换
            if len(start_date) == 8:
                start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
            if len(end_date) == 8:
                end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

            rs = self._bs.query_trade_dates(start_date=start_date, end_date=end_date)
            df = self._fetch_result(rs)
            if df is None or df.empty:
                return None

            df = df.rename(columns={
                "calendar_date": "trade_date",
                "is_trading_day": "is_open",
            })
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
            df["is_open"] = df["is_open"].map({"1": True, "0": False})
            return df

        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_trade_cal 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 每日基础指标
    # ------------------------------------------------------------------

    def get_daily_basic(
        self, ts_code: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        """获取每日基础指标（PE/PB/PS/换手率等）

        Args:
            ts_code: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            每日基础指标 DataFrame，字段与项目标准格式兼容
        """
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None

            code = self._convert_ts_code(ts_code)
            if len(start_date) == 8:
                start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
            if len(end_date) == 8:
                end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

            fields = "date,code,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn"
            rs = self._bs.query_history_k_data_plus(
                code, fields, start_date=start_date, end_date=end_date,
                frequency="d", adjustflag="3",
            )
            df = self._fetch_result(rs)
            if df is None or df.empty:
                return None

            # 映射到项目标准字段
            df = df.rename(columns={
                "date": "trade_date",
                "code": "ts_code",
                "turn": "turnover_rate",
                "peTTM": "pe_ttm",
                "pbMRQ": "pb",
                "psTTM": "ps_ttm",
                "pcfNcfTTM": "pcf_ncf_ttm",
            })
            df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")

            # 添加缺失字段（BaoStock 不支持的字段置为 None）
            df["total_mv"] = None
            df["circ_mv"] = None
            df["total_share"] = None
            df["float_share"] = None
            df["dv_ratio"] = None
            df["dv_ttm"] = None

            return df[
                ["ts_code", "trade_date", "pe_ttm", "pb", "ps_ttm", "pcf_ncf_ttm",
                 "turnover_rate", "total_mv", "circ_mv", "total_share",
                 "float_share", "dv_ratio", "dv_ttm"]
            ]

        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_daily_basic 失败 %s: %s", ts_code, e)
            return None

    # ------------------------------------------------------------------
    # 财务数据
    # ------------------------------------------------------------------

    def get_financial_data(
        self, ts_code: str, start_date: str = "", end_date: str = "",
    ) -> pd.DataFrame | None:
        """获取财务指标数据（利润/运营/成长/资产负债/现金流）

        Args:
            ts_code: 股票代码
            start_date: 开始日期（年份，如 '2024'）
            end_date: 结束日期（年份，如 '2024'）

        Returns:
            财务指标 DataFrame
        """
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None

            code = self._convert_ts_code(ts_code)
            # 获取利润表数据
            rs = self._bs.query_profit_data(code=code, year=start_date[:4] if start_date else "2024", quarter=4)
            profit_df = self._fetch_result(rs)

            # 获取运营能力数据
            rs = self._bs.query_operation_data(code=code, year=start_date[:4] if start_date else "2024", quarter=4)
            operation_df = self._fetch_result(rs)

            # 获取成长能力数据
            rs = self._bs.query_growth_data(code=code, year=start_date[:4] if start_date else "2024", quarter=4)
            growth_df = self._fetch_result(rs)

            # 合并数据
            if profit_df is not None and not profit_df.empty:
                df = profit_df
                if operation_df is not None and not operation_df.empty:
                    df = df.merge(operation_df, on=["code", "pubDate", "statDate"], how="left")
                if growth_df is not None and not growth_df.empty:
                    df = df.merge(growth_df, on=["code", "pubDate", "statDate"], how="left")

                # 映射到项目标准字段
                df = df.rename(columns={
                    "code": "ts_code",
                    "statDate": "end_date",
                    "pubDate": "ann_date",
                    "roeAvg": "roe",
                    "npMargin": "net_profit_margin",
                    "gpMargin": "gross_profit_margin",
                    "netProfit": "net_profit",
                    "epsTTM": "eps",
                    "MBRevenue": "revenue",
                    "totalShare": "total_share",
                    "liqaShare": "float_share",
                })
                df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
                return df

            return None

        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_financial_data 失败 %s: %s", ts_code, e)
            return None

    def get_balance_data(self, ts_code: str, year: str = "2024", quarter: int = 4) -> pd.DataFrame | None:
        """获取资产负债数据"""
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None
            code = self._convert_ts_code(ts_code)
            rs = self._bs.query_balance_data(code=code, year=year, quarter=quarter)
            df = self._fetch_result(rs)
            if df is not None and not df.empty:
                df = df.rename(columns={"code": "ts_code", "statDate": "end_date", "pubDate": "ann_date"})
                df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
                return df
            return None
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_balance_data 失败 %s: %s", ts_code, e)
            return None

    def get_cash_flow_data(self, ts_code: str, year: str = "2024", quarter: int = 4) -> pd.DataFrame | None:
        """获取现金流数据"""
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None
            code = self._convert_ts_code(ts_code)
            rs = self._bs.query_cash_flow_data(code=code, year=year, quarter=quarter)
            df = self._fetch_result(rs)
            if df is not None and not df.empty:
                df = df.rename(columns={"code": "ts_code", "statDate": "end_date", "pubDate": "ann_date"})
                df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
                return df
            return None
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_cash_flow_data 失败 %s: %s", ts_code, e)
            return None

    def get_dupont_data(self, ts_code: str, year: str = "2024", quarter: int = 4) -> pd.DataFrame | None:
        """获取杜邦分析数据"""
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None
            code = self._convert_ts_code(ts_code)
            rs = self._bs.query_dupont_data(code=code, year=year, quarter=quarter)
            df = self._fetch_result(rs)
            if df is not None and not df.empty:
                df = df.rename(columns={"code": "ts_code", "statDate": "end_date", "pubDate": "ann_date"})
                df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
                return df
            return None
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_dupont_data 失败 %s: %s", ts_code, e)
            return None

    def get_dividend_data(self, ts_code: str, year: str = "2024", year_type: str = "report") -> pd.DataFrame | None:
        """获取分红数据"""
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None
            code = self._convert_ts_code(ts_code)
            rs = self._bs.query_dividend_data(code=code, year=year, yearType=year_type)
            df = self._fetch_result(rs)
            if df is not None and not df.empty:
                df = df.rename(columns={"code": "ts_code"})
                df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
                return df
            return None
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_dividend_data 失败 %s: %s", ts_code, e)
            return None

    def get_hs300_stocks(self, date: str = "") -> pd.DataFrame | None:
        """获取沪深300成分股"""
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None
            rs = self._bs.query_hs300_stocks(date=date)
            df = self._fetch_result(rs)
            if df is not None and not df.empty:
                df = df.rename(columns={"code": "ts_code", "code_name": "name"})
                df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
                return df
            return None
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_hs300_stocks 失败: %s", e)
            return None

    def get_sz50_stocks(self, date: str = "") -> pd.DataFrame | None:
        """获取上证50成分股"""
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None
            rs = self._bs.query_sz50_stocks(date=date)
            df = self._fetch_result(rs)
            if df is not None and not df.empty:
                df = df.rename(columns={"code": "ts_code", "code_name": "name"})
                df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
                return df
            return None
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_sz50_stocks 失败: %s", e)
            return None

    def get_zz500_stocks(self, date: str = "") -> pd.DataFrame | None:
        """获取中证500成分股"""
        if not self._available:
            return None
        try:
            if not self._ensure_login():
                return None
            rs = self._bs.query_zz500_stocks(date=date)
            df = self._fetch_result(rs)
            if df is not None and not df.empty:
                df = df.rename(columns={"code": "ts_code", "code_name": "name"})
                df["ts_code"] = df["ts_code"].apply(self._convert_ts_code_full)
                return df
            return None
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[baostock] get_zz500_stocks 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------

    def logout(self) -> None:
        """登出 BaoStock（通常由 atexit 自动调用）"""
        if self._available and self._bs and self._logged_in:
            try:
                self._bs.logout()
                self._logged_in = False
            except (
                ConnectionError,
                TimeoutError,
                OSError,
                ValueError,
                KeyError,
                AttributeError,
                TypeError,
                RuntimeError,
            ):
                pass


# ---------------------------------------------------------------------------
# 单例管理
# ---------------------------------------------------------------------------

_client: BaoStockClient | None = None


def get_client() -> BaoStockClient:
    """获取 BaoStockClient 单例（程序退出时自动登出）"""
    global _client
    if _client is None:
        _client = BaoStockClient()
        atexit.register(_client.logout)
    return _client
