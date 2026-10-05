"""截图 + Windows OCR (带每行/每词的屏幕坐标).

为什么要它: 盲操作 GUI 时, 必须先"看见"实际状态才能安全地点按。
PowerShell 5.1 走 WinRT 拿不到逐词坐标, 这里改用 Python + winsdk。

用法:
    python screen_ocr.py --x 2600 --y 100 --w 1200 --h 800            # 打印文字
    python screen_ocr.py --x 2600 --y 100 --w 1200 --h 800 --boxes    # 附带绝对坐标
    python screen_ocr.py ... --grep assert                            # 只显示匹配行
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import subprocess
import sys
import tempfile

from winsdk.windows.graphics.imaging import BitmapDecoder
from winsdk.windows.media.ocr import OcrEngine
from winsdk.windows.storage import FileAccessMode, StorageFile


async def ocr(path: str):
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise RuntimeError("系统没有可用的 OCR 语言包")
    f = await StorageFile.get_file_from_path_async(path)
    stream = await f.open_async(FileAccessMode.READ)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    return await engine.recognize_async(bitmap)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=int, default=2560)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--grep", default=None)
    ap.add_argument("--boxes", action="store_true")
    ap.add_argument("--image", default=os.path.join(tempfile.gettempdir(), "vdesk_ocr.png"))
    a = ap.parse_args()

    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "gdigrab",
                    "-offset_x", str(a.x), "-offset_y", str(a.y),
                    "-video_size", f"{a.w}x{a.h}", "-i", "desktop",
                    "-frames:v", "1", "-y", a.image],
                   check=True, creationflags=0x08000000)

    res = asyncio.run(ocr(a.image))
    lines = list(res.lines)
    print(f"--- OCR {a.w}x{a.h} @ ({a.x},{a.y})  共 {len(lines)} 行 ---")
    for ln in lines:
        words = list(ln.words)
        if not words:
            continue
        xs = [w.bounding_rect.x for w in words]
        ys = [w.bounding_rect.y for w in words]
        xe = [w.bounding_rect.x + w.bounding_rect.width for w in words]
        ye = [w.bounding_rect.y + w.bounding_rect.height for w in words]
        sx, sy = a.x + int(min(xs)), a.y + int(min(ys))
        ex, ey = a.x + int(max(xe)), a.y + int(max(ye))
        text = ln.text
        if a.grep and not re.search(a.grep, text, re.I):
            continue
        if a.boxes:
            print(f"  [{sx},{sy} - {ex},{ey}]  中心({(sx+ex)//2},{(sy+ey)//2})  {text}")
        else:
            print("  " + text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())