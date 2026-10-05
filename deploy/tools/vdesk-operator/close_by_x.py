"""用鼠标点击窗口右上角的 X 关闭程序 (不用命令行强杀).

强杀会留下悬空锁文件 (PyCharm 的 .port 就是这样被搞坏的)。点 X 让程序正常退出。

用法: python close_by_x.py <窗口类名> [--title=片段] [--timeout=60]
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from hidlink.backends import SoftwareBackend, ensure_dpi_aware  # noqa: E402

u32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


def cls(h):
    b = ctypes.create_unicode_buffer(256); u32.GetClassNameW(h, b, 256); return b.value


def ttl(h):
    b = ctypes.create_unicode_buffer(512); u32.GetWindowTextW(h, b, 512); return b.value


def find(cls_name, title_part=None):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if cls(h) == cls_name and u32.IsWindowVisible(h):
            if title_part is None or title_part.lower() in ttl(h).lower():
                out.append(h)
        return True

    u32.EnumWindows(cb, 0)
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    title_part = None
    timeout = 90
    for a in sys.argv[1:]:
        if a.startswith("--title="):
            title_part = a.split("=", 1)[1]
        if a.startswith("--timeout="):
            timeout = int(a.split("=", 1)[1])
    if not args:
        print("用法: python close_by_x.py <窗口类名> [--title=片段]"); return 1
    target_cls = args[0]

    ensure_dpi_aware()
    be = SoftwareBackend(human=True, seed=20261005)

    wins = find(target_cls, title_part)
    if not wins:
        print("没有可关闭的窗口"); return 3
    h = wins[0]
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    print(f"[1] 关闭 {ttl(h)[:50]!r} ({r.l},{r.t}) {r.r-r.l}x{r.b-r.t}")

    # 先点标题栏激活, 再点右上角 X (窗口不可见或未激活时 X 可能点不到)
    be.move_to(r.l + (r.r - r.l) // 2, r.t + 16); time.sleep(0.3)
    be.click(None, None, "left", 1); time.sleep(0.8)
    print("[2] 点右上角 X")
    be.move_to(r.r - 22, r.t + 15); time.sleep(0.4)
    be.click(None, None, "left", 1)

    for i in range(timeout):
        time.sleep(1)
        if not find(target_cls, title_part):
            print(f"[3] 已关闭 (等待 {i+1}s)")
            return 0
    print("!! 超时, 窗口还在"); return 4


if __name__ == "__main__":
    raise SystemExit(main())