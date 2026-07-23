"""
数据库管理模块（双后端兼容）

  - CockroachDB（生产）：设置环境变量 CRDB_URL 时启用，使用 psycopg2 驱动，
    支持分布式、强一致与 UPSERT / RETURNING 等 PG 语法。
  - SQLite（默认 / 测试回退）：CRDB_URL 为空时使用，零额外依赖，
    通过 _to_sqlite_ddl() 复用同一套 DDL 定义。

调用方契约（与后端无关）：
  - 参数占位符统一使用 `?`（CockroachDB 侧自动转为 `%s`）
  - 时间默认值统一写作 `NOW()::STRING`（SQLite 侧自动转为 (datetime('now'))）
  - 行访问支持 `row['col']` / `row[i]` / 迭代取值 / `keys()` / `items()`
  - 异常统一捕获 `sqlite3.Error`（CockroachDB 异常被包装为 DBAPIError，
    继承自 sqlite3.Error，因此现有 `except sqlite3.Error` 在双后端下均生效）
"""

import logging
import os
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING
from datetime import datetime
from collections.abc import Generator
from dataclasses import dataclass
from contextlib import contextmanager

if TYPE_CHECKING:
    from modules.core.errors import ErrorCode, ZettarancError

logger = logging.getLogger(__name__)


def _backend() -> str:
    """探测当前后端：设置 CRDB_URL 走 CockroachDB，否则走 SQLite。"""
    return "crdb" if os.environ.get("CRDB_URL") else "sqlite"


@dataclass
class TradeRecord:
    """交易记录数据类"""
    ts_code: str
    trade_date: str
    action: str
    price: float
    quantity: int
    amount: float
    reason: str = ""
    signal_type: str = ""
    zg_review: str = ""
    broker: str = ""
    fee: float = 0
    tags: str = ""
    notes: str = ""


@dataclass
class StockInfo:
    """股票信息数据类"""
    ts_code: str
    name: str = ""
    area: str = ""
    industry: str = ""
    market: str = ""


# ==================== 统一异常 ====================

class DBAPIError(sqlite3.Error):
    """CockroachDB (psycopg2) 异常的统一包装，继承自 sqlite3.Error，
    使现有调用方的 `except sqlite3.Error` 在双后端下均生效。"""


# ==================== 行包装 ====================

class _Row:
    """统一行对象。

    无论底层后端返回何种原生行（sqlite3.Row / psycopg2 tuple），均包装为 _Row：
      - row['col']   按列名访问
      - row[i]       按下标访问
      - iter(row)    迭代列值（兼容 dict(zip(cols, row))）
      - row.keys() / row.values() / row.items() / row.get()
    """

    __slots__ = ("_values", "_cols")

    def __init__(self, values: tuple, cols: tuple):
        self._values = values
        self._cols = cols

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        if isinstance(key, str):
            try:
                return self._values[self._cols.index(key)]
            except ValueError as exc:
                raise KeyError(key) from exc
        raise TypeError(f"row index must be int or str, got {type(key).__name__}")

    def __setitem__(self, key, value):
        if isinstance(key, int):
            self._values = tuple(value if i == key else v for i, v in enumerate(self._values))
        elif isinstance(key, str):
            idx = self._cols.index(key)
            self._values = tuple(value if i == idx else v for i, v in enumerate(self._values))
        else:
            raise TypeError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def keys(self):
        return self._cols

    def values(self):
        return self._values

    def items(self):
        return tuple(zip(self._cols, self._values))

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, key):
        return key in self._cols

    def __repr__(self):
        return f"_Row({dict(self.items())})"


# ==================== SQL 方言转换 ====================

def _convert_sql(sql: str, backend: str) -> str:
    """将统一 SQL（? 占位符 / NOW()::STRING）转换为后端方言。"""
    if backend == "crdb":
        return sql.replace("?", "%s")
    # SQLite：NOW()::STRING -> (datetime('now'))
    return sql.replace("NOW()::STRING", "(datetime('now'))")


def _to_sqlite_ddl(crdb_sql: str) -> str:
    """将 CockroachDB DDL 转换为 SQLite 兼容 DDL。

    说明：统一把 `id BIGINT DEFAULT unique_rowid()` 转为 `id INTEGER`，
    并保留原 DDL 中的 PRIMARY KEY 声明。SQLite 中「单列 INTEGER 主键」
    会自动成为 rowid 别名并自动赋值；复合主键表的 id 退化为普通列
    （插入不提供 id 时存 NULL，不依赖 id 唯一性），均不会与 PRIMARY KEY 冲突。
    """
    s = crdb_sql
    s = s.replace("id BIGINT DEFAULT unique_rowid()", "id INTEGER")
    s = s.replace("NOW()::STRING", "(datetime('now'))")
    s = s.replace("BOOLEAN DEFAULT TRUE", "INTEGER DEFAULT 1")
    s = s.replace("BOOLEAN", "INTEGER")
    s = s.replace("DOUBLE PRECISION", "REAL")
    return s


def _is_psycopg2_error(exc: Exception) -> bool:
    try:
        import psycopg2
    except ImportError:
        return False
    return isinstance(exc, psycopg2.Error)


# ==================== 连接 / 游标包装 ====================

class _Cursor:
    """游标包装：负责占位符转换、异常统一、行对象包装。"""

    def __init__(self, raw, backend: str):
        self._raw = raw
        self._backend = backend

    def _cols(self):
        desc = self._raw.description
        return tuple(d[0] for d in desc) if desc else ()

    def _wrap_error(self, fn, sql, params=None):
        sql2 = _convert_sql(sql, self._backend)
        try:
            if params is None:
                return fn(sql2)
            return fn(sql2, params)
        except Exception as exc:  # noqa: BLE001 - 统一异常类型
            if self._backend == "crdb" and _is_psycopg2_error(exc):
                raise DBAPIError(str(exc)) from exc
            raise

    def execute(self, sql, params=None):
        return self._wrap_error(self._raw.execute, sql, params)

    def executemany(self, sql, seq_of_params):
        return self._wrap_error(self._raw.executemany, sql, seq_of_params)

    def fetchall(self):
        cols = self._cols()
        return [_Row(tuple(r), cols) for r in self._raw.fetchall()]

    def fetchone(self):
        r = self._raw.fetchone()
        if r is None:
            return None
        return _Row(tuple(r), self._cols())

    def fetchmany(self, size=None):
        cols = self._cols()
        rows = self._raw.fetchmany(size) if size is not None else self._raw.fetchmany()
        return [_Row(tuple(r), cols) for r in rows]

    @property
    def rowcount(self):
        return self._raw.rowcount

    @property
    def lastrowid(self):
        return self._raw.lastrowid

    @property
    def description(self):
        return self._raw.description

    def close(self):
        return self._raw.close()

    def __iter__(self):
        cols = self._cols()
        for r in self._raw:
            yield _Row(tuple(r), cols)


class _Connection:
    """连接包装：屏蔽 sqlite3 / psycopg2 差异。"""

    def __init__(self, raw, backend: str):
        self._raw = raw
        self._backend = backend
        # 默认 row_factory 非空（与历史行为一致：调用方按 row['col'] 访问）
        self.row_factory = sqlite3.Row

    @property
    def backend(self) -> str:
        return self._backend

    def cursor(self):
        return _Cursor(self._raw.cursor(), self._backend)

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        return self._raw.commit()

    def rollback(self):
        return self._raw.rollback()

    def close(self):
        return self._raw.close()

    @property
    def rowcount(self):
        return self._raw.rowcount


def _get_crdb_connection():
    """获取 CockroachDB 连接（psycopg2）。"""
    import psycopg2

    conn = psycopg2.connect(os.environ.get("CRDB_URL", ""))
    conn.autocommit = False
    return conn


def get_db_path() -> Path:
    """获取数据库路径（每次调用时动态读取 DB_PATH 环境变量）。"""
    path_str = os.getenv("DB_PATH", "data/stock_data.db")
    path = Path(path_str)
    if not path.is_absolute():
        path = Path(__file__).parent.parent / path_str
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_db_connection(db_path: str | None = None):
    """获取数据库连接（非上下文管理器版本）。"""
    if _backend() == "crdb":
        return _Connection(_get_crdb_connection(), "crdb")
    path = db_path or get_db_path()
    return _Connection(sqlite3.connect(path), "sqlite")


@contextmanager
def get_connection(db_path: str | None = None) -> Generator[_Connection, None, None]:
    """获取数据库连接的上下文管理器（自动 commit / rollback / close）。"""
    if _backend() == "crdb":
        raw = _get_crdb_connection()
    else:
        raw = sqlite3.connect(db_path or get_db_path())
    conn = _Connection(raw, _backend())
    try:
        yield conn
        conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("[database] 事务失败，触发回滚: %s", e)
        conn.rollback()
        raise
    finally:
        conn.close()


# ==================== K 线写入 ====================

def save_klines(data: list[dict]) -> int:
    """批量保存 K 线数据（UPSERT）。"""
    if not data:
        return 0

    with get_connection() as conn:
        cursor = conn.cursor()
        count = 0

        for row in data:
            try:
                cursor.execute(
                    """
                    INSERT INTO daily_kline
                    (ts_code, trade_date, open, high, low, close, vol, amount, pct_chg)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (ts_code, trade_date) DO UPDATE SET
                        open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        vol = EXCLUDED.vol,
                        amount = EXCLUDED.amount,
                        pct_chg = EXCLUDED.pct_chg
                """,
                    (
                        row.get("ts_code"), row.get("trade_date"),
                        row.get("open"), row.get("high"), row.get("low"),
                        row.get("close"), row.get("vol"), row.get("amount"),
                        row.get("pct_chg", 0),
                    ),
                )
                count += 1
            except Exception as e:
                logger.warning("[database] save_klines 写入失败: %s", e)

        return count


# ==================== 表结构初始化 ====================

_SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS stock_basic (
        ts_code TEXT PRIMARY KEY,
        name TEXT,
        area TEXT,
        industry TEXT,
        market TEXT,
        list_date TEXT,
        is_hs TEXT DEFAULT 'N'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_kline (
        id BIGINT DEFAULT unique_rowid(),
        ts_code TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        vol DOUBLE PRECISION,
        amount DOUBLE PRECISION,
        pct_chg DOUBLE PRECISION,
        vol_ratio DOUBLE PRECISION,
        is_limit_up BIGINT DEFAULT 0,
        is_limit_down BIGINT DEFAULT 0,
        pe_ttm DOUBLE PRECISION,
        pb DOUBLE PRECISION,
        ps_ttm DOUBLE PRECISION,
        PRIMARY KEY (ts_code, trade_date)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kline_code_date
    ON daily_kline(trade_date DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS indicator_cache (
        ts_code TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        close DOUBLE PRECISION DEFAULT 0.0,
        open DOUBLE PRECISION DEFAULT 0.0,
        high DOUBLE PRECISION DEFAULT 0.0,
        low DOUBLE PRECISION DEFAULT 0.0,
        vol DOUBLE PRECISION DEFAULT 0.0,
        pct_chg DOUBLE PRECISION DEFAULT 0.0,
        k DOUBLE PRECISION DEFAULT 0.0,
        d DOUBLE PRECISION DEFAULT 0.0,
        j DOUBLE PRECISION DEFAULT 0.0,
        dif DOUBLE PRECISION DEFAULT 0.0,
        dea DOUBLE PRECISION DEFAULT 0.0,
        macd_hist DOUBLE PRECISION DEFAULT 0.0,
        bbi DOUBLE PRECISION DEFAULT 0.0,
        ma5 DOUBLE PRECISION DEFAULT 0.0,
        ma10 DOUBLE PRECISION DEFAULT 0.0,
        ma20 DOUBLE PRECISION DEFAULT 0.0,
        ma60 DOUBLE PRECISION DEFAULT 0.0,
        rsi6 DOUBLE PRECISION DEFAULT 0.0,
        rsi12 DOUBLE PRECISION DEFAULT 0.0,
        rsi24 DOUBLE PRECISION DEFAULT 0.0,
        wr5 DOUBLE PRECISION DEFAULT 0.0,
        wr10 DOUBLE PRECISION DEFAULT 0.0,
        boll_mid DOUBLE PRECISION DEFAULT 0.0,
        boll_upper DOUBLE PRECISION DEFAULT 0.0,
        boll_lower DOUBLE PRECISION DEFAULT 0.0,
        boll_width DOUBLE PRECISION DEFAULT 0.0,
        boll_position DOUBLE PRECISION DEFAULT 0.0,
        vol_ratio DOUBLE PRECISION DEFAULT 1.0,
        zg_white DOUBLE PRECISION DEFAULT 0.0,
        dg_yellow DOUBLE PRECISION DEFAULT 0.0,
        is_gold_cross BIGINT DEFAULT 0,
        is_dead_cross BIGINT DEFAULT 0,
        rsl_short DOUBLE PRECISION DEFAULT 0.0,
        rsl_long DOUBLE PRECISION DEFAULT 0.0,
        is_needle_20 BIGINT DEFAULT 0,
        brick_value DOUBLE PRECISION DEFAULT 0.0,
        brick_trend TEXT DEFAULT 'NEUTRAL',
        brick_count BIGINT DEFAULT 0,
        brick_trend_up BIGINT DEFAULT 0,
        is_fanbao BIGINT DEFAULT 0,
        is_beidou BIGINT DEFAULT 0,
        is_suoliang BIGINT DEFAULT 0,
        is_jiayin_zhenyang BIGINT DEFAULT 0,
        is_jiayang_zhenyin BIGINT DEFAULT 0,
        is_fangliang_yinxian BIGINT DEFAULT 0,
        sell_score BIGINT DEFAULT 0,
        sell_reason TEXT DEFAULT '',
        signal TEXT DEFAULT 'WATCH',
        signal_desc TEXT DEFAULT '',
        prev_high DOUBLE PRECISION DEFAULT 0.0,
        prev_low DOUBLE PRECISION DEFAULT 0.0,
        dmi_plus DOUBLE PRECISION DEFAULT 0.0,
        dmi_minus DOUBLE PRECISION DEFAULT 0.0,
        adx DOUBLE PRECISION DEFAULT 0.0,
        net_lg_mf DOUBLE PRECISION DEFAULT 0.0,
        net_elg_mf DOUBLE PRECISION DEFAULT 0.0,
        last_b1_date TEXT,
        last_b1_price DOUBLE PRECISION DEFAULT 0.0,
        last_yidong_date TEXT,
        market_pct_chg DOUBLE PRECISION DEFAULT 0.0,
        market_dir TEXT DEFAULT 'NEUTRAL',
        updated_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (ts_code, trade_date)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_ind_date
    ON indicator_cache(trade_date)
    """,
    """
    CREATE TABLE IF NOT EXISTS moneyflow (
        id BIGINT DEFAULT unique_rowid(),
        ts_code TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        buy_sm_amount DOUBLE PRECISION DEFAULT 0,
        sell_sm_amount DOUBLE PRECISION DEFAULT 0,
        buy_md_amount DOUBLE PRECISION DEFAULT 0,
        sell_md_amount DOUBLE PRECISION DEFAULT 0,
        buy_lg_amount DOUBLE PRECISION DEFAULT 0,
        sell_lg_amount DOUBLE PRECISION DEFAULT 0,
        buy_elg_amount DOUBLE PRECISION DEFAULT 0,
        sell_elg_amount DOUBLE PRECISION DEFAULT 0,
        net_mf DOUBLE PRECISION DEFAULT 0,
        pct_mf DOUBLE PRECISION DEFAULT 0,
        PRIMARY KEY (ts_code, trade_date)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_mf_code_date
    ON moneyflow(ts_code, trade_date)
    """,
    """
    CREATE TABLE IF NOT EXISTS financial_data (
        ts_code TEXT NOT NULL,
        ann_date TEXT,
        end_date TEXT,
        revenue DOUBLE PRECISION,
        net_profit DOUBLE PRECISION,
        total_assets DOUBLE PRECISION,
        pe DOUBLE PRECISION,
        pb DOUBLE PRECISION,
        ps DOUBLE PRECISION,
        PRIMARY KEY (ts_code, end_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_signals (
        id BIGINT DEFAULT unique_rowid(),
        ts_code TEXT NOT NULL,
        signal_date TEXT NOT NULL,
        signal_type TEXT,
        signal_score DOUBLE PRECISION,
        signal_price DOUBLE PRECISION,
        signal_desc TEXT,
        created_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_records (
        id BIGINT DEFAULT unique_rowid(),
        ts_code TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        action TEXT NOT NULL,
        price DOUBLE PRECISION,
        quantity BIGINT,
        amount DOUBLE PRECISION,
        reason TEXT,
        signal_type TEXT,
        zg_review TEXT,
        broker TEXT,
        fee DOUBLE PRECISION DEFAULT 0,
        tags TEXT,
        notes TEXT,
        created_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_log (
        id BIGINT DEFAULT unique_rowid(),
        data_type TEXT,
        ts_code TEXT,
        last_date TEXT,
        status TEXT,
        message TEXT,
        created_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_sync_log_type_date
    ON sync_log(data_type, last_date DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        id BIGINT DEFAULT unique_rowid(),
        ts_code TEXT NOT NULL,
        name TEXT,
        tags TEXT,
        added_date TEXT DEFAULT NOW()::STRING,
        alert_enabled BOOLEAN DEFAULT TRUE,
        notes TEXT,
        updated_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (id),
        UNIQUE(ts_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_response_log (
        id BIGINT DEFAULT unique_rowid(),
        ts_code TEXT,
        request_date TEXT,
        model TEXT,
        response_time_ms BIGINT,
        success BOOLEAN,
        error_message TEXT DEFAULT '',
        created_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_llm_log_code_date
    ON llm_response_log(ts_code, request_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_llm_log_date
    ON llm_response_log(request_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_llm_log_model
    ON llm_response_log(model)
    """,
]


def init_database() -> None:
    """初始化数据库表结构（双后端兼容，含核心表与自我改进跟踪表）。"""
    backend = _backend()
    with get_connection() as conn:
        cursor = conn.cursor()
        for ddl in _SCHEMA_DDL + _TRACKING_DDL:
            sql = _to_sqlite_ddl(ddl) if backend == "sqlite" else ddl
            cursor.execute(sql)
    logger.info("数据库表结构初始化完成 (backend=%s)", backend)


def drop_all_tables() -> None:
    """删除所有表（危险操作，仅用于测试）。"""
    tables = [
        "tracking_pool_self", "tracking_records_self",
        "monthly_reviews_self", "strategy_performance_self",
        "llm_response_log", "watchlist", "sync_log",
        "trade_records", "trade_signals", "financial_data",
        "moneyflow", "indicator_cache", "daily_kline", "stock_basic",
    ]
    with get_connection() as conn:
        cursor = conn.cursor()
        if _backend() == "crdb":
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        else:
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
    logger.info("所有表已删除")


def get_table_info(table_name: str) -> list[dict]:
    """获取表结构信息（双后端）。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if _backend() == "crdb":
            cursor.execute(
                """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = ?
                ORDER BY ordinal_position
                """,
                (table_name,),
            )
            return [
                {"name": r[0], "type": r[1], "nullable": r[2] == "YES", "default": r[3]}
                for r in cursor.fetchall()
            ]
        # SQLite
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [
            {"name": r[1], "type": r[2], "nullable": r[3] == 0, "default": r[4]}
            for r in cursor.fetchall()
        ]


def get_table_columns(table_name: str) -> set[str]:
    """获取表的列名集合（双后端，供动态 ALTER 探测使用）。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if _backend() == "crdb":
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
                (table_name,),
            )
            return {r[0] for r in cursor.fetchall()}
        cursor.execute(f"PRAGMA table_info({table_name})")
        return {r[1] for r in cursor.fetchall()}


def get_table_count(table_name: str) -> int:
    """获取表行数。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]


def get_all_tables() -> list[str]:
    """获取所有表名（双后端）。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        if _backend() == "crdb":
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [r[0] for r in cursor.fetchall()]


# 向后兼容
DB_PATH = get_db_path()


# ==================== 交易记录 CRUD ====================

def save_trade_record(record: dict) -> int:
    """保存交易记录，返回新记录 id。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trade_records
            (ts_code, trade_date, action, price, quantity, amount, reason, signal_type, zg_review, broker, fee, tags, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                record.get("ts_code"), record.get("trade_date"), record.get("action"),
                record.get("price"), record.get("quantity"), record.get("amount"),
                record.get("reason", ""), record.get("signal_type", ""),
                record.get("zg_review", ""), record.get("broker", ""),
                record.get("fee", 0), record.get("tags", ""), record.get("notes", ""),
            ),
        )
        return cursor.fetchone()[0]


def get_trade_records(ts_code: str = None, start_date: str = None, end_date: str = None, limit: int = 100) -> list:
    """获取交易记录。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT * FROM trade_records WHERE 1=1"
        params = []
        if ts_code:
            sql += " AND ts_code = ?"
            params.append(ts_code)
        if start_date:
            sql += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND trade_date <= ?"
            params.append(end_date)
        sql += " ORDER BY trade_date DESC LIMIT ?"
        params.append(limit)
        cursor.execute(sql, params)
        return cursor.fetchall()


def get_trade_record_by_id(trade_id: int) -> dict | None:
    """根据 ID 获取交易记录。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trade_records WHERE id = ?", (trade_id,))
        return cursor.fetchone()


def update_trade_record(trade_id: int, updates: dict) -> bool:
    """更新交易记录。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        set_parts = []
        params = []
        for key, value in updates.items():
            set_parts.append(f"{key} = ?")
            params.append(value)
        params.append(trade_id)
        cursor.execute(f"UPDATE trade_records SET {', '.join(set_parts)} WHERE id = ?", params)
        return cursor.rowcount > 0


def delete_trade_record(trade_id: int) -> bool:
    """删除交易记录。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM trade_records WHERE id = ?", (trade_id,))
        return cursor.rowcount > 0


def get_trade_summary(ts_code: str = None, start_date: str = None, end_date: str = None) -> dict:
    """获取交易汇总。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT COUNT(*) as total, SUM(amount) as total_amount FROM trade_records WHERE 1=1"
        params = []
        if ts_code:
            sql += " AND ts_code = ?"
            params.append(ts_code)
        if start_date:
            sql += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            sql += " AND trade_date <= ?"
            params.append(end_date)
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return {"total": row[0] if row else 0, "total_amount": row[1] if row else 0}


# ==================== 观察池 CRUD ====================

def add_watchlist_item(ts_code: str, name: str = "", tags: str = "", notes: str = "") -> int:
    """添加观察池项目，返回 id。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO watchlist (ts_code, name, tags, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (ts_code) DO UPDATE SET
                name = EXCLUDED.name,
                tags = EXCLUDED.tags,
                notes = EXCLUDED.notes,
                updated_at = NOW()::STRING
            RETURNING id
            """,
            (ts_code, name, tags, notes),
        )
        return cursor.fetchone()[0]


def remove_watchlist_item(ts_code: str) -> bool:
    """移除观察池项目。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM watchlist WHERE ts_code = ?", (ts_code,))
        return cursor.rowcount > 0


def get_watchlist(tags: str = None) -> list:
    """获取观察池列表。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT * FROM watchlist WHERE 1=1"
        params = []
        if tags:
            sql += " AND tags LIKE ?"
            params.append(f"%{tags}%")
        sql += " ORDER BY added_date DESC"
        cursor.execute(sql, params)
        return cursor.fetchall()


def update_watchlist_item(ts_code: str, updates: dict) -> bool:
    """更新观察池项目。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        set_parts = []
        params = []
        for key, value in updates.items():
            set_parts.append(f"{key} = ?")
            params.append(value)
        params.append(ts_code)
        cursor.execute(
            f"UPDATE watchlist SET {', '.join(set_parts)}, updated_at = NOW()::STRING WHERE ts_code = ?",
            params,
        )
        return cursor.rowcount > 0


# ==================== 其他辅助函数 ====================

def get_all_stock_codes(limit: int = None) -> list[str]:
    """获取所有股票代码。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT ts_code FROM stock_basic"
        if limit:
            sql += f" LIMIT {limit}"
        cursor.execute(sql)
        return [row[0] for row in cursor.fetchall()]


def record_llm_response(ts_code: str, model: str, response_time_ms: int, success: bool = True,
                        request_date: str = None, error_message: str = None) -> None:
    """记录 LLM 响应。"""
    if request_date is None:
        request_date = datetime.now().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO llm_response_log (ts_code, request_date, model, response_time_ms, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ts_code, request_date, model, response_time_ms, success, error_message or ""),
        )


def get_llm_response_log(ts_code: str = None, model: str = None, request_date: str = None,
                         limit: int = 100) -> list:
    """获取 LLM 响应日志（支持 ts_code / model / request_date 过滤）。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = "SELECT * FROM llm_response_log WHERE 1=1"
        params = []
        if ts_code:
            sql += " AND ts_code = ?"
            params.append(ts_code)
        if model:
            sql += " AND model = ?"
            params.append(model)
        if request_date:
            sql += " AND request_date = ?"
            params.append(request_date)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cursor.execute(sql, params)
        return cursor.fetchall()


def get_llm_response_stats(request_date: str = None) -> dict:
    """获取 LLM 响应统计（按日聚合）。"""
    with get_connection() as conn:
        cursor = conn.cursor()
        sql = (
            "SELECT COUNT(*) as total_calls, "
            "SUM(CASE WHEN success THEN 1 ELSE 0 END) as success_calls, "
            "SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failed_calls, "
            "AVG(response_time_ms) as avg_ms, "
            "MAX(response_time_ms) as max_ms, "
            "MIN(response_time_ms) as min_ms "
            "FROM llm_response_log WHERE 1=1"
        )
        params = []
        if request_date:
            sql += " AND request_date = ?"
            params.append(request_date)
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return {
            "total_calls": row[0] or 0,
            "success_calls": row[1] or 0,
            "failed_calls": row[2] or 0,
            "avg_ms": float(row[3]) if row[3] is not None else 0.0,
            "max_ms": float(row[4]) if row[4] is not None else 0.0,
            "min_ms": float(row[5]) if row[5] is not None else 0.0,
        }


# ==================== 跟踪表初始化 ====================

_TRACKING_DDL = [
    """
    CREATE TABLE IF NOT EXISTS tracking_pool_self (
        id BIGINT DEFAULT unique_rowid(),
        ts_code TEXT NOT NULL,
        name TEXT,
        add_date TEXT NOT NULL,
        remove_date TEXT,
        status TEXT DEFAULT 'active',
        track_reason TEXT,
        strategy_tags TEXT,
        notes TEXT,
        created_at TEXT DEFAULT NOW()::STRING,
        updated_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (ts_code, add_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tracking_records_self (
        id BIGINT DEFAULT unique_rowid(),
        ts_code TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        vol DOUBLE PRECISION,
        pct_chg DOUBLE PRECISION,
        amount DOUBLE PRECISION,
        j_value DOUBLE PRECISION,
        k_value DOUBLE PRECISION,
        d_value DOUBLE PRECISION,
        bbi DOUBLE PRECISION,
        macd_dif DOUBLE PRECISION,
        macd_dea DOUBLE PRECISION,
        macd_hist DOUBLE PRECISION,
        rsi_6 DOUBLE PRECISION,
        wr_6 DOUBLE PRECISION,
        boll_upper DOUBLE PRECISION,
        boll_mid DOUBLE PRECISION,
        boll_lower DOUBLE PRECISION,
        vol_ratio DOUBLE PRECISION,
        is_brick_red BIGINT DEFAULT 0,
        is_brick_green BIGINT DEFAULT 0,
        brick_count BIGINT DEFAULT 0,
        is_n_structure BIGINT DEFAULT 0,
        is_double_gun BIGINT DEFAULT 0,
        signal_type TEXT,
        signal_score DOUBLE PRECISION,
        signal_reason TEXT,
        stage TEXT,
        stage_confidence DOUBLE PRECISION,
        created_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (ts_code, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS monthly_reviews_self (
        id BIGINT DEFAULT unique_rowid(),
        review_month TEXT NOT NULL,
        ts_code TEXT NOT NULL,
        start_price DOUBLE PRECISION,
        start_j_value DOUBLE PRECISION,
        start_signal TEXT,
        end_price DOUBLE PRECISION,
        end_j_value DOUBLE PRECISION,
        end_signal TEXT,
        monthly_return DOUBLE PRECISION,
        max_drawdown DOUBLE PRECISION,
        max_gain DOUBLE PRECISION,
        buy_signals_count BIGINT,
        sell_signals_count BIGINT,
        correct_buy_signals BIGINT,
        correct_sell_signals BIGINT,
        review_summary TEXT,
        lessons_learned TEXT,
        strategy_adjustments TEXT,
        created_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (review_month, ts_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_performance_self (
        id BIGINT DEFAULT unique_rowid(),
        strategy_name TEXT NOT NULL,
        review_month TEXT NOT NULL,
        total_signals BIGINT,
        correct_signals BIGINT,
        accuracy_rate DOUBLE PRECISION,
        avg_return DOUBLE PRECISION,
        max_return DOUBLE PRECISION,
        min_return DOUBLE PRECISION,
        win_rate DOUBLE PRECISION,
        avg_drawdown DOUBLE PRECISION,
        max_drawdown DOUBLE PRECISION,
        sharpe_ratio DOUBLE PRECISION,
        strengths TEXT,
        weaknesses TEXT,
        adjustments TEXT,
        created_at TEXT DEFAULT NOW()::STRING,
        PRIMARY KEY (strategy_name, review_month)
    )
    """,
]


def init_tracking_tables(conn=None) -> None:
    """初始化自我改进系统跟踪表（双后端兼容）。"""
    if conn is None:
        with get_connection() as conn:
            _create_tracking_tables(conn)
    else:
        _create_tracking_tables(conn)


def _create_tracking_tables(conn) -> None:
    cursor = conn.cursor()
    backend = conn.backend
    for ddl in _TRACKING_DDL:
        sql = _to_sqlite_ddl(ddl) if backend == "sqlite" else ddl
        cursor.execute(sql)
    conn.commit()


if __name__ == "__main__":
    init_database()
    print("数据库初始化完成")
    print(f"表数量: {len(get_all_tables())}")
    for table in get_all_tables():
        count = get_table_count(table)
        print(f"  {table}: {count:,} 行")
