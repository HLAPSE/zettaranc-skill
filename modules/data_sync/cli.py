"""Command line interface for data synchronization."""

from __future__ import annotations

import logging

from .syncer import DataSyncer


def main() -> None:
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="数据同步工具（BaoStock + AkShare）")
    parser.add_argument(
        "action",
        choices=["init", "sync", "status"],
        help="操作: init=初始化数据库, sync=同步数据, status=查看状态",
    )
    parser.add_argument("--ts_code", help="股票代码，如 000001.SZ")
    parser.add_argument("--days", type=int, default=730, help="同步天数")
    parser.add_argument("--indicators", action="store_true", help="同步完成后计算并缓存技术指标（indicator_cache 表）")
    parser.add_argument(
        "--skip-indicators",
        action="store_true",
        help="跳过指标缓存同步（默认单只股票自动同步，批量需指定 --indicators）",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    if args.action == "init":
        from ..database import init_database

        init_database()
        print("数据库初始化完成")

    elif args.action == "sync":
        syncer = DataSyncer()

        if args.ts_code:
            syncer.sync_daily_kline(args.ts_code)
            if not args.skip_indicators:
                print(f"正在同步指标缓存: {args.ts_code} ...")
                syncer.sync_indicator_cache(args.ts_code, days=args.days)
        else:
            syncer.sync_stock_basic()
            syncer.sync_all_daily_kline(days=args.days)
            if args.indicators and not args.skip_indicators:
                print("正在批量同步指标缓存...")
                syncer.sync_all_indicators()

        print("同步完成")
        print(syncer.get_sync_status())

    elif args.action == "status":
        syncer = DataSyncer()
        status = syncer.get_sync_status()
        print("=" * 50)
        print(f"数据库: {status['db_path']}")
        print(f"股票数量: {status['stock_count']}")
        print(f"K线数据: {status['kline_count']}")
        print("-" * 50)
        print("同步状态:")
        for s in status["sync_status"]:
            print(f"  {s['data_type']}: {s['last_date']} ({s['status']})")


if __name__ == "__main__":
    main()
