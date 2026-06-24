#!/usr/bin/env python3
"""
在线选股脚本 — 直接用 AkShare 拉数据 + 内存计算，不依赖本地数据库

用法:
    python scripts/online_screen.py --strategy B1 --limit 20
    python scripts/online_screen.py --strategy B1 --limit 20 --json
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass


def fetch_stock_list(limit: int = 0) -> list[dict]:
    """用 AkShare 拉股票列表"""
    import akshare as ak

    df = ak.stock_info_a_code_name()
    stocks = []
    for _, row in df.iterrows():
        code = str(row["code"])
        name = str(row["name"])
        # 拼接后缀
        if code.startswith("6"):
            ts_code = f"{code}.SH"
        elif code.startswith(("0", "3")):
            ts_code = f"{code}.SZ"
        elif code.startswith(("8", "4")):
            ts_code = f"{code}.BJ"
        else:
            continue
        stocks.append({"ts_code": ts_code, "name": name, "code": code})

    if limit > 0:
        stocks = stocks[:limit]
    return stocks


def fetch_klines(code: str, days: int = 150) -> list:
    """用 AkShare 拉日线，返回 DailyData 列表"""
    import akshare as ak
    from modules.indicators.core import DailyData

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=days + 60)).strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date,
                                end_date=end_date, adjust="qfq")
    except Exception:
        return []

    if df is None or df.empty:
        return []

    # 转成 DailyData
    klines = []
    prev_close = 0
    for _, row in df.iterrows():
        close = float(row["收盘"])
        vol = float(row["成交量"])
        k = DailyData(
            ts_code=code,
            trade_date=str(row["日期"]).replace("-", ""),
            open=float(row["开盘"]),
            high=float(row["最高"]),
            low=float(row["最低"]),
            close=close,
            vol=vol,
            amount=float(row["成交额"]),
            pct_chg=float(row.get("涨跌幅", 0)),
            prev_close=prev_close,
        )
        klines.append(k)
        prev_close = close

    return klines[-days:]


def screen_online(strategy: str, limit: int, scan_count: int = 300) -> list[dict]:
    """在线选股，返回结果列表"""
    from modules.screener import (
        StockScore, score_b1_opportunity, score_trend,
        score_volume_pattern, score_risk, is_perfect_pattern,
        _filter_stock, _check_centipede, _check_sandglass_min,
    )

    # 策略中文 → 英文 criteria 映射
    criteria_map = {
        "B1": "b1", "完美图形": "perfect", "超级B1": "super_b1",
        "建仓波": "build_wave", "吸筹": "xishou", "安全": "safe",
        "量比战法": "volume_ratio_super", "超跌": "oversold", "突破": "breakout",
    }
    criteria = criteria_map.get(strategy, strategy.lower())

    print(f"正在获取股票列表 (扫描前 {scan_count} 只)...", file=sys.stderr)
    stocks = fetch_stock_list(scan_count)
    print(f"共 {len(stocks)} 只股票待扫描", file=sys.stderr)

    results = []
    for i, stock in enumerate(stocks):
        ts_code = stock["ts_code"]
        name = stock["name"]
        code = stock["code"]

        if (i + 1) % 50 == 0:
            print(f"  进度: {i+1}/{len(stocks)}", file=sys.stderr)

        try:
            klines = fetch_klines(code, days=150)
            if not klines or len(klines) < 30:
                continue

            # 构造 StockScore（绕过数据库）
            b1_score, b1_reasons = score_b1_opportunity(klines)
            trend_score, trend_dir = score_trend(klines)
            volume_score, volume_reasons = score_volume_pattern(klines)
            risk_score, risk_warnings = score_risk(klines)

            # 三波/麒麟会
            wave_stage = "未知"
            kirin_stage = "未知"
            try:
                from modules.indicators import detect_three_waves, detect_kirin_stage
                wave = detect_three_waves(klines)
                wave_stage = wave["wave"]
                kirin = detect_kirin_stage(klines)
                kirin_stage = kirin["stage"]
            except Exception:
                pass

            # 沙漏
            sandglass_is_perfect = False
            try:
                from modules.indicators import calculate_sandglass_score
                sg = calculate_sandglass_score(klines)
                sandglass_is_perfect = sg.get("is_perfect", False)
            except Exception:
                pass

            # 综合评分
            total_score = b1_score * 0.3 + trend_score * 0.25 + volume_score * 0.25 + risk_score * 0.2

            is_perfect, perfect_reasons = is_perfect_pattern(klines)
            if is_perfect:
                total_score = min(100, total_score * 1.1)
                b1_reasons.extend(perfect_reasons)

            if wave_stage == "建仓波":
                total_score = min(100, total_score * 1.05)
            elif wave_stage == "冲刺波" or kirin_stage == "派发":
                total_score = max(0, total_score * 0.7)
            elif kirin_stage == "吸筹":
                total_score = min(100, total_score * 1.08)

            if sandglass_is_perfect:
                total_score = min(100, total_score + 10)

            score = StockScore(
                ts_code=ts_code,
                name=name,
                score=round(total_score, 1),
                b1_score=round(b1_score, 1),
                trend_score=round(trend_score, 1),
                volume_score=round(volume_score, 1),
                risk_score=round(risk_score, 1),
                reasons=b1_reasons + volume_reasons,
                warnings=risk_warnings,
            )

            # 硬过滤
            if _check_centipede(klines):
                continue
            if _check_sandglass_min(klines):
                continue

            # 条件过滤
            result = (ts_code, klines, score)
            if _filter_stock(result, criteria):
                results.append(score)

        except Exception as e:
            print(f"  {ts_code} {name}: ERROR {e}", file=sys.stderr)
            continue

    # 按评分排序
    results.sort(key=lambda x: x.score, reverse=True)
    return results[:limit] if limit > 0 else results


def main():
    parser = argparse.ArgumentParser(description="在线选股 (AkShare 直连)")
    parser.add_argument("--strategy", default="B1", help="选股策略")
    parser.add_argument("--limit", type=int, default=20, help="输出上限")
    parser.add_argument("--scan", type=int, default=300, help="扫描股票数量")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    results = screen_online(args.strategy, args.limit, args.scan)

    if args.json:
        output = {
            "criteria": args.strategy,
            "count": len(results),
            "stocks": [
                {
                    "ts_code": r.ts_code,
                    "name": r.name,
                    "score": r.score,
                    "rating": r.rating,
                    "reasons": getattr(r, "reasons", []),
                    "warnings": getattr(r, "warnings", []),
                }
                for r in results
            ],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print(f"在线选股 (策略={args.strategy}, 命中={len(results)} 只)")
        print(f"{'=' * 60}")
        for r in results:
            print(f"  {r.ts_code} {r.name:<8} | 评分:{r.score:5.1f} | {r.rating}")
            if r.reasons:
                print(f"    理由: {', '.join(r.reasons[:3])}")
        print()


if __name__ == "__main__":
    main()
