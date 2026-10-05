"""§4.4 第 4 段: 改 attention.py 的两处 —— 用 Ctrl+G 定位光标, OCR 只做复核.

为什么要改做法: OCR 能读出文字, 但"点准某一行"仍受滚动位置影响。
实测 Ctrl+G 跳行是可靠的 (跳完光标就在那一行), 所以直接用它定位光标,
OCR 退回到"复核"的角色 —— 每步之后确认屏幕上确实出现了预期文字。
"""
from __future__ import annotations

import ctypes
import re
import sys
import time
from ctypes import wintypes

sys.path.insert(0, r"E:\自媒体\账号运营\tools\vdesk-operator")
from hidlink.backends import SoftwareBackend, ensure_dpi_aware  # noqa: E402
import screenshot_edit as se  # noqa: E402

NEW_LINE = ("        if _attention_impl() == 'sdpa': return _sdpa_varlen_attention(q, k, v, "
            "q_lens=q_lens, k_lens=k_lens, dropout_p=dropout_p, softmax_scale=softmax_scale, "
            "q_scale=q_scale, causal=causal, window_size=window_size, dtype=dtype)")
PAT_ASSERT = r"assert\s+FLASH_ATTN_2_AVAILA"
PAT_NEW = r"_attention_impl"


def visible(pat):
    txt = " ".join(l["text"] for l in se.shot_lines())
    return bool(re.search(pat, txt, re.I))


def main() -> int:
    ensure_dpi_aware()
    be = SoftwareBackend(human=True, seed=20261005)
    hwnd = se.find_frame()
    if not hwnd:
        print("!! 没有 PyCharm 窗口"); return 3
    if not se.focus(be, hwnd):
        print("!! 抢不回前台"); return 2

    print("[1] Ctrl+G -> 111 (实测可靠)")
    be.key_tap("ctrl+g"); time.sleep(1.2)
    be.type_text("111"); time.sleep(1.0)
    be.key_tap("enter"); time.sleep(1.5)

    print("[2] OCR 复核: 屏幕上能看到 assert 行吗")
    seen = visible(PAT_ASSERT)
    print("    能看到 assert:", seen)
    if not seen:
        print("!! 看不到, 中止 (不盲改)"); return 4

    print("[3] End -> Shift+Home -> Delete -> 输入替换行")
    be.key_tap("end"); time.sleep(0.3)
    be.key_tap("shift+home"); time.sleep(0.4)
    be.key_tap("delete"); time.sleep(0.4)
    be.type_text(NEW_LINE); time.sleep(0.5)
    be.key_tap("end"); time.sleep(0.3)

    print("[4] OCR 复核结果")
    still = visible(PAT_ASSERT)
    nownew = visible(PAT_NEW)
    print("    assert 还在:", still, " 新行出现:", nownew)

    print("[5] Ctrl+Home -> End -> 回车 -> 输入 import os")
    be.key_tap("ctrl+home"); time.sleep(0.7)
    be.key_tap("end"); time.sleep(0.3)
    be.key_tap("enter"); time.sleep(0.6)
    be.type_text("import os"); time.sleep(0.4)

    print("[6] Ctrl+S 保存")
    be.key_tap("ctrl+s"); time.sleep(2.0)
    print("完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())