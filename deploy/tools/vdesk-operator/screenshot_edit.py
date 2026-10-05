"""按 OCR 找到目标行的屏幕坐标, 再用鼠标点进去改 —— 每一步都用 OCR 复核.

流程:
  1) 聚焦 PyCharm -> Ctrl+Home -> Ctrl+G 跳到目标行
  2) OCR 截取编辑器区域, 找匹配正则的那一行; 找不到就中止 (不盲改)
  3) 鼠标点到该行文字末尾 -> End -> Shift+Home -> Delete -> 输入替换内容
  4) 再 OCR 复核: 新内容出现且旧内容消失
  5) 顶部插入 import os (Ctrl+Home -> End -> 回车 -> 输入)
  6) Ctrl+S
"""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import os
import re
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

sys.path.insert(0, r"E:\自媒体\账号运营\tools\vdesk-operator")
from hidlink.backends import SoftwareBackend, ensure_dpi_aware  # noqa: E402
from winsdk.windows.graphics.imaging import BitmapDecoder  # noqa: E402
from winsdk.windows.media.ocr import OcrEngine  # noqa: E402
from winsdk.windows.storage import FileAccessMode, StorageFile  # noqa: E402

CLASS = "SunAwtFrame"
u32 = ctypes.windll.user32
EDITOR = (2560, 0, 1920, 1080)      # 先整屏 OCR, 再按正则找目标行 (不用猜编辑器在哪)
NEW_LINE = ("        if _attention_impl() == 'sdpa': return _sdpa_varlen_attention(q, k, v, "
            "q_lens=q_lens, k_lens=k_lens, dropout_p=dropout_p, softmax_scale=softmax_scale, "
            "q_scale=q_scale, causal=causal, window_size=window_size, dtype=dtype)")


class RECT(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                ("r", ctypes.c_long), ("b", ctypes.c_long)]


def cls(h):
    b = ctypes.create_unicode_buffer(256); u32.GetClassNameW(h, b, 256); return b.value


def find_frame():
    out = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if cls(h) == CLASS and u32.IsWindowVisible(h):
            out.append(h)
        return True
    u32.EnumWindows(cb, 0)
    return out[0] if out else None


async def _ocr(path):
    engine = OcrEngine.try_create_from_user_profile_languages()
    f = await StorageFile.get_file_from_path_async(path)
    st = await f.open_async(FileAccessMode.READ)
    dec = await BitmapDecoder.create_async(st)
    bmp = await dec.get_software_bitmap_async()
    return await engine.recognize_async(bmp)


def shot_lines(region=EDITOR):
    x, y, w, h = region
    img = os.path.join(tempfile.gettempdir(), "vdesk_edit.png")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "gdigrab",
                    "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}",
                    "-i", "desktop", "-frames:v", "1", "-y", img],
                   check=True, creationflags=0x08000000)
    res = asyncio.run(_ocr(img))
    out = []
    for ln in res.lines:
        ws = list(ln.words)
        if not ws:
            continue
        xs = [w.bounding_rect.x for w in ws]
        ys = [w.bounding_rect.y for w in ws]
        xe = [w.bounding_rect.x + w.bounding_rect.width for w in ws]
        ye = [w.bounding_rect.y + w.bounding_rect.height for w in ws]
        out.append({"text": ln.text,
                    "x0": x + int(min(xs)), "y0": y + int(min(ys)),
                    "x1": x + int(max(xe)), "y1": y + int(max(ye))})
    return out


def focus(be, hwnd):
    r = RECT(); u32.GetWindowRect(hwnd, ctypes.byref(r))
    for _ in range(3):
        if cls(u32.GetForegroundWindow()) == CLASS:
            return True
        be.move_to(r.l + (r.r - r.l) // 2, r.t + 40); time.sleep(0.2)
        be.click(None, None, "left", 1); time.sleep(0.7)
    return cls(u32.GetForegroundWindow()) == CLASS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--line", type=int, default=111)
    ap.add_argument("--pattern", default=r"assert\s+FLASH_ATTN_2_AVAILABLE")
    a = ap.parse_args()

    ensure_dpi_aware()
    be = SoftwareBackend(human=True, seed=20261005)
    hwnd = find_frame()
    if not hwnd:
        print("!! 没有 PyCharm 窗口"); return 3
    if not focus(be, hwnd):
        print("!! 抢不回前台"); return 2

    print(f"[1] Ctrl+G 跳到第 {a.line} 行 (实测这条可用, 且随后的 OCR 会验证)")
    be.key_tap("ctrl+g"); time.sleep(1.2)
    be.type_text(str(a.line)); time.sleep(1.0)
    be.key_tap("enter"); time.sleep(1.5)
    # 跳过去之后目标行可能在可视区边缘; 把鼠标放到编辑器里滚两格, 保证它进入画面
    be.move_to(3600, 500); time.sleep(0.3)
    be.wheel(-2); time.sleep(0.9)

    print("[2] OCR 找目标行")
    lines = shot_lines()
    hit = None
    for ln in lines:
        if re.search(a.pattern, ln["text"], re.I):
            hit = ln; break
    if hit is None:
        print("!! OCR 没找到目标行, 中止。当前可见行:")
        for ln in lines[:25]:
            print("   ", ln["text"][:70].encode("utf-8", "replace").decode("utf-8", "replace"))
        return 4
    print("    命中: [%d,%d - %d,%d] %r" % (hit["x0"], hit["y0"], hit["x1"], hit["y1"], hit["text"][:60]))

    print("[3] 点到该行文字末尾, 选中整行并替换")
    be.move_to(hit["x1"] - 8, (hit["y0"] + hit["y1"]) // 2); time.sleep(0.4)
    be.click(None, None, "left", 1); time.sleep(0.6)
    be.key_tap("end"); time.sleep(0.3)
    be.key_tap("shift+home"); time.sleep(0.4)
    be.key_tap("delete"); time.sleep(0.4)
    be.type_text(NEW_LINE); time.sleep(0.5)
    be.key_tap("end"); time.sleep(0.3)

    print("[4] OCR 复核")
    lines2 = shot_lines()
    joined = " ".join(l["text"] for l in lines2)
    ok_new = "if_attention_impl" in joined.replace(" ", "").replace("_atten tion_impl", "_attention_impl")
    still = any(re.search(a.pattern, l["text"], re.I) for l in lines2)
    print(f"    新内容出现: {ok_new}; 旧 assert 仍在: {still}")

    print("[5] 顶部插入 import os")
    be.key_tap("ctrl+home"); time.sleep(0.6)
    be.key_tap("end"); time.sleep(0.3)
    be.key_tap("enter"); time.sleep(0.5)
    be.type_text("import os"); time.sleep(0.4)

    print("[6] Ctrl+S")
    be.key_tap("ctrl+s"); time.sleep(2.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())