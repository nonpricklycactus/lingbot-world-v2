"""把命令清单以人类节奏敲进虚拟屏上的 Windows Terminal.

清单文件格式 (UTF-8, 每行一条):
    # 注释
    WAIT  2.5        等待
    WHEEL 5          鼠标滚轮往上滚 5 格 (看上面的输出)
    CLS              清屏 (等价于输入 cls 回车)
    CLEAR            不输入任何东西, 只按 Ctrl+L 清屏
    <其他>           当作命令逐字敲进去并回车

改动 (2026-10-05 用户反馈):
  * 不再自动输入"解释性提示", 讲解留给配音
  * 窗口比屏幕小一圈 (留边距), 避免底部被裁掉
  * 聚焦后自动 Ctrl+- 缩小字号 2 档, 一屏能放更多行
"""
from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from hidlink.backends import SoftwareBackend, ensure_dpi_aware  # noqa: E402

SCR_X, SCR_Y, SCR_W, SCR_H = 2560, 0, 1920, 1080
MARGIN = 24
VX, VY = SCR_X + MARGIN, SCR_Y + MARGIN
VW, VH = SCR_W - MARGIN * 2, SCR_H - MARGIN * 2
WT = r"D:\Scoop\shims\wt.exe"
CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"
u32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


def class_of(h):
    b = ctypes.create_unicode_buffer(256); u32.GetClassNameW(h, b, 256); return b.value


def find_wt_on_vdesk():
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if class_of(h) == CLASS and u32.IsWindowVisible(h):
            r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
            if r.l >= SCR_X - 200:
                out.append(h)
        return True

    u32.EnumWindows(cb, 0)
    return out[0] if out else None


def load_commands(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            s = raw.rstrip("\n").rstrip("\r")
            t = s.strip()
            if not t or t.startswith("#"):
                continue
            up = t.upper()
            if up.startswith("WAIT "):
                out.append(("wait", float(t.split(None, 1)[1])))
            elif up.startswith("WHEEL "):
                out.append(("wheel", int(t.split(None, 1)[1])))
            elif up == "CLS":
                out.append(("cls", 0))
            elif up == "CLEAR":
                out.append(("clear", 0))
            else:
                out.append(("cmd", s))
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    reuse = "--reuse" in sys.argv
    zoom = 2
    for a in sys.argv[1:]:
        if a.startswith("--zoom="):
            zoom = int(a.split("=", 1)[1])
    if not args:
        print("用法: python type_into_vdesk.py <清单文件> [--reuse] [--zoom=2]"); return 1

    ensure_dpi_aware()
    be = SoftwareBackend(human=True, seed=20261005)

    hwnd = find_wt_on_vdesk() if reuse else None
    if hwnd is None:
        print("[i] 在虚拟屏新开 Windows Terminal")
        subprocess.Popen([WT, "--pos", f"{SCR_X},{SCR_Y}", "powershell.exe", "-NoLogo", "-NoExit"],
                         creationflags=0x00000008 | 0x00000200)
        for _ in range(60):
            time.sleep(0.25)
            hwnd = find_wt_on_vdesk()
            if hwnd:
                break
    if hwnd is None:
        print("!! 找不到终端窗口"); return 3

    u32.SetWindowPos(hwnd, 0, VX, VY, VW, VH, 0x0040)
    time.sleep(1.2)

    print("[i] 点标题栏聚焦")
    be.move_to(VX + VW // 2, VY + 16)
    time.sleep(0.35)
    be.click(None, None, "left", 1)
    time.sleep(0.9)
    if class_of(u32.GetForegroundWindow()) != CLASS:
        print("!! 前台不是终端, 中止"); return 2

    if zoom:
        print(f"[i] 缩小字号 {zoom} 档 (Ctrl+-)")
        for _ in range(zoom):
            be.key_tap("ctrl+-")
            time.sleep(0.35)

    be.move_to(VX + 360, VY + 240)          # 光标停在画面里
    time.sleep(0.3)

    cmds = load_commands(args[0])
    print(f"[i] 共 {len(cmds)} 条")
    for kind, val in cmds:
        if kind == "wait":
            time.sleep(val)
        elif kind == "wheel":
            be.wheel(val)
            time.sleep(0.6)
        elif kind == "cls":
            print("    > cls")
            be.type_text("cls"); time.sleep(0.4); be.key_tap("enter"); time.sleep(1.0)
        elif kind == "clear":
            be.key_tap("ctrl+l"); time.sleep(0.6)
        else:
            print("    >", val[:78])
            be.type_text(val)
            time.sleep(0.5)
            be.key_tap("enter")
            time.sleep(2.2)
    print("[i] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())