from typing import List, Dict, Optional
from .core import StrategyType, StrategySignal, Priority, Action, _calc_kdj, _calc_bbi

def detect_b1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B1 买点

    B1 条件：
    1. J < -10（核心条件）
    2. 缩量回调（最佳）
    3. 价格在 BBI 下方或附近
    4. 非绿砖状态（连续下跌）
    """
    if index < 10:
        return None

    today = klines[index]
    k, d, j = _calc_kdj(klines[:index+1])

    # 核心条件：J < -10
    if j >= -10:
        return None

    # 最佳条件：缩量回调
    is_suoliang = today['is_suoliang']

    # 检查是否在连续下跌中（绿砖状态）
    # 绿砖：连续4根阴线
    recent_4 = klines[index-3:index+1]
    yin_count = sum(1 for k in recent_4 if k['is_yinxian'])

    # B1 买点
    bbi = _calc_bbi(klines[:index+1])
    price = today['close']

    # 计算止损位
    stop_loss = today['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B1,
        confidence=0.8 if is_suoliang else 0.6,
        description=f"B1买点 J={j:.2f}" + (" 缩量回调" if is_suoliang else ""),
        details={
            'j': j,
            'k': k,
            'd': d,
            'is_suoliang': is_suoliang,
            'yin_count_4': yin_count,
            'bbi': bbi,
            'price': price,
        },
        action=Action.BUY.value,
        stop_loss=stop_loss,
        priority=Priority.OPPORTUNITY)


def detect_b2(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B2 买点

    B2 条件（B1后的确认信号）：
    1. 前几日有B1（J<-10）
    2. 放量长阳（涨幅>=4%）
    3. J值拐头（>-10）
    4. 无上影线最好
    """
    if index < 15:
        return None

    today = klines[index]

    # 检查是否有B1在前几日
    has_b1 = False
    prev_j_list = []
    for i in range(5, min(15, index)):
        pk, pd, pj = _calc_kdj(klines[:index-i+1])
        prev_j_list.append(pj)
        if pj < -10:
            has_b1 = True
            break

    if not has_b1:
        return None

    # 放量长阳
    is_beidou = today['is_beidou']
    pct_chg = today['pct_chg']
    is_long_yang = pct_chg >= 4

    # 无上影线
    has_upper_shadow = today['high'] > today['close'] * 1.01

    if not (is_long_yang and is_beidou):
        return None

    # 计算J值
    k, d, j = _calc_kdj(klines[:index+1])

    # B2 确认
    stop_loss = today['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B2,
        confidence=0.85 if not has_upper_shadow else 0.75,
        description=f"B2确认 涨{pct_chg:.2f}% J={j:.2f}",
        details={
            'j': j,
            'pct_chg': pct_chg,
            'is_beidou': is_beidou,
            'has_upper_shadow': has_upper_shadow,
            'price': today['close'],
        },
        action=Action.BUY.value,
        stop_loss=stop_loss,
        priority=Priority.OPPORTUNITY)


def detect_b3(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B3 中继买点

    B3 条件：
    1. B2后出现
    2. 分歧转一致（小阳线）
    3. 涨幅<2%
    4. 振幅<7%
    """
    if index < 20:
        return None

    today = klines[index]

    # 检查前几日是否有B2
    has_b2 = False
    for i in range(3, min(10, index)):
        if klines[index-i]['pct_chg'] >= 4 and klines[index-i]['is_beidou']:
            has_b2 = True
            break

    if not has_b2:
        return None

    # B3：小阳线，分歧转一致
    pct_chg = today['pct_chg']
    amplitude = (today['high'] - today['low']) / today['prev_close'] * 100

    if not (0 < pct_chg < 2 and amplitude < 7):
        return None

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B3,
        confidence=0.7,
        description=f"B3中继 涨{pct_chg:.2f}% 振幅{amplitude:.2f}%",
        details={
            'pct_chg': pct_chg,
            'amplitude': amplitude,
            'price': today['close'],
        },
        action=Action.BUY.value,
        stop_loss=today['low'],
        priority=Priority.OPPORTUNITY)


def detect_sb1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测超级B1

    超级B1条件：
    1. 缩量回调到极致
    2. 突然放量下跌（震仓）
    3. 继续缩量企稳
    4. J出现负值
    """
    if index < 10:
        return None

    today = klines[index]
    prev_1 = klines[index-1] if index >= 1 else None
    prev_2 = klines[index-2] if index >= 2 else None

    if not (prev_1 and prev_2):
        return None

    # 检查前2天是否有放量下跌
    is_drop_vol = prev_2['close'] < prev_2['open'] and prev_2['vol'] > klines[index-3]['vol'] * 1.5

    if not is_drop_vol:
        return None

    # 今日缩量企稳
    is_suoliang = today['is_suoliang']

    # J值
    k, d, j = _calc_kdj(klines[:index+1])

    if j >= -5:
        return None

    # 超级B1确认
    stop_loss = prev_2['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.SB1,
        confidence=0.9,
        description=f"超级B1 J={j:.2f} 放量跌后缩量企稳",
        details={
            'j': j,
            'drop_vol': prev_2['vol'],
            'is_suoliang': is_suoliang,
            'price': today['close'],
        },
        action=Action.BUY.value,
        stop_loss=stop_loss,
        priority=Priority.OPPORTUNITY)
