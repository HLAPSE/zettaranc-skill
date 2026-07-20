"""
启动向导模块
用户首次使用时引导配置数据源：JNB 模式（走 BaoStock + AkShare）或 普通小万模式（走网络搜索）
"""

from typing import Optional
import os
import logging
from pathlib import Path

from .core.errors import ErrorCode, ZettarancError

# dotenv 加载已移至 modules/__init__.py（包级别一次性加载）

logger = logging.getLogger(__name__)

# 数据模式别名
MODE_JNB = "jnb"  # JNB 模式：走 BaoStock + AkShare
MODE_NORMAL = "websearch"  # 普通小万模式：走网络搜索
MODE_NAMES = {
    MODE_JNB: "JNB",
    MODE_NORMAL: "普通小万",
}


def check_env_exists() -> bool:
    """检查 .env 文件是否存在且包含有效配置"""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return False

    data_mode = os.environ.get("DATA_MODE", "")
    return data_mode != ""


def check_data_mode() -> str | None:
    """返回当前数据模式：jnb / websearch / None（未配置）"""
    return os.environ.get("DATA_MODE", None)


def get_mode_display_name(mode: str) -> str:
    """获取模式显示名称"""
    return MODE_NAMES.get(mode, mode)


def write_env_file(mode: str = MODE_NORMAL, env_path: Path | None = None) -> str:
    """
    写入 .env 文件

    Args:
        mode: 数据模式，"jnb" 或 "websearch"
        env_path: 目标 .env 写入路径（可选，若未指定则写入默认位置）

    Returns:
        .env 文件的绝对路径
    """
    if env_path is None:
        env_path = Path(__file__).parent.parent / ".env"

    lines = [
        "# 数据模式: jnb(JNB模式/走 BaoStock + AkShare) 或 websearch(普通小万模式/走网络搜索)",
        f"DATA_MODE={mode}",
        "",
        "# 数据库路径（相对于项目根目录）",
        "DATA_DIR=data",
        "DB_PATH=data/stock_data.db",
        "",
    ]

    env_path.write_text("\n".join(lines), encoding="utf-8")

    # 同时设置环境变量，使当前会话立即生效
    os.environ["DATA_MODE"] = mode

    return str(env_path)


def test_baostock_connection() -> bool:
    """
    测试 BaoStock 连通性

    Returns:
        True 表示连接成功
    """
    try:
        from .baostock_client import get_client
        client = get_client()
        return client.check_connection()
    except (OSError, ConnectionError, TimeoutError, ValueError) as e:
        logger.warning("[启动向导] BaoStock 连通性测试失败: %s", e)
        print(f"  连接测试失败: {e}")
        return False


def run_wizard() -> str | None:
    """
    运行启动向导（命令行模式，agent 对话中不直接使用）

    流程：
    1. 检查是否已配置
    2. 询问用户选择数据模式
    3. 如选 JNB，测试 BaoStock 连通性
    4. 写入 .env 并确认
    """
    print("=" * 50)
    print("  Zettaranc 启动向导")
    print("=" * 50)
    print()

    # 检查是否已配置
    if check_env_exists():
        mode = check_data_mode()
        if mode is None:
            print("[未配置] 环境变量缺失 DATA_MODE，请重新配置")
            return None
        display = get_mode_display_name(mode)
        print(f"[已配置] 当前模式: {display}")
        print()
        print("如需重新配置，请删除 .env 文件后重新运行")
        return mode

    print("欢迎使用 Zettaranc！请选择模式：")
    print()
    print("  [1] JNB — 走 BaoStock + AkShare（免费数据源，指标全开）")
    print("  [2] 普通小万 — 走网络搜索（不用配，开箱即用）")
    print()

    while True:
        choice = input("请选择 [1/2]: ").strip()
        if choice in ("1", "2"):
            break
        print("  请输入 1 或 2")

    if choice == "1":
        # ====== JNB 模式 ======
        print()
        print("正在测试 BaoStock 连通性...")
        if test_baostock_connection():
            print("  连接测试通过！")
            env_path = write_env_file(mode=MODE_JNB)
            print(f"  配置已写入: {env_path}")
            print()
            print("JNB 模式已启用（BaoStock + AkShare）")
            return MODE_JNB
        else:
            print("  连接测试失败")
            print()
            retry = input("是否重试？[y/n]: ").strip().lower()
            if retry == "y":
                return run_wizard()
            else:
                print("已切换至普通小万模式")
                env_path = write_env_file(mode=MODE_NORMAL)
                print(f"配置已写入: {env_path}")
                return MODE_NORMAL

    else:
        # ====== 普通小万 模式 ======
        print()
        env_path = write_env_file(mode=MODE_NORMAL)
        print(f"配置已写入: {env_path}")
        print("普通小万模式已启用")
        return MODE_NORMAL


if __name__ == "__main__":
    mode = run_wizard()
    if mode is not None:
        print(f"\n最终模式: {get_mode_display_name(mode)}")
