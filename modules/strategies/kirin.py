from typing import List, Dict, Any
from .core import StrategyType

def analyze_kirin_phase(klines: List[Dict]) -> Dict[str, Any]:
    """
    分析麒麟会四阶段（吸→拉→派→落）

    基于最近 30 天量价特征判断当前最可能阶段
    """
    if len(klines) < 30:
        return {"phase": "UNKNOWN", "confidence": 0}

    recent = klines[-30:]
    closes = [k['close'] for k in recent]
    vols = [k['vol'] for k in recent]
    avg_vol = sum(vols) / len(vols)

    # 1. 趋势方向
    first_half = closes[:15]
    second_half = closes[15:]
    trend = "UP" if second_half[-1] > first_half[0] else "DOWN"

    # 2. 量价关系
    red_vol = sum(k['vol'] for k in recent if k['is_rise'])
    green_vol = sum(k['vol'] for k in recent if not k['is_rise'])
    red_days = sum(1 for k in recent if k['is_rise'])
    green_days = 30 - red_days

    red_avg = red_vol / red_days if red_days > 0 else 0
    green_avg = green_vol / green_days if green_days > 0 else 0

    # 3. 阶段判定
    phase = "UNKNOWN"
    confidence = 0.5

    # 吸筹：低位、缩量震荡、红肥绿瘦（阳线量能 > 阴线）
    is_low = min(closes) <= max(closes) * 0.85
    is_shrink = avg_vol < sum(klines[i]['vol'] for i in range(-60, -30)) / 30 if len(klines) >= 60 else False
    if is_low and red_avg > green_avg * 1.2:
        phase = "吸筹"
        confidence = 0.75

    # 拉升：放量、连续上涨、趋势向上
    up_days = sum(1 for i in range(1, len(recent)) if recent[i]['close'] > recent[i-1]['close'])
    if trend == "UP" and avg_vol > (sum(klines[i]['vol'] for i in range(-60, -30)) / 30 if len(klines) >= 60 else avg_vol) * 1.3 and up_days >= 18:
        phase = "拉升"
        confidence = 0.8

    # 派发：高位、放量滞涨、绿肥红瘦
    is_high = closes[-1] >= max(closes[:20]) * 0.95
    if is_high and green_avg > red_avg * 1.1 and abs(closes[-1] - closes[0]) / closes[0] < 0.05:
        phase = "派发"
        confidence = 0.75

    # 回落：缩量下跌、无承接
    if trend == "DOWN" and avg_vol < (sum(klines[i]['vol'] for i in range(-60, -30)) / 30 if len(klines) >= 60 else avg_vol) * 0.8 and up_days < 10:
        phase = "回落"
        confidence = 0.7

    phase_map = {
        "吸筹": StrategyType.XISHOU,
        "拉升": StrategyType.LASHENG,
        "派发": StrategyType.PAIFA,
        "回落": StrategyType.LUOLUO,
        "UNKNOWN": None,
    }

    return {
        "phase": phase,
        "confidence": confidence,
        "strategy_type": phase_map.get(phase),
        "trend": trend,
        "red_avg_vol": round(red_avg, 2),
        "green_avg_vol": round(green_avg, 2),
        "avg_vol": round(avg_vol, 2),
    }
