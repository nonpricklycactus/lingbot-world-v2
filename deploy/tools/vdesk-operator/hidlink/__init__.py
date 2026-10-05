"""hidlink - 屏幕采集 + 鼠标/键盘注入 的 AI 电脑操作工具包.

两种输入后端:
  * software  : 直接用 Windows SendInput 注入 (零硬件, 最快)
  * hardware  : 走串口把动作发给 Pico/ESP32, 由单片机扮演真 USB 键鼠 (免驱/不被拦)

两种屏幕来源:
  * dxcam / mss / PIL  : 软件截图 (默认, 高清低延迟)
  * (可选) KVM HDMI 采集卡 : 只有在需要看 BIOS/开机画面时才需要
"""

__version__ = "0.3.0"

from .protocol import Cmd, FrameDecoder, ProtocolError, crc8, encode_frame  # noqa: F401

__all__ = ["Cmd", "FrameDecoder", "ProtocolError", "crc8", "encode_frame", "__version__"]
