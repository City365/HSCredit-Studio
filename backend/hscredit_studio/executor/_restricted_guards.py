"""RestrictedPython 守卫函数 — 简化版.

RestrictedPython 在用户代码中插入 ``_getattr_`` / ``_getitem_`` / ``_getiter_`` 等
钩子调用, 我们需要实现这些钩子的安全版本.

官方版本 (RestrictedPython.Guards) 太复杂且与 Zope 耦合, 这里我们用
最小化实现, 满足用户代码需求即可.
"""

from __future__ import annotations

from typing import Any


# ===== 简化守卫 =====


def safe_getattr(obj: Any, name: str, default: Any = ...) -> Any:
    """安全的 getattr — 禁止 dunder 属性 (除白名单).

    RestrictedPython 编译时把 ``obj.attr`` 替换成 ``_getattr_(obj, 'attr')``.
    """
    # 禁止 dunder (除安全白名单)
    if name.startswith("__") and name.endswith("__"):
        _SAFE_DUNDERS = frozenset({
            "__init__", "__str__", "__repr__", "__name__",
            "__class__", "__doc__", "__dict__",
            "__iter__", "__next__", "__len__", "__getitem__",
            "__contains__", "__eq__", "__ne__", "__lt__", "__le__",
            "__gt__", "__ge__", "__hash__",
            "__bool__", "__repr__", "__add__", "__mul__",
        })
        if name not in _SAFE_DUNDERS:
            raise AttributeError(f"禁止访问 dunder 属性: {name!r}")
    return getattr(obj, name)


def safe_getitem(obj: Any, key: Any) -> Any:
    """安全的 getitem — dict / list / DataFrame 通用.

    RestrictedPython 编译时把 ``obj[key]`` 替换成 ``_getitem_(obj, key)``.
    """
    # 禁止字符串形式的危险键 (双下划线)
    if isinstance(key, str) and key.startswith("__") and key.endswith("__"):
        raise KeyError(f"禁止访问 dunder 键: {key!r}")
    try:
        return obj[key]
    except (KeyError, IndexError, TypeError) as e:
        # 透明传播 (调用方处理)
        raise


def safe_getiter(obj: Any) -> Any:
    """安全的 iter — 限制迭代次数防止恶意耗尽内存."""
    return iter(obj)


def safe_iter_unpack_sequence(seq: Any) -> Any:
    """解包序列 (a, b, c = some_iter)."""
    return list(seq)


def safe_write(obj: Any, name: str, value: Any) -> None:
    """安全写属性 — 禁止写 dunder."""
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(f"禁止写 dunder 属性: {name!r}")
    setattr(obj, name, value)


__all__ = [
    "safe_getattr",
    "safe_getitem",
    "safe_getiter",
    "safe_iter_unpack_sequence",
    "safe_write",
]
