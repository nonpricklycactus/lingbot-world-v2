"""ASCII -> USB HID Usage ID 的唯一权威表 (上位机用).

固件端 (firmware/pico/code.py) 有一份等价的字面表, 两者必须逐字符一致;
``tools/check_keymap.py`` 会直接解析固件源码做交叉校验, 不需要硬件。
"""

from __future__ import annotations

from typing import Dict, Sequence, Tuple

# HID 修饰键位 (与 USB HID 报告的第 0 字节一致)
MOD_NONE, MOD_LCTRL, MOD_LSHIFT, MOD_LALT, MOD_LGUI = 0x00, 0x01, 0x02, 0x04, 0x08

SHIFT = MOD_LSHIFT

_LOWER = "abcdefghijklmnopqrstuvwxyz"
_DIGITS = "1234567890"

# (字符, HID keycode, 是否需要 Shift)
_PUNCT: Sequence[Tuple[str, int, int]] = (
    (" ", 0x2C, 0), ("\n", 0x28, 0), ("\t", 0x2B, 0),
    ("-", 0x2D, 0), ("=", 0x2E, 0), ("[", 0x2F, 0), ("]", 0x30, 0),
    ("\\", 0x31, 0), (";", 0x33, 0), ("'", 0x34, 0), ("`", 0x35, 0),
    (",", 0x36, 0), (".", 0x37, 0), ("/", 0x38, 0),
    ("_", 0x2D, 1), ("+", 0x2E, 1), ("{", 0x2F, 1), ("}", 0x30, 1),
    ("|", 0x31, 1), (":", 0x33, 1), ('"', 0x34, 1), ("~", 0x35, 1),
    ("<", 0x36, 1), (">", 0x37, 1), ("?", 0x38, 1),
    ("!", 0x1E, 1), ("@", 0x1F, 1), ("#", 0x20, 1), ("$", 0x21, 1),
    ("%", 0x22, 1), ("^", 0x23, 1), ("&", 0x24, 1), ("*", 0x25, 1),
    ("(", 0x26, 1), (")", 0x27, 1),
)

HID_KEYCODES: Dict[str, int] = {}
NEEDS_SHIFT: Dict[str, bool] = {}

for _i, _ch in enumerate(_LOWER):
    HID_KEYCODES[_ch] = 0x04 + _i
    HID_KEYCODES[_ch.upper()] = 0x04 + _i
    NEEDS_SHIFT[_ch] = False
    NEEDS_SHIFT[_ch.upper()] = True

for _i, _ch in enumerate(_DIGITS):
    HID_KEYCODES[_ch] = 0x1E + _i
    NEEDS_SHIFT[_ch] = False

for _ch, _code, _shift in _PUNCT:
    HID_KEYCODES[_ch] = _code
    NEEDS_SHIFT[_ch] = bool(_shift)

SHIFTED = {ch for ch, needs in NEEDS_SHIFT.items() if needs}


def char_to_hid(ch: str) -> Tuple[int, int]:
    """单字符 -> (modifier, keycode); 不可打字符抛 ProtocolError."""
    from .protocol import ProtocolError      # 延迟导入, 避免循环依赖
    if ch not in HID_KEYCODES:
        raise ProtocolError(f"字符无法用 HID 键盘打出: {ch!r} (仅支持 ASCII 可见字符 + 换行/制表)")
    return (SHIFT if NEEDS_SHIFT[ch] else MOD_NONE), HID_KEYCODES[ch]


def precheck_text(text: str) -> Sequence[str]:
    """返回文本里无法键入的字符列表 (空表示全部可打)."""
    return [ch for ch in text if ch not in HID_KEYCODES]
