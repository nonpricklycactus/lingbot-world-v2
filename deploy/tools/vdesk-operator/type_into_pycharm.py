"""把代码逐字敲进 PyCharm 编辑器 —— 带"打开的文件名必须匹配"的硬校验.

v2 修正 (第一次验证失败暴露的问题):
  * 不能靠 `pycharm64.exe <file>` 转发: 它会另起一个实例并报 Start Failed
  * 点标题栏只给窗口焦点, 编辑器不一定有键盘焦点 -> 改用 Ctrl+Shift+N 打开文件,
    再用窗口标题反查确认"当前活动文件确实是目标文件", 不匹配就中止不敲
  * 每行敲完先 Esc (关自动补全) 再 Enter

用法:
    python type_into_pycharm.py <文件名(可含路径)> [--content=<内容文件>] [--no-esc]
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from hidlink.backends import SoftwareBackend, ensure_dpi_aware  # noqa: E402

VX, VY, VW, VH = 2560, 0, 1920, 1080
CLASS = "SunAwtFrame"
u32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


def class_of(h):
    b = ctypes.create_unicode_buffer(256); u32.GetClassNameW(h, b, 256); return b.value


def title_of(h):
    b = ctypes.create_unicode_buffer(512); u32.GetWindowTextW(h, b, 512); return b.value


def find_window(cls_name, title_contains=None):
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if class_of(h) == cls_name and u32.IsWindowVisible(h):
            if title_contains is None or title_contains in title_of(h):
                out.append(h)
        return True

    u32.EnumWindows(cb, 0)
    return out


def close_start_failed():
    for h in find_window("SunAwtDialog", "Start Failed"):
        print("  关闭残留对话框 'Start Failed'")
        u32.PostMessageW(h, 0x0010, 0, 0)      # WM_CLOSE
    time.sleep(1)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    content = None
    for a in sys.argv[1:]:
        if a.startswith("--content="):
            content = a.split("=", 1)[1]
    use_esc = "--no-esc" not in sys.argv
    if not args:
        print("用法: python type_into_pycharm.py <文件名> [--content=<内容文件>]"); return 1

    import os
    name = args[0]
    base = os.path.splitext(os.path.basename(name))[0]
    src = content or name

    ensure_dpi_aware()
    be = SoftwareBackend(human=True, seed=20261005)
    close_start_failed()

    frames = find_window(CLASS)
    if not frames:
        print("!! 没找到 PyCharm 主窗口"); return 3
    hwnd = frames[0]
    r = RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
    if r.l < 2400:
        u32.SetWindowPos(hwnd, 0, VX, VY, VW, VH, 0x0040)
        time.sleep(1.0); u32.GetWindowRect(hwnd, ctypes.byref(r))
    print(f"[i] PyCharm ({r.l},{r.t}) {r.r-r.l}x{r.b-r.t}")

    print("[i] 点标题栏, 给窗口焦点")
    be.move_to(r.l + (r.r - r.l) // 2, r.t + 40)   # 标题栏/标签栏中部, 窗口顶边可能被裁到屏幕外
    time.sleep(0.35); be.click(None, None, "left", 1); time.sleep(1.0)
    if class_of(u32.GetForegroundWindow()) != CLASS:
        print("!! 前台不是 PyCharm, 中止"); return 2

    print("[i] Ctrl+Alt+Y 同步磁盘 -> Ctrl+Shift+N 打开文件")
    be.key_tap("ctrl+alt+y"); time.sleep(1.5)
    be.key_tap("ctrl+shift+n"); time.sleep(1.2)
    be.type_text(base); time.sleep(1.8)
    be.key_tap("enter"); time.sleep(2.5)

    ok = False
    for _ in range(10):
        if base in title_of(hwnd):
            ok = True; break
        time.sleep(0.6)
    print("    当前活动文件标题:", repr(title_of(hwnd)[:70]))
    if not ok:
        print(f"!! 活动文件不是 {base}, 中止 (绝不盲敲)"); return 4

    if "--at-end" in sys.argv:
        print("[i] Ctrl+End 跳到文件末尾")
        be.key_tap("ctrl+end"); time.sleep(0.8)

    be.move_to(r.l + 700, r.t + 380); time.sleep(0.3)
    with open(src, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    # 关键: 编辑器的回车会继承上一行的缩进, 所以不要自己打前导空格 (会翻倍)。
    # 改为: 每行开头用 Tab / Shift+Tab 把缩进调到目标层级, 再打"去掉前导空格"的正文。
    def level_of(s):
        return (len(s) - len(s.lstrip(" "))) // 4

    print(f"[i] 敲入 {len(lines)} 行")
    prev = 0
    last = len(lines) - 1
    for idx, line in enumerate(lines):
        text = line.lstrip(" ")
        if not text:
            # 空行: 只回车, 不动缩进也不改基准, 否则后面所有行的缩进都会错
            if use_esc:
                be.key_tap("esc")
            be.key_tap("enter"); time.sleep(0.25)
            continue
        target = level_of(line)
        print("    |" + line[:74])
        if target > prev:
            for _ in range(target - prev):
                be.key_tap("tab"); time.sleep(0.12)
        elif target < prev:
            for _ in range(prev - target):
                be.key_tap("shift+tab"); time.sleep(0.12)
        if text:
            be.type_text(text); time.sleep(0.15)
        if use_esc:
            be.key_tap("esc"); time.sleep(0.1)
        if idx != last:                     # 最后一行不回車, 免得留下一条带缩进的空行
            be.key_tap("enter"); time.sleep(0.3)
        prev = target

    print("[i] Ctrl+S 保存")
    be.key_tap("ctrl+s"); time.sleep(2.0)
    print("[i] 完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())