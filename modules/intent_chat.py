#!/usr/bin/env python3
"""
意图识别 + RAG 聊天界面

用法：
    python -m modules.intent_chat          # 交互模式
    python -m modules.intent_chat "B1 买点怎么判断"   # 单次查询
"""
import os
import sys
from pathlib import Path

# 清除代理
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY']:
    os.environ.pop(k, None)
os.environ['no_proxy'] = 'localhost,127.0.0.1'

from .intent_router import IntentRouter

# 意图显示名称
INTENT_LABELS = {
    "stock": "📈 投资模式",
    "career": "💼 职业模式",
    "life": "🌊 人生模式",
    "chat": "💬 闲聊模式",
    "fallback": "🤔 默认模式",
}


def chat_once(router: IntentRouter, message: str):
    """单次意图识别 + RAG 查询"""
    result = router.process(message)
    
    # 显示识别结果
    label = INTENT_LABELS.get(result.intent, result.intent)
    print(f"\n{'='*60}")
    print(f"🎯 意图: {label}")
    print(f"📊 置信度: {result.confidence:.0%}")
    if result.rule_matched:
        print(f"📏 匹配规则: {result.rule_matched}")
    if result.matched_keywords:
        print(f"🔑 命中词: {', '.join(result.matched_keywords[:5])}")
    
    # 显示知识库检索结果
    if result.knowledge_context:
        card_count = result.knowledge_context.count("---") // 2 + 1
        print(f"📚 知识卡片: {card_count} 条")
        # 显示卡片来源
        for line in result.knowledge_context.split("\n"):
            if line.startswith("[") and "] " in line:
                print(f"   {line}")
    
    # 显示系统提示长度
    print(f"📝 系统提示: {len(result.system_prompt)} 字符")
    print(f"{'='*60}\n")
    
    # 如果有股票数据，显示（后续 Phase 4 集成）
    if hasattr(result, 'stock_data') and result.stock_data:
        sd = result.stock_data
        print(f"📊 实时数据: {sd.ts_code}")
        print(f"   J={sd.j:.1f} DIF={sd.dif:.2f} 信号={sd.signal}")
        print()
    
    # 输出完整的系统提示（用于 LLM 调用）
    # 实际使用时，这里会调 LLM 生成回答
    print("系统提示词（前 500 字符）:")
    print(result.system_prompt[:500])
    print("...")


def chat_interactive(router: IntentRouter):
    """交互模式"""
    print("\n" + "=" * 60)
    print("Z哥意图识别聊天")
    print("输入消息自动识别意图并检索知识库")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 60 + "\n")
    
    while True:
        try:
            message = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        
        if not message:
            continue
        if message.lower() in ('quit', 'exit', 'q'):
            print("再见！")
            break
        
        chat_once(router, message)


def main():
    router = IntentRouter()
    
    if len(sys.argv) > 1:
        # 单次查询
        message = " ".join(sys.argv[1:])
        chat_once(router, message)
    else:
        # 交互模式
        chat_interactive(router)


if __name__ == "__main__":
    main()
