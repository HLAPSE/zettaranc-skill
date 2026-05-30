from typing import List, Dict, Optional
from .core import StrategyType, StrategySignal, Priority, Action, _klines_dict_to_daily
from ..indicators import detect_four_brick_system

def detect_s1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 S1 初级逃顶信号

    触发条件：
    1. 近期流畅上涨（20日内涨幅 > 15%，位于高位）
    2. 丑陋大绿帽：放量阴线或假阴真阳，收盘价接近当日低点
    3. 量能异常（放量 > 前日 1.5 倍）
    """
    if index < 20:
        return None

    today = klines[index]

    # 近期高点
    recent_high = max(k['high'] for k in klines[index - 19:index + 1])
    recent_low_20 = min(k['low'] for k in klines[index - 19:index])

    # 流畅上涨条件：20日内涨幅 > 15%
    up_pct = (recent_high - recent_low_20) / recent_low_20
    if up_pct < 0.15:
        return None

    # 当前位于高位（距20日高点 < 10%）
    if today['close'] < recent_high * 0.90:
        return None

    # 丑陋大绿帽：放量阴线 或 假阴真阳
    is_ugly = (
        today['is_fangliang_yinxian'] or
        (today['is_jiayin'] and today['vol'] > klines[index - 1]['vol'] * 1.5)
    )
    if not is_ugly:
        return None

    # 收盘价接近当日低点（绿帽实体大）
    day_range = today['high'] - today['low']
    if day_range > 0:
        close_position = (today['close'] - today['low']) / day_range
    else:
        close_position = 0.5

    if close_position > 0.3:
        return None

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.S1,
        confidence=0.85,
        description=f"S1逃顶 20日涨{up_pct*100:.0f}% 放量阴线 收盘距低点{close_position*100:.0f}%",
        details={
            'up_pct': round(up_pct * 100, 2),
            'close_position': round(close_position, 2),
            'vol_ratio': round(today['vol'] / klines[index - 1]['vol'], 2) if klines[index - 1]['vol'] > 0 else 0,
        },
        action="SELL",
        stop_loss=today['low'],
        priority=Priority.CRITICAL)


def _calc_dif(klines: List[Dict]) -> List[float]:
    """
    简化版 MACD DIF 计算（用于 S2 顶背离检测）
    EMA12 - EMA26
    """
    if len(klines) < 26:
        return []

    closes = [k['close'] for k in klines]

    def ema(data: List[float], period: int) -> List[float]:
        multiplier = 2 / (period + 1)
        result = [data[0]]
        for price in data[1:]:
            result.append(price * multiplier + result[-1] * (1 - multiplier))
        return result

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    dif = [ema12[i] - ema26[i] for i in range(len(closes))]
    return dif


def detect_s2(klines: List[Dict], index: int,
              dif_list: Optional[List[float]] = None) -> Optional[StrategySignal]:
    """
    检测 S2 确认逃顶信号（MACD顶背离）

    触发条件：
    1. 股价挑战前高（close >= 近期高点 * 0.97）
    2. MACD 顶背离（价格创新高，DIF未创新高）

    dif_list: 可选的外部 MACD DIF 序列，避免重复计算
    """
    if index < 30:
        return None

    today = klines[index]

    # 找前高（过去30天内的最高点，排除最近5天）
    prev_high = max(k['high'] for k in klines[index - 29:index - 4])
    prev_high_idx = next(
        i for i in range(index - 29, index - 4)
        if klines[i]['high'] == prev_high
    )

    # 当前价格接近或超过前高
    if today['close'] < prev_high * 0.97:
        return None

    # 计算 DIF（如果没有外部传入）
    if dif_list is None or len(dif_list) < index + 1:
        dif_list = _calc_dif(klines)

    if not dif_list or len(dif_list) < index + 1:
        return None

    # 顶背离：价格创新高，DIF 未创新高
    current_dif = dif_list[index]
    prev_dif = dif_list[prev_high_idx]

    if today['close'] > klines[prev_high_idx]['close'] and current_dif < prev_dif * 0.98:
        return StrategySignal(
            ts_code=today['ts_code'],
            trade_date=today['trade_date'],
            strategy=StrategyType.S2,
            confidence=0.8,
            description="S2顶背离 价新高DIF未新高",
            details={
                'prev_high': prev_high,
                'prev_high_date': klines[prev_high_idx]['trade_date'],
                'current_dif': round(current_dif, 4),
                'prev_dif': round(prev_dif, 4),
            },
            action="SELL",
            stop_loss=klines[prev_high_idx]['low'],
        priority=Priority.CRITICAL)

    return None


def detect_s3(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 S3 最后逃生信号（简化版）

    触发条件：
    1. 之前有 S1 或高位放量阴线
    2. 近期反弹到 S1 高点下沿但量能不足
    3. 无法突破，出现滞涨
    """
    if index < 15:
        return None

    today = klines[index]

    # 找近期 S1 或放量阴线的位置（过去15天内）
    s1_index = None
    for i in range(index - 14, index):
        if klines[i].get('is_fangliang_yinxian', False) and klines[i]['close'] < klines[i]['open']:
            s1_index = i
            break

    if s1_index is None:
        return None

    s1_high = klines[s1_index]['high']
    s1_open = klines[s1_index]['open']

    # 当前价格反弹到 S1 开盘价附近但未能突破 S1 高点
    if not (s1_open * 0.95 <= today['close'] <= s1_high * 1.02):
        return None

    # 反弹量能不足（小于 S1 当天量能的 70%）
    if today['vol'] > klines[s1_index]['vol'] * 0.7:
        return None

    # 当日涨幅受限（< 2%）
    if today['pct_chg'] > 2:
        return None

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.S3,
        confidence=0.7,
        description=f"S3最后逃生 反弹至S1下沿 量能不足",
        details={
            's1_date': klines[s1_index]['trade_date'],
            's1_high': s1_high,
            'rebound_pct': round((today['close'] - klines[s1_index]['close']) / klines[s1_index]['close'] * 100, 2),
            'vol_ratio': round(today['vol'] / klines[s1_index]['vol'], 2),
        },
        action="SELL",
        stop_loss=klines[s1_index]['low'],
        priority=Priority.CRITICAL)


def detect_brick_signals(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测砖形图信号

    基于四块砖交易体系，检测状态变化点：
    - 红砖翻绿 → 止损 (BRICK_EXIT)
    - 红砖满4块 → 减仓 (BRICK_REDUCE)
    - 绿砖满4块 → 可能止跌观察 (BRICK_BOUNCE)

    只在状态变化当天触发，避免连续多天重复信号。
    """
    if index < 11:
        return None

    today = klines[index]

    # 转换为 DailyData 并检测今天状态
    daily_list = _klines_dict_to_daily(klines[:index + 1])
    brick_today = detect_four_brick_system(daily_list)

    # 只关注重要操作状态
    action_today = brick_today.get('brick_action', '观望')
    if action_today in ('观望', '持有'):
        return None

    # 检测昨天状态（用于判断是否为状态变化首日）
    daily_yesterday = _klines_dict_to_daily(klines[:index])
    brick_yesterday = detect_four_brick_system(daily_yesterday)
    action_yesterday = brick_yesterday.get('brick_action', '观望')

    # 如果昨天已经是同样的重要状态，说明不是首日，不重复触发
    if action_yesterday == action_today:
        return None

    # 映射到 StrategyType
    strategy_map = {
        '止损': (StrategyType.BRICK_EXIT, 'SELL', 0.85, Priority.CRITICAL),
        '减仓': (StrategyType.BRICK_REDUCE, 'SELL', 0.75, Priority.OBSERVE),
        '禁止抄底': (StrategyType.BRICK_BOUNCE, 'WATCH', 0.7, Priority.OBSERVE),
    }

    if action_today not in strategy_map:
        return None

    strategy_type, action, confidence, priority = strategy_map[action_today]

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=strategy_type,
        confidence=confidence,
        description=brick_today.get('brick_action_desc', action_today),
        details={
            'brick_consecutive': brick_today.get('brick_consecutive', 0),
            'is_brick_flip_green': brick_today.get('is_brick_flip_green', False),
            'prev_action': action_yesterday,
            'current_action': action_today,
        },
        action=action,
        stop_loss=today['low'],
        priority=priority,
    )
