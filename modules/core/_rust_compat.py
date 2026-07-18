"""Rust / Python 实现切换 compat shim。

业务代码通过此模块判断是否启用 Rust 实现：

    from modules.core._rust_compat import get_compute_module

    compute = get_compute_module()
    if compute is not None:
        return compute.compute_atr(klines, 14)
    else:
        # 走原 Python 实现
        from modules.core.atr import calculate_atr
        return calculate_atr(klines, 14)

环境变量：
    ZETTARANC_BACKTEST_IMPL = "rust"（默认）| "python" | "auto"
        rust   - 强制使用 Rust
        python - 强制使用 Python（跳过 _core_compute 导入）
        auto   - 优先 Rust；导入失败则降级 Python
"""
from __future__ import annotations

import os
from types import ModuleType
from typing import Literal

ImplChoice = Literal["rust", "python", "auto"]

_DEFAULT_IMPL: ImplChoice = "rust"


def get_impl_choice() -> ImplChoice:
    """读取并校验 ZETTARANC_BACKTEST_IMPL 环境变量。"""
    raw = os.getenv("ZETTARANC_BACKTEST_IMPL", _DEFAULT_IMPL).lower()
    if raw not in ("rust", "python", "auto"):
        raise ValueError(
            f"invalid ZETTARANC_BACKTEST_IMPL={raw!r}; expected one of: rust, python, auto"
        )
    return raw  # type: ignore[return-value]


_cached_module: ModuleType | None = None
_cached_resolved: bool = False


def get_compute_module() -> ModuleType | None:
    """返回 _core_compute 模块；若不可用则返回 None。

    "auto" 模式下：成功导入返回模块，失败返回 None。
    "rust" 模式下：导入失败抛 RuntimeError。
    "python" 模式下：永远返回 None。
    """
    global _cached_module, _cached_resolved
    if _cached_resolved:
        return _cached_module

    choice = get_impl_choice()
    if choice == "python":
        _cached_module = None
        _cached_resolved = True
        return None

    try:
        import _core_compute  # type: ignore[import-not-found]

        _cached_module = _core_compute
        _cached_resolved = True
        return _cached_module
    except ImportError as e:
        if choice == "rust":
            raise RuntimeError(
                f"_core_compute import failed (impl=rust): {e}. "
                f"Set ZETTARANC_BACKTEST_IMPL=python to fall back, "
                f"or run `maturin develop --release` to build."
            ) from e
        # auto 模式：降级
        _cached_module = None
        _cached_resolved = True
        return None


def reset_cache() -> None:
    """测试用：清空模块缓存。"""
    global _cached_module, _cached_resolved
    _cached_module = None
    _cached_resolved = False
