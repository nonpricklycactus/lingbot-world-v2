"""输入后端: software(SendInput) / hardware(Pico 串口) / null(离线回放).

三个后端暴露完全相同的接口, 上层 Agent 不关心动作最终是软件注入还是真 USB 键鼠:

    move_to(x, y)  move_rel(dx, dy)  click(x, y, btn)  wheel(n)
    key_tap("ctrl+s")  key_down(...)  key_up(...)  type_text("hello")
    release_all()  position()  screen_size()

建议: 默认用 software (零延迟零硬件), 只在遇到"软件注入被拦/无效"的窗口
(提权窗口、游戏 Raw Input、某些安全软件) 时切到 hardware。
"""

from __future__ import annotations

import os
import random
import time
from typing import List, Optional, Sequence, Tuple

from . import protocol as P
from .trajectory import click_gap, human_pause, human_path, key_hold_ms

IS_WINDOWS = os.name == "nt"


class Backend:
    kind = "base"
    human = True

    def __init__(self, human: bool = True, seed: Optional[int] = None) -> None:
        self.human = human
        self.rng = random.Random(seed)

    # -- 位置 -------------------------------------------------------------- #
    def position(self) -> Optional[Tuple[int, int]]:
        return None

    def screen_size(self) -> Tuple[int, int]:
        raise NotImplementedError

    # -- 动作 -------------------------------------------------------------- #
    def move_rel(self, dx: int, dy: int) -> None:
        raise NotImplementedError

    def move_to(self, x: int, y: int) -> None:
        raise NotImplementedError

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              btn: str = "left", clicks: int = 1) -> None:
        raise NotImplementedError

    def wheel(self, delta: int) -> None:
        raise NotImplementedError

    def key_tap(self, keys: str, hold_ms: Optional[int] = None) -> None:
        raise NotImplementedError

    def type_text(self, text: str) -> None:
        raise NotImplementedError

    def release_all(self) -> None:
        raise NotImplementedError

    # -- 通用 helper -------------------------------------------------------- #
    def _glide(self, dx: int, dy: int) -> None:
        """把一次位移拆成拟人化轨迹逐步发送."""
        if not self.human:
            self.move_rel(dx, dy)
            return
        for step in human_path(0, 0, dx, dy, seed=self.rng.randrange(1 << 30)):
            self.move_rel(step.dx, step.dy)
            time.sleep(step.delay)

    def pause(self, lo: float = 0.09, hi: float = 0.28) -> None:
        if self.human:
            time.sleep(human_pause(self.rng, lo, hi))

    def close(self) -> None:
        pass

    def __enter__(self) -> "Backend":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class NullBackend(Backend):
    """不碰真实桌面, 只记录动作 —— 供单元测试 / dry-run / 回放."""

    kind = "null"

    def __init__(self, human: bool = False, seed: Optional[int] = None,
                 size: Tuple[int, int] = (1920, 1080)) -> None:
        super().__init__(human=human, seed=seed)
        self.log: List[tuple] = []
        self._pos = (0, 0)
        self._size = size

    def position(self) -> Tuple[int, int]:
        return self._pos

    def screen_size(self) -> Tuple[int, int]:
        return self._size

    def move_rel(self, dx: int, dy: int) -> None:
        self._pos = (self._pos[0] + dx, self._pos[1] + dy)
        self.log.append(("move_rel", dx, dy))

    def move_to(self, x: int, y: int) -> None:
        dx, dy = x - self._pos[0], y - self._pos[1]
        self._glide(dx, dy)
        self._pos = (x, y)
        self.log.append(("move_to", x, y))

    def click(self, x=None, y=None, btn="left", clicks=1):
        if x is not None and y is not None:
            self.move_to(x, y)
        for i in range(clicks):
            if i:
                time.sleep(click_gap(self.rng) if self.human else 0)
            self.log.append(("click", btn))

    def wheel(self, delta: int) -> None:
        self.log.append(("wheel", delta))

    def key_tap(self, keys: str, hold_ms: Optional[int] = None) -> None:
        self.log.append(("key_tap", keys, hold_ms or 0))

    def type_text(self, text: str) -> None:
        self.log.append(("type_text", text))

    def release_all(self) -> None:
        self.log.append(("release_all",))


# --------------------------------------------------------------------------- #
# Windows SendInput
# --------------------------------------------------------------------------- #
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR)]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", _ULONG_PTR)]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    def ensure_dpi_aware() -> None:
        """让本进程按物理像素思考。

        默认情况下非 DPI 感知进程看到的"虚拟屏幕"尺寸是被缩放过的
        (例如 2560x1600 在 150% 缩放下报 1707x1067)。多显示器下用这种
        坐标做归一化注入, 鼠标会落错位置 —— 所以注入前先声明 DPI 感知。
        """
        try:
            if _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):   # PER_MONITOR_AWARE_V2
                return
        except Exception:
            pass
        try:
            _user32.SetProcessDPIAware()
        except Exception:
            pass
    _user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
    _user32.SendInput.restype = wintypes.UINT

    INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
    MOUSEEVENTF = {"MOVE": 0x0001, "LDOWN": 0x0002, "LUP": 0x0004, "RDOWN": 0x0008,
                   "RUP": 0x0010, "MDOWN": 0x0020, "MUP": 0x0040, "WHEEL": 0x0800,
                   "HWHEEL": 0x1000, "ABSOLUTE": 0x8000, "VIRTUALDESK": 0x4000}
    KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004

    VK: dict = {
        "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
        "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
        "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
        "insert": 0x2D, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22,
        "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28,
        "left": 0x25, "right": 0x27, "capslock": 0x14, "printscreen": 0x2C,
    }
    for _i in range(1, 25):
        VK[f"f{_i}"] = 0x6F + _i

    def _mouse_input(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> "_INPUT":
        return _INPUT(type=INPUT_MOUSE,
                      mi=_MOUSEINPUT(dx=dx, dy=dy, mouseData=data & 0xFFFFFFFF,
                                     dwFlags=flags, time=0, dwExtraInfo=0))

    def _key_input(vk: int = 0, scan: int = 0, flags: int = 0) -> "_INPUT":
        return _INPUT(type=INPUT_KEYBOARD,
                      ki=_KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0))

    def _send(*inputs: "_INPUT") -> None:
        arr = (_INPUT * len(inputs))(*inputs)
        sent = _user32.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))
        if sent != len(inputs):
            raise OSError(f"SendInput 被系统拒绝 (err={ctypes.get_last_error()}); "
                          f"若目标是提权窗口, 请改用 hardware 后端或同样以管理员身份运行")


class SoftwareBackend(Backend):
    """Windows SendInput 注入: 零硬件, 延迟最低; 打不进提权窗口/安全桌面."""

    kind = "software"

    def __init__(self, human: bool = True, seed: Optional[int] = None) -> None:
        super().__init__(human=human, seed=seed)
        if not IS_WINDOWS:
            raise RuntimeError("SoftwareBackend 仅支持 Windows; 其它平台请用 hardware 后端")
        ensure_dpi_aware()

    def screen_size(self) -> Tuple[int, int]:
        return (_user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1))

    def _virtual_desktop(self) -> Tuple[int, int, int, int]:
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
        return (_user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
                _user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
                _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
                _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))

    def position(self) -> Tuple[int, int]:
        pt = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    def move_rel(self, dx: int, dy: int) -> None:
        if dx or dy:
            _send(_mouse_input(MOUSEEVENTF["MOVE"], dx, dy))

    def move_to(self, x: int, y: int) -> None:
        if not self.human:
            self._absolute(x, y)
            return
        cx, cy = self.position()
        self._glide(x - cx, y - cy)
        self._absolute(x, y)          # 收尾, 消除累计误差

    def _absolute(self, x: int, y: int) -> None:
        vx, vy, vw, vh = self._virtual_desktop()
        nx = int(round((x - vx) * 65535 / max(1, vw - 1)))
        ny = int(round((y - vy) * 65535 / max(1, vh - 1)))
        flags = MOUSEEVENTF["MOVE"] | MOUSEEVENTF["ABSOLUTE"] | MOUSEEVENTF["VIRTUALDESK"]
        _send(_mouse_input(flags, nx, ny))

    def click(self, x=None, y=None, btn="left", clicks=1) -> None:
        if x is not None and y is not None:
            self.move_to(x, y)
        down, up = {"left": ("LDOWN", "LUP"), "right": ("RDOWN", "RUP"),
                    "middle": ("MDOWN", "MUP")}[btn]
        for i in range(clicks):
            if i:
                time.sleep(click_gap(self.rng) if self.human else 0.02)
            _send(_mouse_input(MOUSEEVENTF[down]))
            time.sleep((key_hold_ms(self.rng) / 1000.0) if self.human else 0.02)
            _send(_mouse_input(MOUSEEVENTF[up]))
        self.pause()

    def wheel(self, delta: int) -> None:
        _send(_mouse_input(MOUSEEVENTF["WHEEL"], data=(delta * 120) & 0xFFFFFFFF))

    # -- 键盘 --------------------------------------------------------------- #
    def _press_vk(self, vk: int, hold_ms: Optional[int]) -> None:
        _send(_key_input(vk=vk))
        time.sleep((hold_ms or key_hold_ms(self.rng)) / 1000.0)
        _send(_key_input(vk=vk, flags=KEYEVENTF_KEYUP))

    def key_tap(self, keys: str, hold_ms: Optional[int] = None) -> None:
        parts = [p.strip().lower() for p in keys.replace("+", " ").split() if p.strip()]
        if not parts:
            return
        vks = [VK[p] if p in VK else ord(p.upper()) if len(p) == 1 else None for p in parts]
        if any(v is None for v in vks):
            bad = [p for p, v in zip(parts, vks) if v is None]
            raise ValueError(f"无法识别的按键: {bad}; 用 ctrl/alt/shift/win/f1..f24/单字符")
        mods = [v for p, v in zip(parts, vks) if p in ("ctrl", "control", "shift", "alt", "win")]
        main = [v for p, v in zip(parts, vks) if p not in ("ctrl", "control", "shift", "alt", "win")]
        for m in mods:
            _send(_key_input(vk=m))
        for v in (main or mods):
            self._press_vk(v, hold_ms)
        for m in reversed(mods):
            _send(_key_input(vk=m, flags=KEYEVENTF_KEYUP))
        self.pause(0.05, 0.16)

    def type_text(self, text: str) -> None:
        """走 KEYEVENTF_UNICODE, 中文/emoji 也能直接打出来."""
        for ch in text:
            code = ord(ch)
            if code > 0xFFFF:                      # 补充平面 -> 代理对
                code -= 0x10000
                pair = (0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF))
            else:
                pair = (code,)
            for unit in pair:
                _send(_key_input(scan=unit, flags=KEYEVENTF_UNICODE))
                _send(_key_input(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
            if self.human:
                time.sleep(self.rng.uniform(0.012, 0.045))
            else:
                time.sleep(0.002)
        self.pause(0.05, 0.15)

    def release_all(self) -> None:
        for name in ("LUP", "RUP", "MUP"):
            _send(_mouse_input(MOUSEEVENTF[name]))
        _send(_key_input(vk=0x11, flags=KEYEVENTF_KEYUP), _key_input(vk=0x10, flags=KEYEVENTF_KEYUP),
              _key_input(vk=0x12, flags=KEYEVENTF_KEYUP), _key_input(vk=0x5B, flags=KEYEVENTF_KEYUP))


# --------------------------------------------------------------------------- #
# 硬件 HID (Pico / ESP32-S3 + CircuitPython 固件)
# --------------------------------------------------------------------------- #
class HardwareBackend(Backend):
    """把动作编码成串口帧发给单片机, 由单片机扮演真 USB 键鼠.

    dry_run=True 时不打开串口, 只把帧记进 self.sent, 便于无硬件时测试与演练.

    注意: 硬件后端"看不见光标", 所以 move_to 会先用 GetCursorPos (纯读取, 不注入)
    问系统当前光标位置, 再算出需要的相对位移 —— 这样鼠标一动都不会白动。
    """

    kind = "hardware"

    def __init__(self, port: Optional[str] = None, baud: int = 921600,
                 human: bool = True, seed: Optional[int] = None,
                 dry_run: bool = False, timeout: float = 0.05) -> None:
        super().__init__(human=human, seed=seed)
        self.baud = baud
        self.dry_run = dry_run
        self.sent: List[bytes] = []
        self.port = port or (None if dry_run else self.find_port())
        self._ser = None
        self._pos: Optional[Tuple[int, int]] = None
        self.decoder = P.FrameDecoder()
        if not dry_run:
            if not self.port:
                raise RuntimeError(
                    "没找到硬件 HID 设备。请确认 Pico 已烧录 CircuitPython 固件并插好; "
                    "或用 HardwareBackend(port='COM7') 显式指定, 或用 dry_run=True 先演练")
            import serial                                # 延迟导入, pyserial 可选
            self._ser = serial.Serial(self.port, baud, timeout=timeout,
                                      write_timeout=1.0, rtscts=False, dsrdtr=False)
            time.sleep(2.0)                              # 等 CDC 就绪, 避免开机丢帧
            self._ser.reset_input_buffer()

    # -- 设备发现 ----------------------------------------------------------- #
    RP2040_VID = 0x2E8A
    KNOWN_HINTS = ("circuitpython", "pico", "usb serial", "esp32", "ch340", "cp210")

    @classmethod
    def find_port(cls) -> Optional[str]:
        try:
            from serial.tools import list_ports
        except ImportError:
            return None
        cands = []
        for p in list_ports.comports():
            text = f"{p.description} {p.manufacturer} {p.product}".lower()
            score = 0
            if p.vid == cls.RP2040_VID:
                score += 3
            if any(h in text for h in cls.KNOWN_HINTS):
                score += 1
            if score:
                cands.append((score, p.device))
        cands.sort(reverse=True)
        return cands[0][1] if cands else None

    # -- 底层收发 ----------------------------------------------------------- #
    def _send(self, frame: bytes) -> None:
        self.sent.append(frame)
        if self._ser is not None:
            self._ser.write(frame)

    def _read_available(self) -> List[Tuple[int, bytes]]:
        if self._ser is None:
            return []
        n = self._ser.in_waiting
        return self.decoder.feed(self._ser.read(n)) if n else []

    def ping(self, timeout: float = 0.5) -> Optional[float]:
        """测一次往返延迟 (毫秒); 返回 None 表示固件没回 PONG."""
        seq = self.rng.randrange(1 << 16)
        t0 = time.perf_counter()
        self._send(P.ping(seq))
        end = t0 + timeout
        while time.perf_counter() < end:
            for cmd, payload in self._read_available():
                if cmd == P.Cmd.PONG and len(payload) == 2:
                    return (time.perf_counter() - t0) * 1000
            time.sleep(0.002)
        return None

    # -- 位置 --------------------------------------------------------------- #
    def position(self) -> Optional[Tuple[int, int]]:
        # 只读地问系统"光标在哪", 不做任何注入 —— 这样硬件后端也能精确算相对位移
        cur = _read_cursor()
        return cur if cur is not None else self._pos

    def screen_size(self) -> Tuple[int, int]:
        if IS_WINDOWS:
            return (_user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1))
        return (1920, 1080)

    # -- 动作 --------------------------------------------------------------- #
    def move_rel(self, dx: int, dy: int) -> None:
        if dx or dy:
            self._send(P.move_rel(dx, dy))

    def move_to(self, x: int, y: int) -> None:
        cur = self.position()
        if cur is None:
            self._send(P.move_abs(x, y))           # 固件不支持绝对定位时由上层保证先归零
            self._pos = (x, y)
            return
        self._glide(x - cur[0], y - cur[1])
        self._pos = (x, y)

    def click(self, x=None, y=None, btn="left", clicks=1) -> None:
        if x is not None and y is not None:
            self.move_to(x, y)
        for i in range(clicks):
            if i:
                time.sleep(click_gap(self.rng) if self.human else 0.02)
            self._send(P.button(btn, True))
            time.sleep((key_hold_ms(self.rng) / 1000.0) if self.human else 0.02)
            self._send(P.button(btn, False))
        self.pause()

    def wheel(self, delta: int) -> None:
        self._send(P.wheel(delta))

    def key_tap(self, keys: str, hold_ms: Optional[int] = None) -> None:
        parts = [p.strip().lower() for p in keys.replace("+", " ").split() if p.strip()]
        if not parts:
            return
        mod_lut = {"ctrl": P.MOD_LCTRL, "control": P.MOD_LCTRL, "shift": P.MOD_LSHIFT,
                   "alt": P.MOD_LALT, "win": P.MOD_LGUI}
        mod = 0
        main = None
        for p in parts:
            if p in mod_lut:
                mod |= mod_lut[p]
            elif p in P.HID_KEYCODES:
                main = P.HID_KEYCODES[p]
            elif len(p) == 1:
                m, k = P.char_to_hid(p)
                mod |= m
                main = k
            else:
                raise ValueError(f"硬件后端不支持的按键名: {p!r} (用 ctrl/alt/shift/win/单字符)")
        if main is None:
            raise ValueError(f"缺主键: {keys!r}")
        self._send(P.key_tap(mod, main, hold_ms or key_hold_ms(self.rng)))
        self.pause(0.05, 0.16)

    def type_text(self, text: str) -> None:
        bad = P.precheck_text(text)
        if bad:
            raise P.ProtocolError(f"硬件键盘打不出这些字符: {bad!r} (硬件路径仅支持 ASCII)")
        for frame in P.type_text(text):
            self._send(frame)
        self.pause(0.05, 0.15)

    def release_all(self) -> None:
        self._send(P.release_all())

    def close(self) -> None:
        try:
            if self._ser is not None:
                self.release_all()                      # 断线前松开所有键, 免得卡住 Ctrl
                self._ser.close()
        finally:
            self._ser = None


if IS_WINDOWS:
    def _read_cursor() -> Optional[Tuple[int, int]]:
        pt = wintypes.POINT()
        return (pt.x, pt.y) if _user32.GetCursorPos(ctypes.byref(pt)) else None
else:
    def _read_cursor() -> Optional[Tuple[int, int]]:
        return None


def make_backend(kind: str = "auto", **kw) -> Backend:
    """kind: auto | software | hardware | null."""
    kind = (kind or "auto").lower()
    if kind == "auto":
        if IS_WINDOWS:
            return SoftwareBackend(**kw)
        return HardwareBackend(**kw) if HardwareBackend.find_port() else NullBackend(**kw)
    if kind == "software":
        return SoftwareBackend(**kw)
    if kind == "hardware":
        return HardwareBackend(**kw)
    if kind == "null":
        return NullBackend(**kw)
    raise ValueError(f"未知后端: {kind!r}")


def available(kind: str) -> bool:
    if kind == "null":
        return True
    if kind == "software":
        return IS_WINDOWS
    if kind == "hardware":
        try:
            import serial  # noqa: F401
        except ImportError:
            return False
        return HardwareBackend.find_port() is not None
    return False
