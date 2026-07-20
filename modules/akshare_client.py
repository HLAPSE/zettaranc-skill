"""
AkShare 数据源客户端封装

AkShare 是一个免费的 Python 财经数据接口库，无需 token，支持多种数据源。
用于补充 BaoStock 不支持的数据：资金流向、实时行情、股息率等。

注意：部分接口在 pandas 3.x 环境下可能报错，已通过 try/except 处理。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# 限流配置
_RATE_LIMIT_SLEEP = 0.5  # 秒
_last_request_time = 0.0


def _rate_limit():
    """简单限流"""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _RATE_LIMIT_SLEEP:
        time.sleep(_RATE_LIMIT_SLEEP - elapsed)
    _last_request_time = time.time()


class AkShareClient:
    """AkShare API 客户端封装。

    用于获取 BaoStock 不支持的数据：
    - 资金流向（moneyflow）
    - 实时行情（realtime_quote）
    - 每日基础指标（daily_basic）- 股息率/股本等
    - 涨跌停列表（limit_list）
    """

    def __init__(self) -> None:
        try:
            import akshare as ak
            self._ak = ak
            self._available = True
        except ImportError:
            logger.warning("[akshare] akshare 未安装，AkShareClient 将不可用")
            self._available = False
            self._ak = None

    @property
    def available(self) -> bool:
        """检查 akshare 是否可用"""
        return self._available

    def check_connection(self) -> bool:
        """检查 AkShare 是否可用"""
        if not self._available:
            return False
        try:
            _rate_limit()
            df = self._ak.stock_zh_a_spot_em()
            return df is not None and not df.empty
        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            RuntimeError,
        ) as e:
            logger.warning("[akshare] 连通性检查失败: %s", e)
            return False

    # ------------------------------------------------------------------
    # 实时行情
    # ------------------------------------------------------------------

    def get_realtime_quote(self, ts_codes: list[str]) -> pd.DataFrame | None:
        """获取 A 股实时行情快照

        Args:
            ts_codes: 股票代码列表，如 ['600487.SH', '000001.SZ']

        Returns:
            实时行情 DataFrame，字段与项目标准格式兼容
        """
        if not self._available:
            return None
        try:
            _rate_limit()
            df = self._ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None

            # 筛选指定股票
            codes = [self._convert_ts_code(c) for c in ts_codes]
            df = df[df["代码"].isin(codes)]
            if df.empty:
                return None

            # 字段映射（中文 → 英文）
            result = pd.DataFrame({
                "ts_code": df["代码"].apply(self._convert_ts_code_full),
                "name": df["名称"],
                "open": df["今开"],
                "high": df["最高"],
                "low": df["最低"],
                "close": df["最新价"],
                "vol": df["成交量"],  # AkShare 返回手，与数据库一致
                "amount": df["成交额"] / 1000,  # AkShare 返回元 → 数据库存千元
                "pct_chg": df["涨跌幅"],
            })
            return result

        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[akshare] get_realtime_quote 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 资金流向
    # ------------------------------------------------------------------

    def get_moneyflow(self, ts_code: str, trade_date: str) -> pd.DataFrame | None:
        """获取个股资金流向（注意：AkShare 仅提供 5 日汇总数据）

        **重要说明**：
        - AkShare 的 `stock_individual_fund_flow_rank()` 返回的是**最近 5 个交易日的汇总数据**，
          不是单日数据。因此无论传入哪个 `trade_date`，返回的都是同一组 5 日汇总值。
        - 这意味着如果多次调用（不同日期），会将相同的 5 日汇总数据重复存储到不同日期下，
          可能导致策略信号计算不准确。
        - 建议策略层仅使用 `net_mf` 和 `pct_mf` 字段，忽略 `buy_*`/`sell_*` 明细（均为 0）。

        Args:
            ts_code: 股票代码，如 '600487.SH'
            trade_date: 交易日期，如 '20260720'（实际返回的是最近 5 日汇总）

        Returns:
            资金流向 DataFrame，字段与项目标准格式兼容
        """
        if not self._available:
            return None
        try:
            code = self._convert_ts_code(ts_code)

            _rate_limit()
            df = self._ak.stock_individual_fund_flow_rank()
            if df is None or df.empty:
                return None

            df = df[df["代码"] == code]
            if df.empty:
                return None

            row = df.iloc[0]
            # AkShare 返回元 -> 数据库存万元（÷10000）
            # 注意：AkShare 仅提供净额（买入-卖出），无法拆分为买卖明细
            # 下游 strategies/core.py 应优先使用 net_mf 字段
            net_mf_yuan = float(row.get("5日主力净流入-净金额", 0) or 0)
            pct_mf = float(row.get("5日主力净流入-净占比", 0) or 0)
            result = {
                "ts_code": ts_code,
                "trade_date": trade_date,
                # 明细字段：AkShare 不提供买卖拆分，置 0
                "buy_sm_amount": 0.0,
                "sell_sm_amount": 0.0,
                "buy_md_amount": 0.0,
                "sell_md_amount": 0.0,
                "buy_lg_amount": 0.0,
                "sell_lg_amount": 0.0,
                "buy_elg_amount": 0.0,
                "sell_elg_amount": 0.0,
                # 净额字段：主力净流入（万元）
                "net_mf": net_mf_yuan / 10000,
                # 主力净流入占比（%）
                "pct_mf": pct_mf,
            }
            return pd.DataFrame([result])

        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[akshare] get_moneyflow 失败 %s: %s", ts_code, e)
            return None

    # ------------------------------------------------------------------
    # 资金流向排名（全市场）
    # ------------------------------------------------------------------

    def get_moneyflow_rank(self) -> pd.DataFrame | None:
        """获取全市场资金流向排名（5日）

        Returns:
            资金流向排名 DataFrame
        """
        if not self._available:
            return None
        try:
            _rate_limit()
            df = self._ak.stock_individual_fund_flow_rank()
            if df is None or df.empty:
                return None

            # 字段映射（AkShare 返回元，这里保留原始单位，下游按需转换）
            result = pd.DataFrame({
                "ts_code": df["代码"].apply(self._convert_ts_code_full),
                "name": df["名称"],
                "close": df["最新价"],
                "pct_chg": df["5日涨跌幅"],
                "net_mf_5d": df["5日主力净流入-净金额"],
                "net_mf_ratio_5d": df["5日主力净流入-净占比"],
                "net_elg_mf_5d": df["5日超大单净流入-净金额"],
                "net_lg_mf_5d": df["5日大单净流入-净金额"],
                "net_md_mf_5d": df["5日中单净流入-净金额"],
                "net_sm_mf_5d": df["5日小单净流入-净金额"],
            })
            return result

        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.warning("[akshare] get_moneyflow_rank 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 涨跌停列表
    # ------------------------------------------------------------------

    def get_limit_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取涨跌停股票列表

        Args:
            trade_date: 交易日期，如 '20260720'（YYYYMMDD 格式）

        Returns:
            涨跌停列表 DataFrame
        """
        if not self._available:
            return None
        try:
            _rate_limit()
            df = self._ak.stock_zt_pool_em(date=trade_date)
            if df is None or df.empty:
                return None

            result = pd.DataFrame({
                "ts_code": df["代码"].apply(self._convert_ts_code_full),
                "name": df["名称"],
                "close": df["最新价"],
                "pct_chg": df["涨跌幅"],
                "amount": df["成交额"],
                "turnover_rate": df["换手率"],
                "封板资金": df.get("封板资金", 0),
                "连板数": df.get("连板数", 0),
            })
            return result

        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[akshare] get_limit_list 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 龙虎榜
    # ------------------------------------------------------------------

    def get_top_list(self, trade_date: str) -> pd.DataFrame | None:
        """获取龙虎榜数据

        Args:
            trade_date: 交易日期，如 '20260720'（YYYYMMDD 格式）

        Returns:
            龙虎榜 DataFrame
        """
        if not self._available:
            return None
        try:
            _rate_limit()
            df = self._ak.stock_lhb_detail_em(start_date=trade_date, end_date=trade_date)
            if df is None or df.empty:
                return None

            result = pd.DataFrame({
                "ts_code": df["代码"].apply(self._convert_ts_code_full) if "代码" in df.columns else "",
                "name": df.get("名称", ""),
                "close": df.get("收盘价", 0),
                "pct_chg": df.get("涨跌幅", 0),
                "listed_reason": df.get("上榜理由", ""),
            })
            return result

        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[akshare] get_top_list 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 财务数据
    # ------------------------------------------------------------------

    def get_financial_indicator(self, ts_code: str, start_year: str = "2020") -> pd.DataFrame | None:
        """获取财务分析指标（ROE/ROA/毛利率/净利率等）"""
        if not self._available:
            return None
        try:
            code = self._convert_ts_code(ts_code)
            _rate_limit()
            df = self._ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year)
            if df is None or df.empty:
                return None
            # 字段映射到项目标准格式
            rename_map = {}
            for col in df.columns:
                if "日期" in col or "报告期" in col:
                    rename_map[col] = "end_date"
                elif "净资产收益率" in col and "摊薄" not in col:
                    rename_map[col] = "roe"
                elif "销售毛利率" in col:
                    rename_map[col] = "gross_profit_margin"
                elif "销售净利率" in col:
                    rename_map[col] = "net_profit_margin"
            if rename_map:
                df = df.rename(columns=rename_map)
            return df
        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[akshare] get_financial_indicator 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 估值数据
    # ------------------------------------------------------------------

    def get_valuation(self, ts_code: str) -> pd.DataFrame | None:
        """获取个股估值分析（PE/PB/股息率等）"""
        if not self._available:
            return None
        try:
            code = self._convert_ts_code(ts_code)
            _rate_limit()
            df = self._ak.stock_value_em(symbol=code)
            if df is None or df.empty:
                return None
            return df
        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[akshare] get_valuation 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 北向资金
    # ------------------------------------------------------------------

    def get_northbound_flow(self, days: int = 30) -> pd.DataFrame | None:
        """获取北向资金历史流向"""
        if not self._available:
            return None
        try:
            _rate_limit()
            df = self._ak.stock_hsgt_hist_em(symbol="沪股通")
            if df is None or df.empty:
                return None
            return df.tail(days)
        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[akshare] get_northbound_flow 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 融资融券
    # ------------------------------------------------------------------

    def get_margin_data(self, date: str = "") -> pd.DataFrame | None:
        """获取融资融券汇总数据"""
        if not self._available:
            return None
        try:
            _rate_limit()
            df = self._ak.stock_margin_account_info()
            if df is None or df.empty:
                return None
            return df
        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[akshare] get_margin_data 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 板块数据
    # ------------------------------------------------------------------

    def get_industry_board(self) -> pd.DataFrame | None:
        """获取行业板块实时行情"""
        if not self._available:
            return None
        try:
            _rate_limit()
            df = self._ak.stock_board_industry_name_em()
            if df is None or df.empty:
                return None
            return df
        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[akshare] get_industry_board 失败: %s", e)
            return None

    def get_concept_board(self) -> pd.DataFrame | None:
        """获取概念板块实时行情"""
        if not self._available:
            return None
        try:
            _rate_limit()
            df = self._ak.stock_board_concept_name_em()
            if df is None or df.empty:
                return None
            return df
        except (
            requests.RequestException,
            ConnectionError,
            TimeoutError,
            OSError,
            ValueError,
            KeyError,
            AttributeError,
            TypeError,
            RuntimeError,
        ) as e:
            logger.debug("[akshare] get_concept_board 失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_ts_code(ts_code: str) -> str:
        """将股票代码转换为 AkShare 格式（去掉 .SH/.SZ 后缀）"""
        if "." in ts_code:
            return ts_code.split(".")[0]
        return ts_code

    @staticmethod
    def _convert_ts_code_full(code: str) -> str:
        """将 AkShare 格式转换为完整格式（600487 → 600487.SH）"""
        if len(code) == 6:
            if code.startswith("6"):
                return f"{code}.SH"
            elif code.startswith("0") or code.startswith("3"):
                return f"{code}.SZ"
            elif code.startswith("8") or code.startswith("4"):
                return f"{code}.BJ"
        return code


_client: AkShareClient | None = None


def get_client() -> AkShareClient:
    """获取 AkShareClient 单例"""
    global _client
    if _client is None:
        _client = AkShareClient()
    return _client
