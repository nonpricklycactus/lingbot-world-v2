"""上位机 <-> 硬件 HID 桥的串口帧协议.

线上格式 (变长, 最小 5 字节)::

    offset   0    1     2     3         4 .. 4+LEN     5+LEN
          +----+----+-----+-----+-------------------+-------+
          | AA | 55 | CMD | LEN |      PAYLOAD      | CRC8  |
          +----+----+-----+-----+-------------------+-------+

约定
----
* 魔数 ``AA 55``;  ``LEN`` 为 1 字节, 即 PAYLOAD 长度 (0..255)
* ``CRC8`` 覆盖 ``CMD | LEN | PAYLOAD`` 三个部分, 多项式 0x07, 初值 0x00
* 多字节整数一律 little-endian 有符号; 鼠标坐标为相对位移或绝对坐标(见 Cmd)
* 解码器必须能吞下"半帧": 串口一次 read() 可能只返回半个帧, 也可能一次返回
  好几帧。把未收全的尾巴丢掉 = 鼠标瞬移 + 事件丢失, 这是最经典的事故。

本文件是事务化的 MODIFIED_FILE: 基线版本见 ``_transaction/baseline/protocol.py``,
基线假设"每次 read() 恰好返回完整帧"且 CRC 覆盖范围与固件不一致, 会被
``tests/test_protocol.py`` 的 golden-vector 与分片用例判负。
"""

from __future__ import annotations

import struct
from enum import IntEnum
from typing import Iterable, List, Sequence, Tuple

MAGIC = b"\xAA\x55"
MAX_PAYLOAD = 255
CRC8_POLY = 0x07

_HDR = 4          # MAGIC(2) + CMD(1) + LEN(1)
_CRC = 1
_MIN_FRAME = _HDR + _CRC


class ProtocolError(ValueError):
    """帧不合法 / 长度越界."""


class Cmd(IntEnum):
    MOVE_REL = 0x01     # int16 dx, int16 dy
    MOVE_ABS = 0x02     # int16 x,  int16 y
    BUTTON = 0x03       # uint8 mask, uint8 down(1)/up(0)
    CLICK = 0x04        # uint8 mask
    WHEEL = 0x05        # int16 delta
    KEY_DOWN = 0x06     # uint8 modifier, uint8 hid_keycode
    KEY_UP = 0x07       # uint8 modifier, uint8 hid_keycode
    KEY_TAP = 0x08      # uint8 modifier, uint8 hid_keycode, uint16 hold_ms
    TYPE_TEXT = 0x09    # ascii bytes (可分段发送)
    DELAY = 0x0A        # uint16 ms
    PING = 0x0B         # uint16 seq
    PONG = 0x0C         # uint16 seq
    RELEASE_ALL = 0x0D  # 无负载: 松开所有键和鼠标键
    INFO = 0x0E         # 无负载: 请求固件回一段 ASCII 版本串

BUTTONS = {"left": 0x01, "right": 0x02, "middle": 0x04}


def crc8(data: bytes, crc: int = 0x00) -> int:
    """CRC-8/ATM (poly 0x07, init 0x00), 与固件端逐位实现保持一致."""
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ CRC8_POLY) & 0xFF if (crc & 0x80) else (crc << 1) & 0xFF
    return crc


def encode_frame(cmd: int, payload: bytes | bytearray = b"") -> bytes:
    """把一条命令打包成线上帧, 含 CRC8."""
    payload = bytes(payload)
    if len(payload) > MAX_PAYLOAD:
        raise ProtocolError(f"payload too long: {len(payload)} > {MAX_PAYLOAD}")
    body = bytes((int(cmd) & 0xFF, len(payload))) + payload
    return MAGIC + body + bytes((crc8(body),))


def frame_len(cmd: int) -> int:
    """各命令的固定负载长度; 变长命令返回 -1."""
    return {
        Cmd.MOVE_REL: 4, Cmd.MOVE_ABS: 4, Cmd.BUTTON: 2, Cmd.CLICK: 1,
        Cmd.WHEEL: 2, Cmd.KEY_DOWN: 2, Cmd.KEY_UP: 2, Cmd.KEY_TAP: 4,
        Cmd.DELAY: 2, Cmd.PING: 2, Cmd.PONG: 2,
        Cmd.RELEASE_ALL: 0, Cmd.INFO: 0, Cmd.TYPE_TEXT: -1,
    }.get(Cmd(cmd), -1)


def check_frame(raw: bytes) -> bool:
    """校验一段完整帧 (长度/魔数/CRC 全对才为 True)."""
    if len(raw) < _MIN_FRAME or raw[:2] != MAGIC:
        return False
    plen = raw[3]
    if len(raw) != _HDR + plen + _CRC:
        return False
    return crc8(raw[2:_HDR + plen]) == raw[-1]


class FrameDecoder:
    """流式解码器: feed() 任意切分的数据, 返回本轮凑齐的 [(cmd, payload), ...].

    关键行为 (基线版本缺失的部分):
      * 半帧缓存: 不足一帧时留在缓冲区, 等下次 feed
      * 垃圾重同步: 帧头前/CRC 错的字节被丢弃并计数, 不会污染后续解析
      * 缓冲区上限: 防止对端持续吐垃圾把内存吃满
    """

    def __init__(self, max_buffer: int = 8192) -> None:
        self._buf = bytearray()
        self.max_buffer = max_buffer
        self.resyncs = 0        # 丢弃的垃圾字节数
        self.crc_errors = 0     # CRC 校验失败次数
        self.frames_ok = 0      # 成功解出的帧数

    def feed(self, data: bytes | bytearray) -> List[Tuple[int, bytes]]:
        self._buf.extend(data)
        out: List[Tuple[int, bytes]] = []
        while True:
            idx = self._buf.find(MAGIC)
            if idx < 0:
                # 没有帧头: 保留最后 1 字节 (可能是 0xAA 的前半)
                if len(self._buf) > 1:
                    self.resyncs += len(self._buf) - 1
                    del self._buf[:-1]
                break
            if idx > 0:
                self.resyncs += idx
                del self._buf[:idx]
            if len(self._buf) < _HDR:
                break
            plen = self._buf[3]
            total = _HDR + plen + _CRC
            if len(self._buf) < total:
                break                              # 半帧 -> 等下一次
            frame = bytes(self._buf[:total])
            if crc8(frame[2:_HDR + plen]) != frame[-1]:
                self.crc_errors += 1
                self.resyncs += 2
                del self._buf[:2]                  # 跳过这对魔数, 重新找头
                continue
            out.append((frame[2], frame[_HDR:_HDR + plen]))
            self.frames_ok += 1
            del self._buf[:total]
        if len(self._buf) > self.max_buffer:
            self.resyncs += len(self._buf) - 1
            del self._buf[:-1]
        return out

    @property
    def pending(self) -> bytes:
        """还没凑齐的尾部字节 (调试用)."""
        return bytes(self._buf)

    def stats(self) -> dict:
        return {"frames_ok": self.frames_ok, "crc_errors": self.crc_errors,
                "resyncs": self.resyncs, "buffered": len(self._buf)}


# --------------------------------------------------------------------------- #
# 便捷构造器 (给上层直接调用)
# --------------------------------------------------------------------------- #
def move_rel(dx: int, dy: int) -> bytes:
    return encode_frame(Cmd.MOVE_REL, struct.pack("<hh", int(dx), int(dy)))


def move_abs(x: int, y: int) -> bytes:
    return encode_frame(Cmd.MOVE_ABS, struct.pack("<hh", int(x), int(y)))


def button(btn: str | int = "left", down: bool = True) -> bytes:
    mask = BUTTONS[btn] if isinstance(btn, str) else int(btn)
    return encode_frame(Cmd.BUTTON, bytes((mask & 0xFF, 1 if down else 0)))


def click(btn: str | int = "left") -> bytes:
    mask = BUTTONS[btn] if isinstance(btn, str) else int(btn)
    return encode_frame(Cmd.CLICK, bytes((mask & 0xFF,)))


def wheel(delta: int) -> bytes:
    return encode_frame(Cmd.WHEEL, struct.pack("<h", int(delta)))


def key_down(modifier: int, keycode: int) -> bytes:
    return encode_frame(Cmd.KEY_DOWN, bytes((modifier & 0xFF, keycode & 0xFF)))


def key_up(modifier: int, keycode: int) -> bytes:
    return encode_frame(Cmd.KEY_UP, bytes((modifier & 0xFF, keycode & 0xFF)))


def key_tap(modifier: int, keycode: int, hold_ms: int = 45) -> bytes:
    return encode_frame(Cmd.KEY_TAP, bytes((modifier & 0xFF, keycode & 0xFF)) + struct.pack("<H", int(hold_ms)))


def delay(ms: int) -> bytes:
    return encode_frame(Cmd.DELAY, struct.pack("<H", int(ms)))


def ping(seq: int = 0) -> bytes:
    return encode_frame(Cmd.PING, struct.pack("<H", seq & 0xFFFF))


def release_all() -> bytes:
    return encode_frame(Cmd.RELEASE_ALL, b"")


def request_info() -> bytes:
    return encode_frame(Cmd.INFO, b"")


def type_text(text: str, chunk: int = 32) -> List[bytes]:
    """ASCII 文本 -> 多个 TYPE_TEXT 帧 (固件按帧逐字符按键盘发送)."""
    bad = precheck_text(text)
    if bad:
        raise ProtocolError(f"硬件键盘打不出这些字符: {bad!r} (仅支持 ASCII 可见字符 + 换行/制表)")
    raw = text.encode("ascii")
    return [encode_frame(Cmd.TYPE_TEXT, raw[i:i + chunk]) for i in range(0, len(raw), chunk)] or []


# --------------------------------------------------------------------------- #
# ASCII -> USB HID Usage ID: 权威表在 hidlink.keymap, 这里原样转出, 让
# ``from hidlink.protocol import HID_KEYCODES`` 这类写法继续可用。
# --------------------------------------------------------------------------- #
from .keymap import (  # noqa: E402
    HID_KEYCODES, MOD_LALT, MOD_LCTRL, MOD_LGUI, MOD_LSHIFT, MOD_NONE,
    NEEDS_SHIFT, SHIFTED, char_to_hid, precheck_text,
)
