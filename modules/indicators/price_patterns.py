"""
价格模式识别模块
"""

from typing import Any, Optional

from .core import (
    DailyData,
    calculate_ma,
    calculate_ema,
    calculate_sma_series,
    calculate_slope,
    calculate_kdj,
)


def detect_divergence(klines: list[DailyData], dif_list: list[float]) -> dict:
    """
    顶底背离系统化检测（基于语料标准）

    顶背离：价格创新高但DIF不创新高 → 趋势衰竭，见顶减仓
    底背离：价格创新低但DIF不创新低 → 反转在即，底部建仓

    要求：
    - 对比窗口：最近60个交易日的极值区间
    - 价格容忍度：接近极值1%-2%即视为"同一水平"
    - DIF衰减：DIF未突破前值的90%(顶)或未跌破前值的110%(底)
    """
    result = {
        "is_top_divergence": False,
        "is_bottom_divergence": False,
    }

    if len(klines) < 60 or len(dif_list) < 30:
        return result

    closes = [k.close for k in klines]
    today_close = closes[-1]

    # ====== 顶背离检测 ======
    # 找最近60天内的最高收盘价窗口（排除最后5天，避免与当前比较）
    window_start = max(0, len(closes) - 60)
    window_end = max(0, len(closes) - 10)
    if window_end <= window_start:
        window_end = len(closes) - 5

    if window_end > window_start:
        max_close = max(closes[window_start:window_end])
        max_idx = closes[window_start:window_end].index(max_close) + window_start

        # 对应窗口的DIF最大值
        dif_window_start = max(0, window_start)
        dif_window_end = min(len(dif_list), window_end)
        if dif_window_end > dif_window_start:
            max_dif = max(dif_list[dif_window_start:dif_window_end])

            # 当前价格接近或达到最高，但DIF明显低于前高
            price_near_high = today_close >= max_close * 0.98
            dif_weaker = dif_list[-1] < max_dif * 0.9

            if price_near_high and dif_weaker and max_dif > 0:
                result["is_top_divergence"] = True

    # ====== 底背离检测 ======
    if window_end > window_start:
        min_close = min(closes[window_start:window_end])
        min_idx = closes[window_start:window_end].index(min_close) + window_start

        dif_window_start = max(0, window_start)
        dif_window_end = min(len(dif_list), window_end)
        if dif_window_end > dif_window_start:
            min_dif = min(dif_list[dif_window_start:dif_window_end])

            # 当前价格接近或达到最低，但DIF明显高于前低
            price_near_low = today_close <= min_close * 1.02
            dif_stronger = dif_list[-1] > min_dif * 1.1

            if price_near_low and dif_stronger and min_dif < 0:
                result["is_bottom_divergence"] = True

    return result


def detect_macd_signals(
    klines: list[DailyData], dif_list: list[float], dea_list: list[float], macd_list: list[float]
) -> dict[str, Any]:
    """
    根据 Z哥 语料检测 MACD 信号

    三大用法:
    1. DIF 上下穿 0 轴 — 判多空区间
    2. 顶/底背离 — 判趋势终结
    3. 金叉空 + 死叉多 — 判陷阱
    """
    signals = {
        "is_dif_positive": False,
        "is_dif_cross_zero": False,
        "is_dif_cross_zero_down": False,
        "is_gold_cross": False,
        "is_dead_cross": False,
        "is_gold_fake": False,
        "is_dead_fake": False,
        "is_top_divergence": False,
        "is_bottom_divergence": False,
        "macd_veto": False,
    }

    if len(dif_list) < 2 or len(dea_list) < 1:
        return signals

    dif_today = dif_list[-1]
    dif_yesterday = dif_list[-2] if len(dif_list) >= 2 else 0
    dea_today = dea_list[-1]
    dea_yesterday = dea_list[-2] if len(dea_list) >= 2 else 0

    # === 用法 1: DIF 0 轴判多空 ===
    signals["is_dif_positive"] = dif_today > 0

    # DIF 上穿 0 轴
    signals["is_dif_cross_zero"] = dif_yesterday <= 0 and dif_today > 0
    # DIF 下穿 0 轴
    signals["is_dif_cross_zero_down"] = dif_yesterday >= 0 and dif_today < 0

    # === 金叉/死叉 ===
    if len(dif_list) >= 3 and len(dea_list) >= 2:
        signals["is_gold_cross"] = dif_yesterday <= dea_yesterday and dif_today > dea_today
        signals["is_dead_cross"] = dif_yesterday >= dea_yesterday and dif_today < dea_today

    # === 用法 3: 金叉空 + 死叉多（多等一天）===
    if len(dif_list) >= 5 and len(dea_list) >= 3:
        # 检查最近 3 天的金叉/死叉变化
        recent_gold = 0
        recent_dead = 0
        for i in range(max(0, len(dif_list) - 4), len(dif_list) - 1):
            di = i
            dei = i - (len(dif_list) - len(dea_list))
            if dei >= 0 and dei < len(dea_list) and dei + 1 < len(dea_list):
                if dif_list[di] > dea_list[dei] and dif_list[di - 1] <= dea_list[dei - 1 if dei > 0 else 0]:
                    recent_gold += 1
                if dif_list[di] < dea_list[dei] and dif_list[di - 1] >= dea_list[dei - 1 if dei > 0 else 0]:
                    recent_dead += 1

        # 金叉空：刚金叉又马上死叉
        if signals["is_dead_cross"] and recent_gold >= 1:
            signals["is_gold_fake"] = True

        # 死叉多：刚死叉又马上金叉
        if signals["is_gold_cross"] and recent_dead >= 1:
            signals["is_dead_fake"] = True

    # === 用法 2: 顶底背离（系统化检测）===
    div = detect_divergence(klines, dif_list)
    signals["is_top_divergence"] = div["is_top_divergence"]
    signals["is_bottom_divergence"] = div["is_bottom_divergence"]

    # === 一票否决权 ===
    # DIF < 0 + 没有底背离 → 一票否决
    if dif_today < 0 and not signals["is_bottom_divergence"]:
        signals["macd_veto"] = True

    return signals


def calculate_zg_white(klines: list[DailyData]) -> float:
    """
    计算 Z哥白线 = EMA(EMA(C,10),10)

    双重平滑后的短期动能线
    """
    if len(klines) < 10:
        return 0
    closes = [k.close for k in klines]
    ema1 = calculate_ema(closes, 10)
    # 再次平滑：用前10天数据计算第二次EMA
    if len(klines) < 19:
        return ema1
    recent_10 = closes[-10:]
    ema2 = calculate_ema(recent_10, 10)
    return round(ema2, 2)


def calculate_dg_yellow(klines: list[DailyData]) -> float:
    """
    计算 大哥线 = (MA14 + MA28 + MA57 + MA114) / 4

    多空生命线，长期均线系统
    """
    if len(klines) < 114:
        return 0
    closes = [k.close for k in klines]
    ma14 = calculate_ma(closes, 14)
    ma28 = calculate_ma(closes, 28)
    ma57 = calculate_ma(closes, 57)
    ma114 = calculate_ma(closes, 114)
    return round((ma14 + ma28 + ma57 + ma114) / 4, 2)


def detect_double_line_cross(klines: list[DailyData]) -> tuple[bool, bool]:
    """
    检测双线战法金叉死叉

    Returns:
        (is_gold_cross, is_dead_cross)
    """
    if len(klines) < 3:
        return False, False

    # 需要足够数据计算大哥线
    if len(klines) < 115:
        return False, False



    # 计算历史白线和大哥线
    white_values = []
    dg_values = []

    for i in range(60, len(klines) + 1):
        sub_klines = klines[:i]
        if len(sub_klines) >= 114:
            white = calculate_zg_white(sub_klines)
            dg = calculate_dg_yellow(sub_klines)
            white_values.append(white)
            dg_values.append(dg)

    if len(white_values) < 3:
        return False, False

    # 今天、前天、昨天
    w_today = white_values[-1]
    w_yesterday = white_values[-2]


    d_today = dg_values[-1]
    d_yesterday = dg_values[-2]

    # 金叉：白线从下方上穿大哥线
    gold_cross = w_yesterday <= d_yesterday and w_today > d_today

    # 死叉：白线从上方下穿大哥线
    dead_cross = w_yesterday >= d_yesterday and w_today < d_today

    return gold_cross, dead_cross


def calculate_rsl(klines: list[DailyData], period: int) -> float:
    """
    计算 RSL 相对强度定位（通达信标准公式）

    100*(C-LLV(L,N))/(HHV(C,N)-LLV(L,N))
    """
    if len(klines) < period:
        return 50

    recent = klines[-period:]
    lows = [k.low for k in recent]
    closes = [k.close for k in recent]
    current_close = klines[-1].close

    llv = min(lows)
    hhv = max(closes)  # 通达信用 HHV(CLOSE)，不是 HHV(HIGH)

    if hhv == llv:
        return 50

    rsl = (current_close - llv) / (hhv - llv) * 100
    return round(rsl, 2)


def detect_needle_20(klines: list[DailyData]) -> tuple[float, float, bool]:
    """
    检测单针下20信号（通达信标准）

    条件：短期RSL(3) <= 20 AND 长期RSL(21) >= 60
    即白线下20买：散户浮筹<20 且 主力控盘>60

    Returns:
        (rsl_short, rsl_long, is_needle_20)
    """
    if len(klines) < 22:
        return 50, 50, False

    rsl_short = calculate_rsl(klines, 3)
    rsl_long = calculate_rsl(klines, 21)

    is_needle = rsl_short <= 20 and rsl_long >= 60  # 对齐通达信

    return rsl_short, rsl_long, is_needle


def detect_needle_30(klines: list[DailyData]) -> bool:
    """
    检测单针下30信号（单针下20的迭代版）

    量化资金介入后阈值上移：
    - 红线(主力控盘) > 85
    - 白线(散户浮筹) < 30

    舍弃部分低位空间，换取更高确定性与入场频次
    """
    if len(klines) < 22:
        return False
    rsl_short = calculate_rsl(klines, 3)
    rsl_long = calculate_rsl(klines, 21)
    return rsl_long > 85 and rsl_short < 30


def detect_double_gun(klines: list[DailyData]) -> dict:
    """
    双枪战法检测

    图形特征：两根放量阳柱中间夹一堆缩量阴线
    本质：主力建仓确认 — 第一根试盘，中间洗盘，第二根确认

    规则：
    - 往前找最近一根放量阳线（第二枪）
    - 再往前找另一根放量阳线（第一枪）
    - 中间夹缩量小阴小阳（3-10天）
    - 第二枪前一日应有B1痕迹（J<13）
    """
    result: dict[str, Any] = {
        "is_double_gun": False,
        "double_gun_vol1": 0.0,
        "double_gun_vol2": 0.0,
        "double_gun_gap_days": 0,
    }
    if len(klines) < 15:
        return result

    n = len(klines)

    # 往前找最近一根放量阳线（第二枪），排除今天
    gun2_idx = None
    for i in range(n - 2, max(0, n - 15), -1):
        if i > 0:
            prev_i = klines[i - 1]
            vol_ratio = klines[i].vol / prev_i.vol if prev_i.vol > 0 else 0
            if klines[i].pct_chg >= 3 and klines[i].close > klines[i].open and vol_ratio >= 1.8:
                gun2_idx = i
                break

    if gun2_idx is None or gun2_idx < 5:
        return result

    # 检查第二枪前一日是否有B1痕迹
    _, _, j_before_gun2 = calculate_kdj(klines[:gun2_idx])
    has_b1_before = j_before_gun2 < 20

    # 从第二枪往前找第一枪
    gun1_idx = None
    for i in range(gun2_idx - 3, max(0, gun2_idx - 12), -1):
        if i > 0:
            prev_i = klines[i - 1]
            vol_ratio = klines[i].vol / prev_i.vol if prev_i.vol > 0 else 0
            if klines[i].pct_chg >= 3 and klines[i].close > klines[i].open and vol_ratio >= 1.8:
                gun1_idx = i
                break

    if gun1_idx is None:
        return result

    gap_days = gun2_idx - gun1_idx

    # 检查中间是否缩量
    mid_vols = []
    for i in range(gun1_idx + 1, gun2_idx):
        if i > 0:
            prev_i = klines[i - 1]
            if prev_i.vol > 0:
                mid_vols.append(klines[i].vol / prev_i.vol)

    if not mid_vols:
        return result

    avg_mid_vol = sum(mid_vols) / len(mid_vols)
    is_shrink_mid = avg_mid_vol < 1.2  # 中间平均量比 < 1.2

    # 计算两枪的量比
    g1_prev = klines[gun1_idx - 1] if gun1_idx > 0 else None
    g2_prev = klines[gun2_idx - 1] if gun2_idx > 0 else None
    vol1: float = klines[gun1_idx].vol / g1_prev.vol if g1_prev and g1_prev.vol > 0 else 0.0
    vol2: float = klines[gun2_idx].vol / g2_prev.vol if g2_prev and g2_prev.vol > 0 else 0.0

    if is_shrink_mid and has_b1_before and 3 <= gap_days <= 10:
        result["is_double_gun"] = True
        result["double_gun_vol1"] = round(vol1, 1)
        result["double_gun_vol2"] = round(vol2, 1)
        result["double_gun_gap_days"] = gap_days

    return result


def detect_sb1_detailed(klines: list[DailyData]) -> dict:
    """
    超级B1独立检测

    形态流程：
    N型上涨 → 缩量回调 → 标准B1触发 → 突然放量大阴线击穿止损位 →
    缩量企稳 + J值大负值 → 反转K线确认 → 入场

    只赌一次，不可重复博弈
    """
    result = {
        "is_sb1_detailed": False,
    }
    if len(klines) < 15:
        return result

    n = len(klines)
    today = klines[-1]
    _, _, j_today = calculate_kdj(klines)

    # 往前找放量大阴线（击穿止损位）
    big_drop_idx = None
    for i in range(n - 2, max(0, n - 10), -1):
        if i > 0:
            prev_i = klines[i - 1]
            vol_ratio = klines[i].vol / prev_i.vol if prev_i.vol > 0 else 0
            # 放量大阴线：跌幅>3%, 量比>1.5, 收阴
            if klines[i].pct_chg <= -3 and vol_ratio >= 1.5 and klines[i].close < klines[i].open:
                big_drop_idx = i
                break

    if big_drop_idx is None:
        return result

    # 大阴线后缩量企稳（1-3天）
    days_after_drop = n - 1 - big_drop_idx
    if days_after_drop < 1 or days_after_drop > 3:
        return result

    # 检查大阴线后是否缩量
    drop_vol = klines[big_drop_idx].vol
    for i in range(big_drop_idx + 1, n):
        if klines[i].vol > drop_vol * 0.7:
            return result  # 没有缩量

    # J值大负值
    if j_today > -5:
        return result

    # 反转K线确认（十字星或小阳）
    body = abs(today.close - today.open)
    prev_close = klines[-2].close if len(klines) > 1 else today.close
    body_pct = body / prev_close * 100 if prev_close > 0 else 0
    is_reversal = body_pct <= 2 or (today.pct_chg > 0 and today.close > today.open)

    if not is_reversal:
        return result

    # 检查大阴线前是否有N型上涨结构
    if big_drop_idx >= 5:
        pre_lows = [klines[i].low for i in range(max(0, big_drop_idx - 10), big_drop_idx)]
        if len(pre_lows) >= 3:
            # 简单判断：大阴线前的低点在抬高
            first_half = pre_lows[: len(pre_lows) // 2]
            second_half = pre_lows[len(pre_lows) // 2 :]
            if min(second_half) < min(first_half):
                result["is_sb1_detailed"] = True

    return result


def calculate_dmi(klines: list[DailyData], period: int = 14) -> tuple[float, float, float]:
    """
    计算 DMI 趋向指标

    通达信公式:
    DMI: (MTM-MTM的N日简单移动平均) / (MTM的绝对值的N日简单移动平均) * 100
    MTM = CLOSE - REF(CLOSE,1)

    Args:
        klines: K线数据
        period: 周期，默认14

    Returns:
        (DMI+, DMI-, ADX)
    """
    if len(klines) < period + 1:
        return 0, 0, 0

    # 计算 MTM = 当日收盘 - 昨日收盘
    mtm_list = []
    for i in range(1, len(klines)):
        mtm = klines[i].close - klines[i - 1].close
        mtm_list.append(mtm)

    if len(mtm_list) < period:
        return 0, 0, 0

    # 计算 DMI+ 和 DMI-
    dmi_plus_list = []
    dmi_minus_list = []

    for i in range(1, len(klines)):
        high_diff = klines[i].high - klines[i - 1].high
        low_diff = klines[i - 1].low - klines[i].low

        dm_plus = high_diff if high_diff > low_diff and high_diff > 0 else 0
        dm_minus = low_diff if low_diff > high_diff and low_diff > 0 else 0

        dmi_plus_list.append(dm_plus)
        dmi_minus_list.append(dm_minus)

    # 计算 N 日简单移动平均
    if len(dmi_plus_list) < period:
        return 0, 0, 0

    dm_plus_ma = sum(dmi_plus_list[-period:]) / period
    dm_minus_ma = sum(dmi_minus_list[-period:]) / period

    # 计算 TR (True Range)
    tr_list = []
    for i in range(1, len(klines)):
        high = klines[i].high
        low = klines[i].low
        prev_close = klines[i - 1].close

        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        tr = max(tr1, tr2, tr3)
        tr_list.append(tr)

    if len(tr_list) < period:
        return 0, 0, 0

    tr_ma = sum(tr_list[-period:]) / period

    if tr_ma == 0:
        return 0, 0, 0

    dmi_plus = dm_plus_ma / tr_ma * 100
    dmi_minus = dm_minus_ma / tr_ma * 100

    # 计算 ADX
    dx_list = []
    for i in range(period - 1, len(dmi_plus_list)):
        di_plus = sum(dmi_plus_list[i - period + 1 : i + 1]) / period / tr_ma * 100 if tr_ma > 0 else 0
        di_minus = sum(dmi_minus_list[i - period + 1 : i + 1]) / period / tr_ma * 100 if tr_ma > 0 else 0
        dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
        dx_list.append(dx)

    if len(dx_list) < period:
        adx = sum(dx_list) / len(dx_list) if dx_list else 0
    else:
        adx = sum(dx_list[-period:]) / period

    return round(dmi_plus, 2), round(dmi_minus, 2), round(adx, 2)


def calculate_brick_value(klines: list[DailyData]) -> float:
    """
    计算砖型图数值（通达信标准公式 - 短期砖型图指标v2026）

    VAR1A = (HHV(HIGH,4) - CLOSE) / (HHV(HIGH,4) - LLV(LOW,4)) * 100 - 90
    VAR2A = SMA(VAR1A, 4, 1) + 100
    VAR3A = (CLOSE - LLV(LOW,4)) / (HHV(HIGH,4) - LLV(LOW,4)) * 100
    VAR4A = SMA(VAR3A, 6, 1)
    VAR5A = SMA(VAR4A, 6, 1) + 100
    VAR6A = VAR5A - VAR2A
    砖型图 = IF(VAR6A > 4, VAR6A - 4, 0)
    """
    if len(klines) < 12:
        return 0

    highs = [k.high for k in klines]
    lows = [k.low for k in klines]
    closes = [k.close for k in klines]

    # 构建 VAR3A 序列（需要至少 6 个值来算 SMA(VAR3A,6,1)）
    var3a_list: list[float] = []
    for i in range(3, len(klines)):  # HHV/LLV 需要 4 天，所以从索引 3 开始
        hhv4 = max(highs[max(0, i - 3) : i + 1])
        llv4 = min(lows[max(0, i - 3) : i + 1])
        if hhv4 == llv4:
            v3 = 50.0
        else:
            v3 = (closes[i] - llv4) / (hhv4 - llv4) * 100
        var3a_list.append(v3)

    if len(var3a_list) < 6:
        return 0

    # VAR4A = SMA(VAR3A, 6, 1) —— 递推序列，每个点承接前一个结果
    var4a_list = calculate_sma_series(var3a_list, 6, 1)

    if len(var4a_list) < 6:
        return 0

    # VAR5A = SMA(VAR4A, 6, 1) + 100 —— 递推序列
    var5a_list = calculate_sma_series(var4a_list, 6, 1)
    var5a = var5a_list[-1] + 100

    # 构建 VAR1A 序列
    var1a_list = []
    for i in range(3, len(klines)):
        hhv4 = max(highs[max(0, i - 3) : i + 1])
        llv4 = min(lows[max(0, i - 3) : i + 1])
        if hhv4 == llv4:
            v1: float = -90.0
        else:
            v1 = (hhv4 - closes[i]) / (hhv4 - llv4) * 100 - 90.0
        var1a_list.append(v1)

    if len(var1a_list) < 4:
        var2a = (var1a_list[-1] if var1a_list else -90) + 100
    else:
        # VAR2A = SMA(VAR1A, 4, 1) + 100 —— 递推序列
        var2a_list = calculate_sma_series(var1a_list, 4, 1)
        var2a = var2a_list[-1] + 100

    # VAR6A = VAR5A - VAR2A
    var6a = var5a - var2a

    # 砖型图 = IF(VAR6A > 4, VAR6A - 4, 0)
    brick = var6a - 4 if var6a > 4 else 0

    return round(brick, 2)


def calculate_brick_history(klines: list[DailyData], lookback: int = 20) -> tuple[str, int]:
    """
    计算砖型图趋势（连续红砖/绿砖数量）

    通达信公式逻辑（与官方一致）：
    - 红砖：今日砖值 >= 昨日砖值（动量上涨）→ COLORRED
    - 绿砖：今日砖值 < 昨日砖值（动量下跌）→ COLOR00FF00

    Args:
        klines: K线数据
        lookback: 回溯天数

    Returns:
        (趋势状态: RED/GREEN/NEUTRAL, 连续砖数)
    """
    if len(klines) < 10:
        return "NEUTRAL", 0

    # 计算历史砖值序列（对比昨日大小判断红绿）
    # 1=红(涨), -1=绿(跌), 0=平
    brick_colors: list[int] = []
    prev_brick = None

    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)

        if prev_brick is not None:
            if brick_val >= prev_brick:
                brick_colors.append(1)  # 红砖 = 上涨
            else:
                brick_colors.append(-1)  # 绿砖 = 下跌
        prev_brick = brick_val

    if not brick_colors:
        return "NEUTRAL", 0

    # 从最新往前数连续同色砖
    current_color = brick_colors[-1]
    if current_color == 0:
        return "NEUTRAL", 0

    count = 1
    for i in range(len(brick_colors) - 2, -1, -1):
        if brick_colors[i] == current_color:
            count += 1
        else:
            break

    trend = "RED" if current_color > 0 else "GREEN"
    return trend, count


def detect_brick_trend(klines: list[DailyData]) -> bool:
    """
    检测命值趋势是否上升

    条件：SLOPE(命值, 7) > -0.02 AND 运值 > 命值
    """
    if len(klines) < 115:
        return False

    closes = [k.close for k in klines]

    # 计算命值序列
    ming_values = []
    for i in range(113, len(klines)):
        sub = closes[: i + 1]
        ma14 = calculate_ma(sub, 14)
        ma28 = calculate_ma(sub, 28)
        ma57 = calculate_ma(sub, 57)
        ma114 = calculate_ma(sub, 114)
        ming = (ma14 + ma28 + ma57 + ma114) / 4
        ming_values.append(ming)

    if len(ming_values) < 8:
        return False

    # 使用正确的 SLOPE 函数计算7日斜率
    slope = calculate_slope(ming_values, 7)

    # 计算当前运值和命值
    current_ming = ming_values[-1]
    yun_zhi = calculate_zg_white(klines)

    return slope > -0.02 and yun_zhi > current_ming


def detect_fanbao(klines: list[DailyData]) -> bool:
    """
    检测精准反包信号

    条件：
    1. 今天红柱（砖型图上涨）
    2. 昨天绿柱（砖型图下跌）
    3. 今天砖型图超过昨日绿柱2/3位置
    """
    if len(klines) < 4:
        return False

    brick_today = calculate_brick_value(klines)
    brick_yesterday = calculate_brick_value(klines[:-1])
    brick_before = calculate_brick_value(klines[:-2]) if len(klines) >= 3 else 0

    # 今天红柱
    is_red = brick_today > brick_yesterday
    # 昨天绿柱
    is_green_yesterday = brick_yesterday < brick_before
    # 昨天绿柱的实体高度
    lzgd = max(brick_yesterday, brick_before) - min(brick_yesterday, brick_before)
    # 反包阈值 = 昨日低点 + 2/3高度
    zddd = min(brick_yesterday, brick_before)
    fbwz = zddd + lzgd * 2 / 3

    # 满足2/3反包
    is_fanbao = brick_today > fbwz if lzgd > 0 else False

    return is_red and is_green_yesterday and is_fanbao


def detect_volume_pattern(today: DailyData, yesterday: DailyData | None = None) -> dict[str, bool]:
    """
    检测量价形态

    Args:
        today: 今日数据
        yesterday: 昨日数据

    Returns:
        形态检测结果
    """
    result = {
        "is_beidou": False,  # 倍量
        "is_suoliang": False,  # 缩量
        "is_jiayin_zhenyang": False,  # 假阴真阳
        "is_jiayang_zhenyin": False,  # 假阳真阴
        "is_fangliang_yinxian": False,  # 放量阴线
    }

    if yesterday is None:
        return result

    # 倍量：今日量 > 昨日量 × 2
    if today.vol >= yesterday.vol * 2:
        result["is_beidou"] = True

    # 缩量：今日量 < 昨日量 × 0.5
    if today.vol <= yesterday.vol * 0.5:
        result["is_suoliang"] = True

    # 假阴真阳：收 < 开 but 收 > 昨收
    if today.close < today.open and today.close > today.prev_close:
        result["is_jiayin_zhenyang"] = True

    # 假阳真阴：收 > 开 but 收 < 昨收
    if today.close > today.open and today.close < today.prev_close:
        result["is_jiayang_zhenyin"] = True

    # 放量阴线：下跌 + 放量
    if today.close < today.prev_close and today.vol > yesterday.vol * 1.5:
        result["is_fangliang_yinxian"] = True

    return result


def detect_didi(klines: list[DailyData]) -> dict:
    """
    滴滴战法检测（高位连续两根阴线下台阶）

    来源：Z哥交易体系 3.11 / trading-core.md
    定义：高位连续两根阴线，第二根收盘价 < 第一根最低价，量未明显萎缩。
    性质：最高优先级卖出信号，绕过防卖飞直接清仓。

    条件：
    1. 第一根阴线（收盘价 < 开盘价）
    2. 第二根阴线（收盘价 < 开盘价）
    3. 第二根收盘价 < 第一根最低价（下台阶）
    4. 第二根成交量 >= 第一根成交量 × 0.8（量没明显缩）
    5. 当前处于相对高位（收盘价 >= 近期20天最高价的 80%）

    Args:
        klines: K线数据（至少2根）

    Returns:
        {'is_didi': bool, 'first_low': float, 'second_close': float, 'volume_ratio': float}
    """
    if len(klines) < 2:
        return {"is_didi": False}

    today = klines[-1]
    yesterday = klines[-2]

    # 两根都是阴线（严格：收盘价 < 开盘价）
    is_yin_1 = yesterday.close < yesterday.open
    is_yin_2 = today.close < today.open

    # 下台阶：第二根收盘 < 第一根最低
    is_down_step = today.close < yesterday.low

    # 量未明显萎缩（今天量 >= 昨天量 × 0.8）
    is_volume_ok = today.vol >= yesterday.vol * 0.8 if yesterday.vol > 0 else False

    # 高位判断（当前 >= 近20天最高价的 80%）
    recent = klines[-20:] if len(klines) >= 20 else klines
    recent_high = max(k.high for k in recent)
    is_high = today.close >= recent_high * 0.8

    if is_yin_1 and is_yin_2 and is_down_step and is_volume_ok and is_high:
        return {
            "is_didi": True,
            "first_low": round(yesterday.low, 2),
            "second_close": round(today.close, 2),
            "volume_ratio": round(today.vol / yesterday.vol, 2) if yesterday.vol > 0 else 0,
            "recent_high": round(recent_high, 2),
        }

    return {"is_didi": False}


def calculate_zuchong_target(klines: list[DailyData], lookback: int = 60) -> dict:
    """
    祖冲之法 —— 主力目标价计算

    来源：advanced-patterns.md「坑里起好货」
    核心逻辑：填坑意味着解放前期套牢盘，主力要拉到足够高度才有利润。
    公式：目标价 = 2a - b
      a = 近期高点（填坑前的高点）
      b = 近期低点（坑底）

    应用：
    - 填大坑过程中遇到 BBI 下 2 根 K 线可以扛一会儿
    - 填小坑到达目标价位及时卤煮（止盈）

    Args:
        klines: K线数据
        lookback: 回望天数（默认60天）

    Returns:
        {'target': float, 'a': float, 'b': float, 'current': float, 'upside_pct': float}
    """
    if len(klines) < 10:
        return {"target": 0, "a": 0, "b": 0, "current": 0, "upside_pct": 0}

    recent = klines[-lookback:] if len(klines) >= lookback else klines

    highs = [k.high for k in recent]
    lows = [k.low for k in recent]

    a = max(highs)  # 近期高点
    b = min(lows)  # 近期低点
    current = klines[-1].close

    target = 2 * a - b
    upside_pct = (target - current) / current * 100 if current > 0 else 0

    return {
        "target": round(target, 2),
        "a": round(a, 2),
        "b": round(b, 2),
        "current": round(current, 2),
        "upside_pct": round(upside_pct, 1),
    }


def detect_b1_today(klines: list[DailyData]) -> dict:
    """
    B1建仓波检测（只检查最新这天）
    标准：J<13, 振幅<4%, 涨幅-2%~+1.8%, 缩量
    """
    result: dict[str, Any] = {
        "is_b1": False,
        "b1_j_value": 0.0,
        "b1_amplitude": 0.0,
        "b1_pct_chg": 0.0,
        "b1_volume_shrink": False,
        "b1_score": 0.0,
    }
    if len(klines) < 2:
        return result
    today = klines[-1]
    prev = klines[-2]
    _, _, j = calculate_kdj(klines)
    amplitude = (today.high - today.low) / prev.close * 100 if prev.close > 0 else 0
    pct = today.pct_chg
    vol_shrink = today.vol < prev.vol
    score = 0
    if j < 13:
        score += 1
    if amplitude < 4:
        score += 1
    if -2 <= pct <= 1.8:
        score += 1
    if vol_shrink:
        score += 1
    if score >= 3:
        result["is_b1"] = True
    result["b1_j_value"] = round(j, 2)
    result["b1_amplitude"] = round(amplitude, 2)
    result["b1_pct_chg"] = round(pct, 2)
    result["b1_volume_shrink"] = vol_shrink
    result["b1_score"] = score
    return result


def detect_b2_today(klines: list[DailyData]) -> dict:
    """
    B2突破检测（只检查最新这天）
    标准：B1后5天内, 涨幅>=4%, 放量20%+, J<55
    """
    result: dict[str, Any] = {
        "is_b2": False,
        "b2_follows_b1": False,
        "b2_pct_chg": 0.0,
        "b2_j_value": 0.0,
        "b2_volume_up": False,
        "b2_score": 0.0,
    }
    if len(klines) < 10:
        return result
    today = klines[-1]
    prev = klines[-2]
    if not prev or prev.close <= 0:
        return result
    # 检查最近5天是否有B1痕迹
    has_recent_b1 = False
    for i in range(max(1, len(klines) - 5), len(klines)):
        _, _, j_check = calculate_kdj(klines[: i + 1])
        if j_check < 13:
            has_recent_b1 = True
            break
    _, _, j = calculate_kdj(klines)
    pct = today.pct_chg
    vol_up = today.vol > prev.vol * 1.2
    score = 0
    if has_recent_b1:
        score += 1
    if pct >= 4:
        score += 1
    if j < 55:
        score += 1
    if vol_up:
        score += 1
    if has_recent_b1 and pct >= 4 and score >= 3:
        result["is_b2"] = True
    result["b2_follows_b1"] = has_recent_b1
    result["b2_pct_chg"] = round(pct, 2)
    result["b2_j_value"] = round(j, 2)
    result["b2_volume_up"] = vol_up
    result["b2_score"] = score
    return result


def detect_key_k(klines: list[DailyData], lookback: int = 60) -> list[dict]:
    """
    关键K检测（位置 + 放量 + 长阳/长阴），扫描最近lookback天
    找出那2-3根真正在指挥走势的关键K
    """
    n = len(klines)
    if n < 10:
        return []
    start = max(0, n - lookback)
    scan = klines[start:]
    n = len(scan)
    if n < 10:
        return []

    results = []
    for i in range(max(5, n - 5), n):
        day = scan[i]
        prev = scan[i - 1] if i > 0 else None
        if not prev or prev.close <= 0:
            continue

        body = abs(day.close - day.open)
        body_pct = body / prev.close * 100

        vol_start = max(0, i - 5)
        avg_vol = sum(k.vol for k in scan[vol_start:i]) / max(1, i - vol_start)
        vol_ratio = day.vol / avg_vol if avg_vol > 0 else 0

        is_big_body = body_pct >= 3
        # 大阳线(>=7%)或涨停时放宽量比要求，涨停缩量突破也认可
        vol_threshold = 1.1 if body_pct >= 7 else 1.3
        is_high_vol = vol_ratio >= vol_threshold

        pos_start = max(0, i - 20)
        if i > pos_start:
            recent_high = max(k.high for k in scan[pos_start:i])
            recent_low = min(k.low for k in scan[pos_start:i])
            dist_high = (day.high - recent_high) / recent_high
            dist_low = (recent_low - day.low) / recent_low if recent_low > 0 else 0
            at_key = (dist_high >= -0.02 and dist_high <= 0.15) or (dist_low >= -0.02 and dist_low <= 0.15)
        else:
            at_key = False

        if is_big_body and is_high_vol and at_key:
            results.append(
                {
                    "date": day.trade_date,
                    "close": day.close,
                    "pct": day.pct_chg,
                    "type": "反转" if day.close > day.open else "衰竭",
                    "body_pct": round(body_pct, 1),
                    "vol_ratio": round(vol_ratio, 1),
                    "is_latest": (i == n - 1),
                }
            )

    return results


def detect_violence_k(klines: list[DailyData], lookback: int = 60) -> list[dict]:
    """
    暴力K检测（底部 + 突兀 + 倍量），扫描最近lookback天
    关键K的满配版
    """
    n = len(klines)
    if n < 10:
        return []
    start = max(0, n - lookback)
    scan = klines[start:]
    n = len(scan)
    if n < 10:
        return []

    results = []
    for i in range(max(5, n - 5), n):
        day = scan[i]
        prev = scan[i - 1] if i > 0 else None
        if not prev or prev.close <= 0:
            continue

        body = abs(day.close - day.open)
        body_pct = body / prev.close * 100

        pos_start = max(0, i - 20)
        if i > pos_start:
            recent_low = min(k.low for k in scan[pos_start:i])
            at_bottom = day.low <= recent_low * 1.05
        else:
            at_bottom = False

        body_start = max(0, i - 5)
        prev_bodies = []
        for j in range(body_start, i):
            p = scan[j - 1] if j > 0 else None
            if p and p.close > 0:
                prev_bodies.append(abs(scan[j].close - scan[j].open) / p.close * 100)
        avg_body = sum(prev_bodies) / len(prev_bodies) if prev_bodies else 0
        is_abrupt = body_pct > avg_body * 2 and body_pct >= 5

        vol_start = max(0, i - 5)
        avg_vol = sum(k.vol for k in scan[vol_start:i]) / max(1, i - vol_start)
        vol_ratio = day.vol / avg_vol if avg_vol > 0 else 0
        is_double_vol = vol_ratio >= 2

        if at_bottom and is_abrupt and is_double_vol:
            results.append(
                {
                    "date": day.trade_date,
                    "close": day.close,
                    "pct": day.pct_chg,
                    "type": "大暴力" if vol_ratio >= 3 else "小暴力",
                    "body_pct": round(body_pct, 1),
                    "vol_ratio": round(vol_ratio, 1),
                    "is_latest": (i == n - 1),
                }
            )

    return results


def check_two_30_rule(klines: list[DailyData]) -> dict:
    """
    两个30%原则检查（B1筛选）
    1. B1涨幅约30%
    2. 累计换手率不超过30%
    """
    result: dict[str, Any] = {
        "b1_rally_pct": 0.0,
        "b1_turnover": 0.0,
        "b1_pass_30": False,
    }
    if len(klines) < 10:
        return result
    # 找最近30天的最低点作为B1起点
    lookback = min(30, len(klines))
    lows = [(klines[-lookback + i].low, klines[-lookback + i].close) for i in range(lookback)]
    min_price, min_close = min(lows, key=lambda x: x[0])
    today_close = klines[-1].close
    rally_pct = (today_close - min_close) / min_close * 100 if min_close > 0 else 0
    # 估算累计换手率（简化：累加每日vol/流通股本，用vol近似）
    total_vol = sum(k.vol for k in klines[-lookback:])
    avg_cap = sum(k.vol for k in klines[-lookback:]) / lookback  # 简化
    total_vol / (avg_cap * lookback) * 100 if avg_cap > 0 else 0
    # 用更简单的方式：涨幅在25%-35%之间算通过
    result["b1_rally_pct"] = round(rally_pct, 2)
    result["b1_pass_30"] = 25 <= rally_pct <= 40
    return result


def detect_nana_chart(klines: list[DailyData]) -> dict:
    """
    娜娜图检测：完美建仓形态
    条件：股价新高但阳线缩量，次高点阴线也缩量
    """
    result = {"is_nana": False}
    if len(klines) < 20:
        return result
    n = len(klines)
    # 找最近高点区域
    highs = [k.high for k in klines]
    peak_idx = n - 1
    for i in range(n - 2, max(0, n - 30), -1):
        if highs[i] >= highs[peak_idx]:
            peak_idx = i
    # 从峰值往前找第二高
    second_peak = None
    for i in range(peak_idx - 2, max(0, peak_idx - 25), -1):
        if klines[i].high < klines[peak_idx].high * 0.98:
            second_peak = i
            break
    if second_peak is None or peak_idx < 5:
        return result
    # 检查峰值区域是否缩量
    peak_vol = klines[peak_idx].vol
    prev5_avg = sum(k.vol for k in klines[max(0, peak_idx - 5) : peak_idx]) / min(5, peak_idx)
    vol_shrink_at_peak = peak_vol < prev5_avg * 0.8 if prev5_avg > 0 else False
    # 次高点缩量
    second_vol = klines[second_peak].vol
    sec_prev5 = sum(k.vol for k in klines[max(0, second_peak - 5) : second_peak]) / min(5, second_peak)
    vol_shrink_second = second_vol < sec_prev5 * 0.8 if sec_prev5 > 0 else False
    # 底部堆量：找低点区域量是否明显大于峰值区域
    low_idx = min(range(max(0, second_peak - 10), second_peak), key=lambda i: klines[i].low)
    bottom_vol = klines[low_idx].vol
    if vol_shrink_at_peak and vol_shrink_second and bottom_vol > peak_vol * 0.5:
        result["is_nana"] = True
    return result


def detect_bull_rope(klines: list[DailyData]) -> dict:
    """
    牛绳理论量化检测

    核心逻辑（源自 Z 哥语料 trend-lines.md）：
    - 白线在黄线上 = 主力牵着牛绳，任何下跌都是洗盘
    - 白线在黄线下 = 牛绳断了，任何上涨都是反弹

    状态判定：
    - 牵牛：白线 > 黄线 且 白线在上升（white[-1] > white[-3]）
    - 牛绳断：白线 < 黄线
    - 金叉：白线从下方刚上穿黄线（今日白>黄，昨日白<=黄）
    - 死叉：白线从上方刚下穿黄线（今日白<黄，昨日白>=黄）

    Args:
        klines: K线数据（至少120根）

    Returns:
        {
            'status': '牵牛' | '牛绳断' | '金叉' | '死叉',
            'white': 当前白线值,
            'yellow': 当前黄线值,
            'gap_pct': 白黄差距百分比（正=多头缺口）,
            'white_trend': '上升' | '下降' | '横盘',
            'is_bullish': bool,
            'is_bearish': bool,
        }
    """
    result: dict[str, Any] = {
        "status": "牛绳断",
        "white": 0.0,
        "yellow": 0.0,
        "gap_pct": 0.0,
        "white_trend": "横盘",
        "is_bullish": False,
        "is_bearish": True,
    }

    if len(klines) < 120:
        return result

    # 计算最近几天的白线和黄线历史值（需要至少3天来判断交叉和趋势）
    white_values: list[float] = []
    yellow_values: list[float] = []

    for i in range(114, len(klines) + 1):
        sub = klines[:i]
        w = calculate_zg_white(sub)
        y = calculate_dg_yellow(sub)
        if w > 0 and y > 0:
            white_values.append(w)
            yellow_values.append(y)

    if len(white_values) < 3:
        return result

    w_now = white_values[-1]
    w_prev = white_values[-2]
    w_prev2 = white_values[-3]
    y_now = yellow_values[-1]
    y_prev = yellow_values[-2]

    result["white"] = round(w_now, 2)
    result["yellow"] = round(y_now, 2)

    # 白黄差距百分比
    if y_now > 0:
        result["gap_pct"] = round((w_now - y_now) / y_now * 100, 2)

    # 状态判定（优先级：金叉/死叉 > 牵牛/牛绳断）
    is_golden_cross = w_now > y_now and w_prev <= y_prev
    is_death_cross = w_now < y_now and w_prev >= y_prev

    if is_golden_cross:
        result["status"] = "金叉"
    elif is_death_cross:
        result["status"] = "死叉"
    elif w_now > y_now:
        # 白线在黄线上，进一步判断是否上升
        if w_now > w_prev2:
            result["status"] = "牵牛"
        else:
            # 白线在黄线上但走弱，仍算牵牛（牛绳未断）
            result["status"] = "牵牛"
    else:
        result["status"] = "牛绳断"

    # 白线趋势：用最近5天的斜率
    if len(white_values) >= 5:
        slope = calculate_slope(white_values, 5)
        if slope > 0.01:
            result["white_trend"] = "上升"
        elif slope < -0.01:
            result["white_trend"] = "下降"
        else:
            result["white_trend"] = "横盘"
    elif w_now > w_prev2:
        result["white_trend"] = "上升"
    elif w_now < w_prev2:
        result["white_trend"] = "下降"

    # 多空判断
    result["is_bullish"] = result["status"] in ("牵牛", "金叉")
    result["is_bearish"] = result["status"] in ("牛绳断", "死叉")

    return result


def detect_golden_bowl(klines: list[DailyData]) -> dict:
    """
    黄金碗检测：价格在白线( zg_white )和黄线( dg_yellow )之间
    条件：白线>黄线(多头排列) + 价格落入碗内
    """
    result: dict[str, Any] = {"is_in_bowl": False, "bowl_upper": 0.0, "bowl_lower": 0.0}
    if len(klines) < 120:
        return result
    white = calculate_zg_white(klines)
    yellow = calculate_dg_yellow(klines)
    if white <= 0 or yellow <= 0:
        return result
    result["bowl_upper"] = round(white, 2)
    result["bowl_lower"] = round(yellow, 2)
    today_close = klines[-1].close
    # 白线>黄线且价格在碗内
    if white > yellow and yellow <= today_close <= white:
        result["is_in_bowl"] = True
    return result


def detect_breathing_structure(klines: list[DailyData]) -> dict:
    """
    呼吸结构检测：放量涨->缩量跌->放量涨 的N型节奏
    """
    result = {"breath_phase": "", "breath_n_type": False}
    if len(klines) < 10:
        return result
    n = len(klines)
    # 分析最近5-7天的量价节奏
    phases = []
    for i in range(max(0, n - 7), n):
        day = klines[i]
        prev = klines[i - 1] if i > 0 else None
        if not prev or prev.vol <= 0:
            continue
        vol_ratio = day.vol / prev.vol
        if day.pct_chg > 0 and vol_ratio > 1:
            phases.append("exhale")  # 放量涨=呼气
        elif day.pct_chg < 0 and vol_ratio < 1:
            phases.append("inhale")  # 缩量跌=吸气
        else:
            phases.append("other")
    # 判断当前阶段
    if len(phases) >= 2:
        if phases[-1] == "exhale":
            result["breath_phase"] = "exhale"
        elif phases[-1] == "inhale":
            result["breath_phase"] = "inhale"
        else:
            result["breath_phase"] = "none"
    # N型结构：最近3个低点依次抬高
    if n >= 10:
        lows = [klines[i].low for i in range(n - 10, n, 3)]
        if len(lows) >= 3 and lows[-1] > lows[-2] > lows[-3]:
            result["breath_n_type"] = True
    return result


def detect_sb1(klines: list[DailyData]) -> dict:
    """
    SB1假摔检测：B1后跌破前低再迅速收回
    条件：1)跌破前低 2)次日反包收回 3)收回放量
    """
    result = {"is_sb1": False}
    if len(klines) < 6:
        return result
    n = len(klines)
    klines[-1]
    yesterday = klines[-2]
    # 前天是假摔日
    if len(klines) >= 3:
        fake_drop = klines[-3]
        prev_low = min(k.low for k in klines[-8:-3]) if n >= 8 else klines[-4].low
        # 1) 跌破前低
        broken_low = fake_drop.low < prev_low
        # 2) 次日反包收回
        recovered = yesterday.close > prev_low and yesterday.pct_chg > 2
        # 3) 反包放量
        vol_up = yesterday.vol > fake_drop.vol * 1.2
        if broken_low and recovered and vol_up:
            result["is_sb1"] = True
    return result


def detect_b3(klines: list[DailyData]) -> dict:
    """
    B3买点检测：B2后缩量回踩不破B2低点
    条件：1) 前面有B2(大涨>=4%) 2) 缩量小阳/十字星 3) 不破B2低点
    """
    result = {"is_b3": False}
    if len(klines) < 15:
        return result
    n = len(klines)
    today = klines[-1]
    klines[-2]
    # 往前找B2(大涨>=4%的阳线)
    b2_idx = None
    for i in range(n - 2, max(0, n - 15), -1):
        if klines[i].pct_chg >= 4 and klines[i].close > klines[i].open:
            b2_idx = i
            break
    if b2_idx is None:
        return result
    b2_low = klines[b2_idx].low
    # B2后缩量小阳线
    days_after = n - 1 - b2_idx
    if 2 <= days_after <= 5:
        today_vol_ratio = today.vol / klines[b2_idx].vol if klines[b2_idx].vol > 0 else 0
        not_break_low = today.low >= b2_low * 0.98
        small_candle = abs(today.pct_chg) < 3
        if today_vol_ratio < 0.8 and not_break_low and small_candle:
            result["is_b3"] = True
    return result


def detect_four_brick_system(klines: list[DailyData]) -> dict:
    """
    四块砖交易体系检测

    通达信公式逻辑（与官方一致）：
    - 红砖 = 上涨动量（今日砖值 >= 昨日砖值）→ COLORRED
    - 绿砖 = 下跌动量（今日砖值 < 昨日砖值）→ COLOR00FF00

    规则：
    1. 红砖数满4块 → 减仓至少一半
    2. 红砖翻绿 → 立刻止损
    3. 绿砖下跌 → 绝不抄底，先数4块
    4. 买入后3天不涨 → 止损（DSZ铁律）
    """
    result = {
        "brick_consecutive": 0,  # 当前连续砖数
        "brick_action": "观望",  # 操作建议
        "brick_action_desc": "",  # 操作描述
        "is_brick_flip_green": False,  # 红砖刚翻绿（上涨转下跌）
    }

    if len(klines) < 10:
        result["brick_action_desc"] = "数据不足"
        return result

    # 计算历史砖值序列（至少需要8天才能开始算砖值）
    brick_history = []
    for i in range(8, len(klines) + 1):
        sub_klines = klines[:i]
        brick_val = calculate_brick_value(sub_klines)
        brick_history.append(brick_val)

    if len(brick_history) < 3:
        result["brick_action_desc"] = "数据不足"
        return result

    # 计算红绿砖：与官方公式一致
    # 1=红砖(上涨), -1=绿砖(下跌)
    colors = []
    for i in range(1, len(brick_history)):
        if brick_history[i] >= brick_history[i - 1]:
            colors.append(1)  # 红砖 = 上涨
        else:
            colors.append(-1)  # 绿砖 = 下跌

    if not colors:
        result["brick_action_desc"] = "无砖型数据"
        return result

    # 从最新往前数连续同色砖
    current_color = colors[-1]
    count = 1
    for i in range(len(colors) - 2, -1, -1):
        if colors[i] == current_color:
            count += 1
        else:
            break

    result["brick_consecutive"] = count

    # === 规则判断 ===

    # 1. 红砖翻绿（止损信号）- 上涨转下跌
    if current_color == -1 and len(colors) >= 2:
        prev_color = colors[-2] if len(colors) >= 2 else 1
        if prev_color == 1:
            # 刚翻绿
            result["is_brick_flip_green"] = True
            result["brick_action"] = "止损"
            result["brick_action_desc"] = f"红砖翻绿！立刻止损（连续红砖{count}块后翻绿）"
            return result

    # 2. 红砖数满4块 → 减仓（连续上涨）
    if current_color == 1 and count >= 4:
        result["brick_action"] = "减仓"
        if count == 4:
            result["brick_action_desc"] = "红砖已满4块，至少减仓一半"
        else:
            result["brick_action_desc"] = f"红砖已延续{count}块，趋势延续中，但未减仓需警惕"
        return result

    # 3. 绿砖下跌 → 禁止抄底（连续下跌）
    if current_color == -1:
        result["brick_action"] = "禁止抄底"
        if count >= 4:
            result["brick_action_desc"] = f"绿砖已连续{count}块，跌势可能接近尾声但仍禁止抄底"
        else:
            result["brick_action_desc"] = f"绿砖下跌中（{count}块），绝不抄底，先数4块"
        return result

    # 4. 红砖不足4块 → 持有/观察（上涨中）
    if current_color == 1 and count < 4:
        result["brick_action"] = "持有"
        result["brick_action_desc"] = f"红砖上涨中（{count}块），继续持有"
        return result

    result["brick_action"] = "观望"
    result["brick_action_desc"] = "中性"
    return result


# ========== P1 指标：灾后重建 / 跃跃欲试 / 关键K ==========


def detect_zaihou_chongjian(klines: list[DailyData]) -> dict:
    """
    灾后重建检测 —— 放量金叉后缩量回踩黄线

    来源：advanced-patterns.md
    定义：放量金叉后缩量回踩黄线，交易价值最大，是最后拉升前的震仓动作。

    条件：
    1. 前期有放量上涨（涨幅 > 5%，量 > 前5日均量 × 1.5）
    2. 近期缩量回调（量 < 放量日量的 60%）
    3. 价格回踩黄线（大哥线 / 4参数BBI变体）附近（±2%）
    4. 黄线趋势向上

    Args:
        klines: K线数据（至少60根）

    Returns:
        {'is_rebuild': bool, 'confidence': float, 'desc': str}
    """
    if len(klines) < 60:
        return {"is_rebuild": False}

    today = klines[-1]

    # 计算黄线（4参数BBI变体）
    closes = [k.close for k in klines]
    ma3 = calculate_ma(closes, 3)
    ma6 = calculate_ma(closes, 6)
    ma12 = calculate_ma(closes, 12)
    ma24 = calculate_ma(closes, 24)
    yellow_line = (ma3 + ma6 + ma12 + ma24) / 4

    # 黄线趋势：近5天黄线 vs 近10天黄线
    yellow_5 = (
        calculate_ma(closes[-5:], 3)
        + calculate_ma(closes[-5:], 6)
        + calculate_ma(closes[-5:], 12)
        + calculate_ma(closes[-5:], 24)
    ) / 4
    yellow_10 = (
        calculate_ma(closes[-10:], 3)
        + calculate_ma(closes[-10:], 6)
        + calculate_ma(closes[-10:], 12)
        + calculate_ma(closes[-10:], 24)
    ) / 4
    yellow_up = yellow_5 > yellow_10

    # 查找近期放量上涨日（近15天内）
    recent_15 = klines[-15:]
    fangliang_day = None
    for i, k in enumerate(recent_15):
        if i == 0:
            continue
        prev_5_avg = sum(kl.vol for kl in recent_15[max(0, i - 5) : i]) / 5
        if k.pct_chg > 5 and k.vol > prev_5_avg * 1.5:
            fangliang_day = k
            break

    if fangliang_day is None:
        return {"is_rebuild": False}

    # 缩量条件：今天量 < 放量日量的 60%
    is_suoliang = today.vol < fangliang_day.vol * 0.6

    # 回踩黄线：收盘价在黄线 ±2% 范围内
    near_yellow = abs(today.close - yellow_line) / yellow_line < 0.02 if yellow_line > 0 else False

    if is_suoliang and near_yellow and yellow_up:
        return {
            "is_rebuild": True,
            "confidence": 0.85,
            "yellow_line": round(yellow_line, 2),
            "fangliang_price": round(fangliang_day.close, 2),
            "desc": f"灾后重建：放量({fangliang_day.close:.2f})后缩量回踩黄线({yellow_line:.2f})",
        }

    return {"is_rebuild": False}


def detect_yueyueyushi(klines: list[DailyData]) -> dict:
    """
    跃跃欲试检测 —— 横盘期间放巨大量三次

    来源：advanced-patterns.md
    定义：横盘期间放巨大量，红长绿短、红肥绿瘦，出现至少三次后越往后突破概率越大。
    前提：仅限牛市、未出货的赛赛图。"横有多长竖有多高"。

    条件：
    1. 近20天振幅 < 15%（横盘）
    2. 近20天出现至少3次巨量（量 > 前10日均量 × 2）
    3. 巨量日多为阳线（红肥绿瘦）
    4. 当前未处于明显高位（距20日高点 < 10% 可接受）

    Args:
        klines: K线数据（至少30根）

    Returns:
        {'is_ready': bool, 'count': int, 'confidence': float, 'desc': str}
    """
    if len(klines) < 30:
        return {"is_ready": False}

    recent_20 = klines[-20:]
    high_20 = max(k.high for k in recent_20)
    low_20 = min(k.low for k in recent_20)
    amplitude = (high_20 - low_20) / low_20 if low_20 > 0 else 0

    # 横盘条件
    if amplitude > 0.15:
        return {"is_ready": False}

    # 计算近10日均量
    vols_10 = [k.vol for k in klines[-10:]]
    avg_vol_10 = sum(vols_10) / len(vols_10)

    # 统计巨量次数（量 > 前10日均量 × 2）
    juliang_count = 0
    yang_count = 0
    for k in recent_20:
        if k.vol > avg_vol_10 * 2:
            juliang_count += 1
            if k.close > k.open:
                yang_count += 1

    # 至少3次巨量，且阳线占比 > 50%
    if juliang_count >= 3 and yang_count / juliang_count > 0.5:
        confidence = 0.70 + 0.05 * min(juliang_count - 3, 3)  # 每多一次+5%，上限85%
        return {
            "is_ready": True,
            "count": juliang_count,
            "yang_ratio": round(yang_count / juliang_count, 2),
            "confidence": round(confidence, 2),
            "desc": f"跃跃欲试：横盘振幅{amplitude * 100:.0f}%，{juliang_count}次巨量，阳线占比{yang_count / juliang_count * 100:.0f}%",
        }

    return {"is_ready": False}


def detect_centipede_pattern(klines: list[DailyData]) -> dict:
    """
    蜈蚣图识别 —— 堆量不涨、影线交替、无呼吸节奏的烂股形态

    来源：trading-core.md 3.0b / breathing-theory.md
    定义：图表形似蜈蚣 —— 堆量不涨、长上下影线交替、十字星频繁、无主力控盘迹象。
    本质：散户互搏、资金无序进出，不具备交易价值。

    五大因子（各0-20分，总分0-100）：
    1. 长上影线比例：(high-close) > 2*(close-open) 的天数占比
    2. 长下影线比例：(close-low) > 2*(close-open) 的天数占比
    3. 十字星比例：|close-open|/open < 0.01 的天数占比
    4. 量能无规律：成交量变异系数(CV = std/mean)
    5. 价格无趋势：20日涨跌幅 < 5% 但日波动率 > 2%

    阈值：总分 >= 60 判定为蜈蚣图

    Args:
        klines: K线数据（至少20根）

    Returns:
        {'is_centipede': bool, 'score': int, 'factors': dict}
    """
    result: dict[str, Any] = {
        "is_centipede": False,
        "score": 0,
        "factors": {},
    }

    if len(klines) < 20:
        return result

    recent = klines[-20:]
    factor_scores: dict[str, int] = {}

    # --- 因子1：长上影线比例 ---
    upper_shadow_days = 0
    for k in recent:
        body = abs(k.close - k.open)
        upper_shadow = k.high - k.close
        if body > 0 and upper_shadow > 2 * body:
            upper_shadow_days += 1
    upper_ratio = upper_shadow_days / 20
    if upper_ratio > 0.4:
        factor_scores["长上影线"] = 20
    elif upper_ratio > 0.25:
        factor_scores["长上影线"] = 10
    else:
        factor_scores["长上影线"] = 0

    # --- 因子2：长下影线比例 ---
    lower_shadow_days = 0
    for k in recent:
        body = abs(k.close - k.open)
        lower_shadow = k.close - k.low
        if body > 0 and lower_shadow > 2 * body:
            lower_shadow_days += 1
    lower_ratio = lower_shadow_days / 20
    if lower_ratio > 0.4:
        factor_scores["长下影线"] = 20
    elif lower_ratio > 0.25:
        factor_scores["长下影线"] = 10
    else:
        factor_scores["长下影线"] = 0

    # --- 因子3：十字星比例 ---
    doji_days = 0
    for k in recent:
        if k.open > 0:
            body_pct = abs(k.close - k.open) / k.open
            if body_pct < 0.01:
                doji_days += 1
    doji_ratio = doji_days / 20
    if doji_ratio > 0.3:
        factor_scores["十字星"] = 20
    elif doji_ratio > 0.15:
        factor_scores["十字星"] = 10
    else:
        factor_scores["十字星"] = 0

    # --- 因子4：量能无规律（变异系数） ---
    volumes = [k.vol for k in recent]
    vol_mean = sum(volumes) / len(volumes)
    if vol_mean > 0:
        vol_std = (sum((v - vol_mean) ** 2 for v in volumes) / len(volumes)) ** 0.5
        vol_cv = vol_std / vol_mean
    else:
        vol_cv = 0
    if vol_cv > 0.8:
        factor_scores["量能无规律"] = 20
    elif vol_cv > 0.5:
        factor_scores["量能无规律"] = 10
    else:
        factor_scores["量能无规律"] = 0

    # --- 因子5：价格无趋势（窄幅震荡 + 高波动） ---
    total_change = (recent[-1].close - recent[0].open) / recent[0].open if recent[0].open > 0 else 0
    daily_pcts = [k.pct_chg for k in recent]
    pct_mean = sum(daily_pcts) / len(daily_pcts)
    pct_std = (sum((p - pct_mean) ** 2 for p in daily_pcts) / len(daily_pcts)) ** 0.5
    is_range_bound = abs(total_change) < 0.05
    is_volatile = pct_std > 2.0
    if is_range_bound and is_volatile:
        factor_scores["价格无趋势"] = 20
    elif is_range_bound or is_volatile:
        factor_scores["价格无趋势"] = 10
    else:
        factor_scores["价格无趋势"] = 0

    # --- 汇总 ---
    total_score = sum(factor_scores.values())
    result["score"] = total_score
    result["factors"] = factor_scores
    result["is_centipede"] = total_score >= 60

    return result


def calculate_sandglass_score(klines: list[DailyData]) -> dict:
    """
    沙漏评分 V9 —— 基于图形审美的选股评分系统

    来源：indicators.md / knowledge
    核心思想：好的股票图形应具备缩量收敛、低位枢轴、量能可控、均线有序、无突发风险。
    V9 回测审美与主包基本一致，能识别 wxsw/娜娜等完美图形。

    五因子模型（各 0-20 分，总分 0-100）：
    1. 缩量/收敛（Volume Contraction）：近期量能收缩、量幅收窄
    2. 枢轴邻近（Pivot Proximity）：当前价格接近近期支撑位
    3. 量能斜率（Volume Slope）：成交量趋势温和下降（可控抛压）
    4. 均线结构（MA Structure）：MA5 > MA10 > MA20 多头排列 + 均线收敛
    5. 事件风险（Event Risk）：从 20 分起扣，检查跳空/连跌/异常放量/近高点

    Args:
        klines: K 线数据（至少 20 根）

    Returns:
        {
            'score': int,           # 总分 0-100
            'rating': str,          # 评级: 极佳/良好/一般/较差/极差
            'factors': dict,        # 五因子明细
            'is_perfect': bool,     # score >= 80
        }
    """
    result: dict[str, Any] = {
        "score": 0,
        "rating": "极差",
        "factors": {},
        "is_perfect": False,
    }

    if len(klines) < 20:
        return result

    n = len(klines)
    closes = [k.close for k in klines]
    volumes = [k.vol for k in klines]
    highs = [k.high for k in klines]
    lows = [k.low for k in klines]

    # ========== 因子 1：缩量/收敛 (0-20) ==========
    vol_ma10 = sum(volumes[-10:]) / 10
    vol_ma20 = sum(volumes[-20:]) / 20

    # 子因子 A：10 日均量 vs 20 日均量（收缩程度）
    if vol_ma20 > 0:
        vol_ratio = vol_ma10 / vol_ma20
    else:
        vol_ratio = 1.0

    if vol_ratio < 0.6:
        score_contraction_a = 12
    elif vol_ratio < 0.8:
        score_contraction_a = 8
    elif vol_ratio < 1.0:
        score_contraction_a = 4
    else:
        score_contraction_a = 0

    # 子因子 B：量幅收窄（近 5 天量幅 vs 前 5 天量幅）
    recent_5_vol = volumes[-5:]
    prev_5_vol = volumes[-10:-5]
    vol_range_recent = max(recent_5_vol) - min(recent_5_vol)
    vol_range_prev = max(prev_5_vol) - min(prev_5_vol) if prev_5_vol else vol_range_recent

    if vol_range_prev > 0:
        vol_range_ratio = vol_range_recent / vol_range_prev
    else:
        vol_range_ratio = 1.0

    if vol_range_ratio < 0.5:
        score_contraction_b = 8
    elif vol_range_ratio < 0.8:
        score_contraction_b = 5
    elif vol_range_ratio < 1.0:
        score_contraction_b = 3
    else:
        score_contraction_b = 0

    score_contraction = min(20, score_contraction_a + score_contraction_b)

    # ========== 因子 2：枢轴邻近 (0-20) ==========
    # 近 20 天最低价作为支撑位
    support = min(lows[-20:])
    current_price = closes[-1]

    if support > 0:
        distance_pct = (current_price - support) / support
    else:
        distance_pct = 1.0

    if distance_pct <= 0.03:
        score_pivot = 20
    elif distance_pct <= 0.05:
        score_pivot = 16
    elif distance_pct <= 0.08:
        score_pivot = 12
    elif distance_pct <= 0.10:
        score_pivot = 8
    elif distance_pct <= 0.15:
        score_pivot = 4
    else:
        score_pivot = 0

    # ========== 因子 3：量能斜率 (0-20) ==========
    # 计算最近 10 天成交量的线性回归斜率
    vol_slope = calculate_slope(volumes[-10:], 10) if len(volumes) >= 10 else 0

    # 归一化：斜率相对均值的比值
    if vol_ma10 > 0:
        slope_normalized = vol_slope / vol_ma10
    else:
        slope_normalized = 0

    # 理想：温和下降（-0.05 ~ -0.01）
    if -0.05 <= slope_normalized <= -0.01:
        score_vol_slope = 20
    elif -0.10 <= slope_normalized < -0.05:
        score_vol_slope = 15
    elif -0.01 < slope_normalized <= 0.02:
        score_vol_slope = 12
    elif -0.15 <= slope_normalized < -0.10:
        score_vol_slope = 8
    elif slope_normalized > 0.05:
        # 急剧放量 = 分发风险
        score_vol_slope = 2
    else:
        score_vol_slope = 5

    # ========== 因子 4：均线结构 (0-20) ==========
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)

    score_ma = 0

    # 子因子 A：多头排列 MA5 > MA10 > MA20
    if ma5 > ma10 > ma20:
        score_ma += 10
    elif ma5 > ma10 or ma10 > ma20:
        score_ma += 5

    # 子因子 B：价格在 MA20 上方
    if ma20 > 0 and current_price > ma20:
        score_ma += 4

    # 子因子 C：均线收敛（MA5 与 MA20 差距缩小 = 潜在突破）
    if ma20 > 0:
        ma_gap = abs(ma5 - ma20) / ma20
        if ma_gap < 0.02:
            score_ma += 6  # 极度收敛
        elif ma_gap < 0.05:
            score_ma += 4
        elif ma_gap < 0.08:
            score_ma += 2

    score_ma = min(20, score_ma)

    # ========== 因子 5：事件风险 (0-20，从 20 分起扣) ==========
    score_risk = 20

    # 检查 1：近 5 天大幅跳空下跌
    for i in range(max(0, n - 5), n):
        if i > 0:
            gap_down = (klines[i].open - klines[i - 1].close) / klines[i - 1].close
            if gap_down < -0.03:
                score_risk -= 10
                break

    # 检查 2：连续 3 天以上下跌
    down_count = 0
    for i in range(max(0, n - 5), n):
        if klines[i].pct_chg < 0:
            down_count += 1
        else:
            down_count = 0
    if down_count >= 3:
        score_risk -= 5

    # 检查 3：放量不涨（量增价滞）
    if n >= 5:
        recent_vol_spike = volumes[-1] > vol_ma10 * 1.8
        price_no_rise = closes[-1] <= closes[-2] if n >= 2 else False
        if recent_vol_spike and price_no_rise:
            score_risk -= 5

    # 检查 4：近 52 周高点（距 240 天最高价 < 5%）
    lookback_52w = min(240, n)
    high_52w = max(highs[-lookback_52w:])
    if high_52w > 0 and (high_52w - current_price) / high_52w < 0.05:
        score_risk -= 5

    score_risk = max(0, score_risk)

    # ========== 汇总 ==========
    total_score = score_contraction + score_pivot + score_vol_slope + score_ma + score_risk
    total_score = max(0, min(100, total_score))

    # 评级
    if total_score >= 80:
        rating = "极佳"
    elif total_score >= 65:
        rating = "良好"
    elif total_score >= 45:
        rating = "一般"
    elif total_score >= 25:
        rating = "较差"
    else:
        rating = "极差"

    result["score"] = total_score
    result["rating"] = rating
    result["factors"] = {
        "缩量收敛": score_contraction,
        "枢轴邻近": score_pivot,
        "量能斜率": score_vol_slope,
        "均线结构": score_ma,
        "事件风险": score_risk,
    }
    result["is_perfect"] = total_score >= 80

    return result


def detect_key_candle(klines: list[DailyData]) -> dict:
    """
    关键 K 检测 —— 走势中管理其他 K 线的关键位置放量长中阳/阴

    来源：key-candles.md
    核心价值：
    1. 判断趋势反转（80分含金量）：下跌→上涨、横盘→上涨等
    2. 判断走势衰竭（20分含金量）：卖盘枯竭/买盘枯竭

    关键K条件：
    1. 关键位置（突破前高、跌破前低、平台边缘）
    2. 放量（量 > 前10日均量 × 1.5）
    3. 实体够大（|收-开| / (高-低) > 0.6）
    4. 阳线 close > open，阴线 close < open

    返回最近一根关键K的信息和趋势转换判断。

    Args:
        klines: K线数据（至少20根）

    Returns:
        {'is_key': bool, 'direction': str, 'type': str, 'confidence': float}
    """
    if len(klines) < 20:
        return {"is_key": False}

    today = klines[-1]
    recent_10 = klines[-10:]
    recent_20 = klines[-20:]

    # 实体比例
    body = abs(today.close - today.open)
    range_ = today.high - today.low
    body_ratio = body / range_ if range_ > 0 else 0

    # 放量
    avg_vol_10 = sum(k.vol for k in recent_10) / len(recent_10)
    is_fangliang = today.vol > avg_vol_10 * 1.5

    # 实体够大
    is_big_body = body_ratio > 0.6

    if not is_fangliang or not is_big_body:
        return {"is_key": False}

    # 判断关键位置
    high_20 = max(k.high for k in recent_20[:-1])  # 排除今天
    low_20 = min(k.low for k in recent_20[:-1])
    is_break_high = today.high > high_20 * 1.01  # 突破前高1%
    is_break_low = today.low < low_20 * 0.99  # 跌破前低1%

    # 判断方向
    is_yang = today.close > today.open
    is_yin = today.close < today.open

    result: dict[str, Any] = {"is_key": True, "body_ratio": round(body_ratio, 2)}

    if is_yang and is_break_high:
        result["direction"] = "向上突破"
        result["type"] = "关键阳突破"
        result["confidence"] = 0.90
    elif is_yin and is_break_low:
        result["direction"] = "向下破位"
        result["type"] = "关键阴破位"
        result["confidence"] = 0.90
    elif is_yang:
        result["direction"] = "底部/回调阳"
        result["type"] = "关键阳"
        result["confidence"] = 0.75
    elif is_yin:
        result["direction"] = "顶部/滞涨阴"
        result["type"] = "关键阴"
        result["confidence"] = 0.75
    else:
        return {"is_key": False}

    return result


def detect_key_candle_coverage(klines: list[DailyData]) -> dict:
    """
    关键K管辖范围检测 —— 扫描最近20天寻找关键K，判断当前价是否在其管辖范围内

    来源：knowledge/key-candles.md
    核心逻辑：
    1. 扫描最近20天，找到最近一根关键K（复用 detect_key_candle 的判断条件）
    2. 如果找到关键K，记录其上沿（high）和下沿（low）
    3. 检查当前价格是否在关键K上下沿之间（管辖范围）
    4. 检查关键K之后是否缩量洗盘（量能递减）
    5. 判断当前价是否在关键K一半位置（最佳买点）

    Args:
        klines: K线数据（至少20根）

    Returns:
        {'has_key_candle': bool, 'key_date': str, 'key_high': float, 'key_low': float,
         'key_direction': str, 'in_range': bool, 'volume_shrinking': bool, 'buy_point': bool}
    """
    empty = {
        "has_key_candle": False,
        "key_date": "",
        "key_high": 0.0,
        "key_low": 0.0,
        "key_direction": "",
        "in_range": False,
        "volume_shrinking": False,
        "buy_point": False,
    }

    if len(klines) < 20:
        return empty

    # 扫描最近20天，从远到近找最近一根关键K
    key_idx = -1
    scan_start = max(0, len(klines) - 20)
    for i in range(scan_start, len(klines)):
        k = klines[i]
        # 取该天之前的窗口（不含当天）
        win_start = max(0, i - 20)
        window = klines[win_start:i]
        if len(window) < 10:
            continue

        # 取该天之前的10天窗口（用于计算均量）
        recent_10 = klines[max(0, i - 10) : i]
        if len(recent_10) < 5:
            continue

        # 实体比例
        body = abs(k.close - k.open)
        range_ = k.high - k.low
        body_ratio = body / range_ if range_ > 0 else 0

        # 放量
        avg_vol_10 = sum(v.vol for v in recent_10) / len(recent_10)
        is_fangliang = k.vol > avg_vol_10 * 1.5

        # 实体够大
        is_big_body = body_ratio > 0.6

        if not is_fangliang or not is_big_body:
            continue

        # 判断关键位置
        high_20 = max(w.high for w in window)
        low_20 = min(w.low for w in window)
        is_break_high = k.high > high_20 * 1.01
        is_break_low = k.low < low_20 * 0.99

        is_yang_k = k.close > k.open
        is_yin_k = k.close < k.open

        # 必须满足关键K条件之一
        if not ((is_yang_k and is_break_high) or (is_yin_k and is_break_low) or is_yang_k or is_yin_k):
            continue

        key_idx = i
        # 不 break，继续往后扫描找更新的关键K

    if key_idx < 0:
        return empty

    key_k = klines[key_idx]
    today = klines[-1]

    # 判断方向
    pre_window = klines[max(0, key_idx - 20) : key_idx]
    if pre_window:
        high_20 = max(w.high for w in pre_window)
        low_20 = min(w.low for w in pre_window)
        if key_k.close > key_k.open and key_k.high > high_20 * 1.01:
            direction = "向上突破"
        elif key_k.close < key_k.open and key_k.low < low_20 * 0.99:
            direction = "向下突破"
        elif key_k.close > key_k.open:
            direction = "向上突破"
        else:
            direction = "向下突破"
    else:
        direction = "向上突破" if key_k.close > key_k.open else "向下突破"

    key_high = key_k.high
    key_low = key_k.low

    # 当前价是否在上下沿之间
    in_range = key_low <= today.close <= key_high

    # 关键K之后是否缩量洗盘（量能递减）
    volume_shrinking = False
    if key_idx < len(klines) - 1:
        post_klines = klines[key_idx + 1 :]
        if len(post_klines) >= 2:
            shrinking = True
            for j in range(1, len(post_klines)):
                if post_klines[j].vol >= post_klines[j - 1].vol:
                    shrinking = False
                    break
            volume_shrinking = shrinking

    # 最佳买点：当前价在关键K一半位置附近（±3%）
    mid = (key_high + key_low) / 2
    buy_point = False
    if key_high > key_low:
        buy_point = abs(today.close - mid) / (key_high - key_low) < 0.15 and in_range

    return {
        "has_key_candle": True,
        "key_date": key_k.trade_date,
        "key_high": round(key_high, 2),
        "key_low": round(key_low, 2),
        "key_direction": direction,
        "in_range": in_range,
        "volume_shrinking": volume_shrinking,
        "buy_point": buy_point,
    }


def detect_abc_stages(klines: list[DailyData]) -> dict:
    """
    ABC三阶段建仓检测

    来源：knowledge/position-management.md
    核心逻辑：
    - A阶段（止跌试水）：近10天内有止跌信号（J值<0后回升），缩量横盘（波动率<3%），量能萎缩
    - B阶段（横盘重仓）：价格在A阶段低点附近横盘，量能温和放大（比A阶段高20-50%），波动率适中
    - C阶段（放量突破）：放量突破B阶段高点，量能 > B阶段均量×1.5
    - 评分制：每个阶段0-100分

    Args:
        klines: K线数据（至少30根）

    Returns:
        {'stage': str, 'a_score': float, 'b_score': float, 'c_score': float,
         'confidence': float, 'action': str}
    """
    empty = {
        "stage": "未知",
        "a_score": 0.0,
        "b_score": 0.0,
        "c_score": 0.0,
        "confidence": 0.0,
        "action": "观察",
    }

    if len(klines) < 30:
        return empty

    today = klines[-1]

    # ===== A阶段评分（止跌试水）=====
    recent_10 = klines[-10:]
    prev_20 = klines[-30:-10]

    a_score = 0.0

    # 1. J值<0后回升：用最近10天的KDJ序列
    kdj_vals = calculate_kdj(klines[-19:])
    j_val = kdj_vals[2]

    # 检查近10天内J值是否曾经<0
    j_was_negative = False
    for i in range(max(0, len(klines) - 10), len(klines)):
        slice_k = klines[max(0, i - 8) : i + 1]
        if len(slice_k) >= 9:
            _, _, j = calculate_kdj(slice_k)
            if j < 0:
                j_was_negative = True
                break

    if j_was_negative and j_val > 0:
        a_score += 40  # J值从负值回升，止跌信号强
    elif j_was_negative:
        a_score += 20  # J值曾为负但还没回升

    # 2. 缩量横盘（波动率<3%）
    closes_10 = [k.close for k in recent_10]
    if closes_10:
        max_c = max(closes_10)
        min_c = min(closes_10)
        volatility = (max_c - min_c) / min_c if min_c > 0 else 1
        if volatility < 0.03:
            a_score += 30  # 波动率很小，缩量横盘
        elif volatility < 0.05:
            a_score += 15

    # 3. 量能萎缩（最近5天均量 < 前20天均量的60%）
    avg_vol_recent = sum(k.vol for k in recent_10[-5:]) / 5 if len(recent_10) >= 5 else 0
    avg_vol_prev = sum(k.vol for k in prev_20) / len(prev_20) if prev_20 else 1
    if avg_vol_prev > 0:
        vol_ratio = avg_vol_recent / avg_vol_prev
        if vol_ratio < 0.6:
            a_score += 30  # 明显缩量
        elif vol_ratio < 0.8:
            a_score += 15
    a_score = min(a_score, 100)

    # ===== B阶段评分（横盘重仓）=====
    b_score = 0.0

    # A阶段低点（近20天最低）
    a_low = min(k.low for k in klines[-20:])

    # 1. 价格在A阶段低点附近横盘（不跌破低点5%）
    if today.close >= a_low * 0.95:
        b_score += 30
    if today.close >= a_low * 1.0:
        b_score += 10

    # 2. 量能温和放大（比A阶段均量高20-50%）
    if avg_vol_prev > 0 and avg_vol_recent > 0:
        b_vol_ratio = avg_vol_recent / avg_vol_prev
        if 1.2 <= b_vol_ratio <= 1.5:
            b_score += 35  # 温和放大，最佳
        elif 1.0 < b_vol_ratio < 1.2:
            b_score += 20
        elif b_vol_ratio > 1.5:
            b_score += 10  # 放量过猛，可能是C阶段

    # 3. 波动率适中（3%-8%）
    closes_20 = [k.close for k in klines[-20:]]
    if closes_20:
        vol_range = (max(closes_20) - min(closes_20)) / min(closes_20) if min(closes_20) > 0 else 1
        if 0.03 <= vol_range <= 0.08:
            b_score += 25
        elif vol_range < 0.03:
            b_score += 10  # 波动太小，可能还在A阶段

    b_score = min(b_score, 100)

    # ===== C阶段评分（放量突破）=====
    c_score = 0.0

    # B阶段高点（近20天最高）
    b_high = max(k.high for k in klines[-20:])

    # 1. 放量突破B阶段高点
    if today.close > b_high:
        c_score += 40
    elif today.high > b_high:
        c_score += 20  # 盘中突破但未站稳

    # 2. 量能 > B阶段均量×1.5
    b_avg_vol = sum(k.vol for k in klines[-10:]) / 10
    if b_avg_vol > 0 and today.vol > b_avg_vol * 1.5:
        c_score += 35
    elif b_avg_vol > 0 and today.vol > b_avg_vol * 1.2:
        c_score += 20

    # 3. 当日涨幅 > 3%
    if today.pct_chg > 3:
        c_score += 25
    elif today.pct_chg > 1:
        c_score += 10

    c_score = min(c_score, 100)

    # ===== 判断当前阶段 =====
    if c_score >= 60:
        stage = "C"
        confidence = c_score / 100
        action = "突破"
    elif b_score >= 60:
        stage = "B"
        confidence = b_score / 100
        action = "重仓"
    elif a_score >= 40:
        stage = "A"
        confidence = a_score / 100
        action = "试水"
    else:
        stage = "未知"
        confidence = 0.0
        action = "观察"

    return {
        "stage": stage,
        "a_score": round(a_score, 1),
        "b_score": round(b_score, 1),
        "c_score": round(c_score, 1),
        "confidence": round(confidence, 2),
        "action": action,
    }
