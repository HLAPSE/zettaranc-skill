#!/usr/bin/env python3
"""
在线选股脚本 — 遵循 Z哥理论：择时 → 找主线 → 选股

不依赖本地数据库，直接用 BaoStock 拉数据 + 内存计算。

用法:
    python scripts/online_screen.py --strategy B1 --limit 20
    python scripts/online_screen.py --strategy B1 --limit 20 --json
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    pass


def _safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _to_ts_code(bs_code: str) -> str:
    """sh.600487 -> 600487.SH"""
    market, code = bs_code.split(".")
    suffix = "SH" if market == "sh" else "SZ"
    return f"{code}.{suffix}"


# ==================== Step 1: 择时 ====================

def check_market_timing(bs) -> dict:
    """
    择时：用上证指数判断大盘状态
    - 白线（EMA10）在黄线（MA60）之上 = 多头，可交易
    - 白线在黄线之下 = 空头，空仓观望
    """
    import baostock as bs

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")

    rs = bs.query_history_k_data_plus(
        "sh.000001",
        "date,close",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
    )

    closes = []
    while rs.next():
        row = rs.get_row_data()
        closes.append(_safe_float(row[1]))

    if len(closes) < 60:
        return {"tradable": True, "direction": "未知", "reason": "数据不足，默认可交易"}

    # 白线 = EMA(EMA(C,10),10)
    ema10 = [closes[0]]
    for c in closes[1:]:
        ema10.append(ema10[-1] * 0.8 + c * 0.2)
    white_line = ema10[-1]
    for c in closes[1:]:
        ema10[-1] = ema10[-1] * 0.8 + c * 0.2  # 二次 EMA
    # 简化：直接用 EMA10 的二次平滑
    ema10_2 = [ema10[0]]
    for v in ema10[1:]:
        ema10_2.append(ema10_2[-1] * 0.8 + v * 0.2)
    white_line = ema10_2[-1]

    # 黄线 = MA60
    yellow_line = sum(closes[-60:]) / 60

    today_close = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else today_close
    pct_chg = (today_close - prev_close) / prev_close * 100 if prev_close else 0

    is_bullish = white_line > yellow_line

    result = {
        "tradable": is_bullish,
        "direction": "多头" if is_bullish else "空头",
        "close": round(today_close, 2),
        "pct_chg": round(pct_chg, 2),
        "white_line": round(white_line, 2),
        "yellow_line": round(yellow_line, 2),
        "reason": f"白线{'>' if is_bullish else '<'}黄线，{'可交易' if is_bullish else '空仓观望'}",
    }
    return result


# ==================== Step 2: 找主线 ====================

def fetch_hot_sectors(bs, top_n: int = 5) -> list[dict]:
    """
    找主线：拉全市场股票近期涨幅，按行业聚合，找强势板块
    """
    import baostock as bs

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

    # 1. 获取股票列表
    rs = bs.query_stock_basic()
    all_stocks = []
    while (rs.error_code == '0') and rs.next():
        row = rs.get_row_data()
        bs_code = row[0]
        name = row[1]
        type_val = row[4]
        status = row[5]
        if type_val != "1" or status != "1":
            continue
        if not bs_code.startswith(("sh.6", "sz.0", "sz.3")):
            continue
        all_stocks.append({"bs_code": bs_code, "name": name})

    print(f"  全市场股票: {len(all_stocks)} 只", file=sys.stderr)

    # 2. 获取行业分类
    industry_map = {}
    rs = bs.query_stock_industry()
    while (rs.error_code == '0') and rs.next():
        row = rs.get_row_data()
        # code, code_name, industry, industryClassification
        code = row[0]
        industry = row[2] if len(row) > 2 else "其他"
        industry_map[code] = industry

    # 3. 抽样拉近期涨幅（每 5 只取 1 只，避免太慢）
    sample_stocks = all_stocks[::5]
    print(f"  抽样股票: {len(sample_stocks)} 只 (每5只取1只)", file=sys.stderr)

    sector_gains = defaultdict(list)
    for i, stock in enumerate(sample_stocks):
        if (i + 1) % 100 == 0:
            print(f"  找主线进度: {i+1}/{len(sample_stocks)}", file=sys.stderr)
        try:
            rs = bs.query_history_k_data_plus(
                stock["bs_code"], "date,close",
                start_date=start_date, end_date=end_date, frequency="d",
            )
            closes = []
            while rs.next():
                closes.append(_safe_float(rs.get_row_data()[1]))
            if len(closes) < 2:
                continue
            gain = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0
            industry = industry_map.get(stock["bs_code"], "其他")
            sector_gains[industry].append(gain)
        except Exception:
            continue

    # 4. 按行业平均涨幅排序
    sector_avg = []
    for sector, gains in sector_gains.items():
        if len(gains) < 3:
            continue
        avg_gain = sum(gains) / len(gains)
        sector_avg.append({
            "sector": sector,
            "avg_gain": round(avg_gain, 2),
            "stock_count": len(gains),
        })

    sector_avg.sort(key=lambda x: x["avg_gain"], reverse=True)
    return sector_avg[:top_n]


def fetch_sector_stocks(bs, hot_sectors: list[str], limit: int = 300) -> list[dict]:
    """获取主线板块中的股票列表"""
    import baostock as bs

    # 获取行业分类
    industry_map = {}
    rs = bs.query_stock_industry()
    while (rs.error_code == '0') and rs.next():
        row = rs.get_row_data()
        code = row[0]
        industry = row[2] if len(row) > 2 else "其他"
        industry_map[code] = industry

    # 获取股票列表，只保留在主线板块中的
    rs = bs.query_stock_basic()
    stocks = []
    while (rs.error_code == '0') and rs.next():
        row = rs.get_row_data()
        bs_code = row[0]
        name = row[1]
        type_val = row[4]
        status = row[5]
        if type_val != "1" or status != "1":
            continue
        if not bs_code.startswith(("sh.6", "sz.0", "sz.3")):
            continue
        industry = industry_map.get(bs_code, "其他")
        if industry not in hot_sectors:
            continue
        stocks.append({
            "ts_code": _to_ts_code(bs_code),
            "name": name,
            "bs_code": bs_code,
            "industry": industry,
        })
        if len(stocks) >= limit:
            break

    return stocks


# ==================== Step 3: 选股 ====================

def fetch_klines(bs_code: str, days: int = 150) -> list:
    """用 BaoStock 拉日线，返回 DailyData 列表"""
    import baostock as bs
    from modules.indicators.core import DailyData

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days + 60)).strftime("%Y-%m-%d")

    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,code,open,high,low,close,volume,amount,turn,pctChg",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2",
    )

    if rs.error_code != '0':
        return []

    klines = []
    prev_close = 0
    while rs.next():
        row = rs.get_row_data()
        close = _safe_float(row[5])
        if close == 0:
            continue
        k = DailyData(
            ts_code=_to_ts_code(row[1]),
            trade_date=row[0].replace("-", ""),
            open=_safe_float(row[2]),
            high=_safe_float(row[3]),
            low=_safe_float(row[4]),
            close=close,
            vol=_safe_float(row[6]),
            amount=_safe_float(row[7]),
            pct_chg=_safe_float(row[9]),
            prev_close=prev_close,
        )
        klines.append(k)
        prev_close = close

    return klines[-days:]


def screen_online(strategy: str, limit: int) -> dict:
    """在线选股主流程：择时 → 找主线 → 选股"""
    import baostock as bs
    from modules.screener import (
        StockScore, score_b1_opportunity, score_trend,
        score_volume_pattern, score_risk, is_perfect_pattern,
        _filter_stock, _check_centipede, _check_sandglass_min,
    )

    criteria_map = {
        "B1": "b1", "完美图形": "perfect", "超级B1": "super_b1",
        "建仓波": "build_wave", "吸筹": "xishou", "安全": "safe",
        "量比战法": "volume_ratio_super", "超跌": "oversold", "突破": "breakout",
    }
    criteria = criteria_map.get(strategy, strategy.lower())

    bs.login()
    try:
        # === Step 1: 择时 ===
        print("=== Step 1: 择时 ===", file=sys.stderr)
        market = check_market_timing(bs)
        print(f"  大盘: {market['direction']} | 收盘:{market.get('close','-')} | {market['reason']}", file=sys.stderr)

        if not market["tradable"]:
            print("  => 空头市场，空仓观望，不选股", file=sys.stderr)
            return {
                "market": market,
                "hot_sectors": [],
                "results": [],
                "skipped": "空头市场，空仓观望",
            }

        # === Step 2: 找主线 ===
        print("\n=== Step 2: 找主线 ===", file=sys.stderr)
        hot_sectors = fetch_hot_sectors(bs, top_n=5)
        print(f"  强势板块 TOP 5:", file=sys.stderr)
        for s in hot_sectors:
            print(f"    {s['sector']}: 均涨{s['avg_gain']:+.1f}% ({s['stock_count']}只)", file=sys.stderr)

        sector_names = [s["sector"] for s in hot_sectors]

        # === Step 3: 选股 ===
        print("\n=== Step 3: 选股 ===", file=sys.stderr)
        stocks = fetch_sector_stocks(bs, sector_names, limit=300)
        print(f"  主线板块股票: {len(stocks)} 只", file=sys.stderr)

        results = []
        for i, stock in enumerate(stocks):
            bs_code = stock["bs_code"]
            ts_code = stock["ts_code"]
            name = stock["name"]
            industry = stock["industry"]

            if (i + 1) % 50 == 0:
                print(f"  进度: {i+1}/{len(stocks)}", file=sys.stderr)

            try:
                klines = fetch_klines(bs_code, days=150)
                if not klines or len(klines) < 30:
                    continue

                b1_score, b1_reasons = score_b1_opportunity(klines)
                trend_score, trend_dir = score_trend(klines)
                volume_score, volume_reasons = score_volume_pattern(klines)
                risk_score, risk_warnings = score_risk(klines)

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

                sandglass_is_perfect = False
                try:
                    from modules.indicators import calculate_sandglass_score
                    sg = calculate_sandglass_score(klines)
                    sandglass_is_perfect = sg.get("is_perfect", False)
                except Exception:
                    pass

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

                if _check_centipede(klines):
                    continue
                if _check_sandglass_min(klines):
                    continue

                result = (ts_code, klines, score)
                if _filter_stock(result, criteria):
                    score.reasons.insert(0, f"[{industry}]")
                    results.append(score)

            except Exception as e:
                print(f"  {ts_code} {name}: ERROR {e}", file=sys.stderr)
                continue

        results.sort(key=lambda x: x.score, reverse=True)
        results = results[:limit] if limit > 0 else results

        return {
            "market": market,
            "hot_sectors": hot_sectors,
            "results": results,
        }
    finally:
        bs.logout()


def main():
    parser = argparse.ArgumentParser(description="在线选股 (BaoStock 直连, Z哥三步法)")
    parser.add_argument("--strategy", default="B1", help="选股策略")
    parser.add_argument("--limit", type=int, default=20, help="输出上限")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    data = screen_online(args.strategy, args.limit)
    results = data["results"]
    market = data["market"]

    if args.json:
        output = {
            "market": market,
            "hot_sectors": data["hot_sectors"],
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
        print(f"Z哥三步选股: 择时 → 找主线 → 选股")
        print(f"{'=' * 60}")
        print(f"\n[择时] {market['direction']} | {market['reason']}")
        if not market["tradable"]:
            print("\n  => 空头市场，空仓观望")
            return

        print(f"\n[主线] 强势板块:")
        for s in data["hot_sectors"]:
            print(f"  {s['sector']}: 均涨{s['avg_gain']:+.1f}% ({s['stock_count']}只)")

        print(f"\n[选股] 策略={args.strategy}, 命中={len(results)} 只")
        print(f"{'=' * 60}")
        for r in results:
            print(f"  {r.ts_code} {r.name:<8} | 评分:{r.score:5.1f} | {r.rating}")
            if r.reasons:
                print(f"    理由: {', '.join(r.reasons[:3])}")
        print()


if __name__ == "__main__":
    main()
