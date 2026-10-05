"""用鼠标双击快捷方式启动 GUI 程序. v3: 不再靠猜坐标, 而是截图找图标位置.

为什么要这样: 命令行拉起 GUI 程序会继承不合适的环境 (TEMP 指向会被清理的目录等),
PyCharm 就是这么被搞出 "Start Failed" 的; 让资源管理器去双击快捷方式 = 用户手动双击等效。

v3 做法:
  1. 把快捷方式拷进一个只放它的文件夹 (内容区只有一个图标, 好定位)
  2. 用资源管理器打开, 摆到虚拟屏固定位置
  3. ffmpeg 截这一块 -> 解析 BMP (纯 Python, 不依赖 Pillow), 找内容区第一团"非背景"像素
  4. 双击那团像素的中心

用法: python launch_by_double_click.py "<xxx.lnk>" <窗口类名> [--title=片段]
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from hidlink.backends import SoftwareBackend, ensure_dpi_aware  # noqa: E402

VX, VY = 2560, 0
WIN_W, WIN_H = 1000, 700
CHROME_H = 120          # Explorer 顶部(标题栏+地址栏+命令栏)高度, 内容区从这里往下
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


def grab_bmp(x, y, w, h, path):
    """用 ffmpeg 把屏幕这一块抓成 BMP (无压缩, 方便纯 Python 解析)."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "gdigrab",
           "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}",
           "-i", "desktop", "-frames:v", "1", "-y", path]
    subprocess.run(cmd, check=True, creationflags=0x08000000)   # CREATE_NO_WINDOW


def read_bmp(path):
    """返回 (w, h, 取像素函数 px(x,y)->(r,g,b)). 支持 24/32 位."""
    with open(path, "rb") as fh:
        data = fh.read()
    off = int.from_bytes(data[10:14], "little")
    w = int.from_bytes(data[18:22], "little", signed=True)
    h = int.from_bytes(data[22:26], "little", signed=True)
    bpp = int.from_bytes(data[28:30], "little")
    if bpp not in (24, 32):
        raise ValueError(f"不支持的 BMP 位深: {bpp}")
    stride = ((w * bpp // 8) + 3) // 4 * 4
    bottom_up = h > 0
    hh = abs(h)

    def px(x, y):
        row = (hh - 1 - y) if bottom_up else y
        i = off + row * stride + x * (bpp // 8)
        return data[i + 2], data[i + 1], data[i]

    return w, hh, px


def first_ink(w, h, px, top, x_min=200):
    """在内容区里找第一团"非背景"像素, 返回其中心 (相对坐标).

    x_min 用来跳过左侧导航窗格: Windows 11 资源管理器的导航栏约占左边 200px,
    不排除掉就会把导航项(如"文档")当成文件图标去双击。
    """
    def is_ink(c):
        r, g, b = c
        if r > 235 and g > 235 and b > 235:      # 白底/浅灰底
            return False
        if abs(r - g) < 6 and abs(g - b) < 6 and r > 200:   # 浅灰
            return False
        return True

    for y in range(top, h - 50):
        for x in range(x_min, w - 4):
            if is_ink(px(x, y)):
                # 以这个点为起点, 向右下扩一圈求中心
                x0 = x1 = x
                y0 = y1 = y
                for yy in range(y, min(h, y + 90)):
                    row_ink = [xx for xx in range(max(x_min, x - 60), min(w, x + 260))
                               if is_ink(px(xx, yy))]
                    if row_ink:
                        x0 = min(x0, row_ink[0]); x1 = max(x1, row_ink[-1]); y1 = yy
                return ((x0 + x1) // 2, (y0 + y1) // 2)
    return None


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    title_part = None
    for a in sys.argv[1:]:
        if a.startswith("--title="):
            title_part = a.split("=", 1)[1]
    if len(args) < 2:
        print("用法: python launch_by_double_click.py <lnk> <窗口类名> [--title=片段]"); return 1
    lnk, target_cls = args[0], args[1]

    ensure_dpi_aware()
    be = SoftwareBackend(human=True, seed=20261005)

    box = r"F:\Temp\lingbot-material\vdesk-shortcut"
    os.makedirs(box, exist_ok=True)
    for old in os.listdir(box):
        try: os.remove(os.path.join(box, old))
        except Exception: pass
    shutil.copy2(lnk, os.path.join(box, os.path.basename(lnk)))
    want = os.path.basename(box)
    print(f"[1] 打开只含该快捷方式的文件夹: {box}")
    subprocess.Popen(["explorer.exe", box])
    time.sleep(4.0)

    wins = [h for h in find("CabinetWClass") if want.lower() in ttl(h).lower()]
    if not wins:
        print("!! 没找到目标文件夹窗口:", [ttl(h)[:40] for h in find("CabinetWClass")]); return 3
    h = wins[0]
    u32.SetWindowPos(h, 0, VX, VY, WIN_W, WIN_H, 0x0040)
    time.sleep(1.5)
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    w, hh = r.r - r.l, r.b - r.t
    print(f"    Explorer ({r.l},{r.t}) {w}x{hh} {ttl(h)[:40]!r}")

    # 关键: 窗口没激活时, 第一次点击只用于激活, 不会作用到图标上
    print("[1.5] 先点标题栏把窗口激活")
    be.move_to(r.l + w // 2, r.t + 16); time.sleep(0.3)
    be.click(None, None, "left", 1)
    time.sleep(1.0)

    bmp = os.path.join(tempfile.gettempdir(), "vdesk_shot.bmp")
    grab_bmp(r.l, r.t, w, hh, bmp)
    bw, bh, px = read_bmp(bmp)
    spot = first_ink(bw, bh, px, CHROME_H, x_min=int(bw * 0.32))   # 跳过左侧导航栏
    print(f"[2] 截图 {bw}x{bh}, 内容区第一个图标中心 = {spot}")
    if spot is None:
        print("!! 内容区里没找到图标"); return 4

    cx, cy = r.l + spot[0], r.t + spot[1]
    print(f"[3] 鼠标移到 ({cx},{cy}) 并双击")
    be.move_to(cx, cy); time.sleep(0.4)
    be.click(None, None, "left", 1); time.sleep(0.06)
    be.click(None, None, "left", 1)

    for i in range(40):
        time.sleep(1.0)
        tw = find(target_cls, title_part)
        if tw:
            w2 = tw[0]
            rr = RECT(); u32.GetWindowRect(w2, ctypes.byref(rr))
            print(f"[4] 目标已启动: {ttl(w2)[:50]!r} ({rr.l},{rr.t}) {rr.r-rr.l}x{rr.b-rr.t}  ({i+1}s)")
            if rr.l < 2400:
                u32.SetWindowPos(w2, 0, VX, VY, 1920, 1042, 0x0040)
                print("    -> 已搬到虚拟屏")
            return 0
    print("!! 双击后目标程序没有启动"); return 5


if __name__ == "__main__":
    raise SystemExit(main())