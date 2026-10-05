"""拟人化鼠标轨迹 / 人类节奏延时.

硬件 HID 只是载体, 真正决定"像不像人"的是时序和轨迹:

  * 距离越长步数越多, 但有限幅 (6..140 步)
  * 速度曲线是 ease-in-out: 起步慢 -> 中段快 -> 到位前减速
  * 路径是三次贝塞尔 + 每步抖动, 不会是一条笔直的匀速直线
  * 每步延时在 6~18ms 之间抖动 (对应 55~160Hz 的采样)
  * 每步位移按"累计位移取整"算出, 而不是"单步取整" —— 这样整数增量之和
    恰好等于 round(总位移), 不会因为每步丢半个像素而越走越偏
  * 目标坐标是浮点时 (例如截图缩放过再映射回来), 用 :class:`Pointer` 跨调用
    携带小数余量, 避免每次调用都丢同样的尾数
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Step:
    dx: int
    dy: int
    delay: float      # 秒
    x: float          # 本步结束后的理论坐标 (浮点, 便于调试)
    y: float


def _bezier(p0, p1, p2, p3, t: float) -> Tuple[float, float]:
    u = 1.0 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def human_path(x0: float, y0: float, x1: float, y1: float, *,
               seed: Optional[int] = None,
               jitter: float = 1.6,
               curve: float = 0.18,
               min_delay: float = 0.006,
               max_delay: float = 0.018,
               steps: Optional[int] = None) -> List[Step]:
    """生成从 (x0,y0) 到 (x1,y1) 的拟人化相对位移序列."""
    rng = random.Random(seed)
    dx_total, dy_total = x1 - x0, y1 - y0
    dist = math.hypot(dx_total, dy_total)
    if steps is None:
        steps = int(min(140, max(6, round(dist / 18.0))))
    if dist < 1e-9:
        return []

    # 控制点沿垂直方向偏移 -> 弧线而不是直线
    nx, ny = -dy_total / dist, dx_total / dist
    bow = curve * dist * rng.uniform(-1.0, 1.0)
    c1 = (x0 + dx_total * 0.33 + nx * bow, y0 + dy_total * 0.33 + ny * bow)
    c2 = (x0 + dx_total * 0.67 + nx * bow * 0.6, y0 + dy_total * 0.67 + ny * bow * 0.6)

    out: List[Step] = []
    prev = (x0, y0)
    moved_x = moved_y = 0.0       # 从起点算起的"浮点累计位移"
    sent_x = sent_y = 0           # 已发出去的"整数累计位移"
    for i in range(1, steps + 1):
        t = i / steps
        ease = t * t * (3 - 2 * t)                      # smoothstep 速度曲线
        px, py = _bezier((x0, y0), c1, c2, (x1, y1), ease)
        px += rng.gauss(0, jitter)                      # 手抖
        py += rng.gauss(0, jitter)
        if i == steps:                                  # 最后一步精确落点
            px, py = x1, y1
        moved_x += px - prev[0]
        moved_y += py - prev[1]
        # 关键: 对"累计位移"取整, 不是对"这一步"取整
        want_x, want_y = int(round(moved_x)), int(round(moved_y))
        out.append(Step(want_x - sent_x, want_y - sent_y,
                        rng.uniform(min_delay, max_delay), px, py))
        sent_x, sent_y = want_x, want_y
        prev = (px, py)
    return out


def step_count(dx: float, dy: float, **kw) -> int:
    return len(human_path(0, 0, dx, dy, **kw))


def human_pause(rng: random.Random, lo: float = 0.09, hi: float = 0.28) -> float:
    """动作之间的随机停顿 (人的反应/确认时间)."""
    return rng.uniform(lo, hi)


def key_hold_ms(rng: random.Random) -> int:
    """按键按住时长: 真人 30~80ms, 绝不该是 1ms."""
    return rng.randint(30, 80)


def click_gap(rng: random.Random) -> float:
    """双击间隔: 真人 90~180ms (系统默认双击阈值内)."""
    return rng.uniform(0.09, 0.18)


class Pointer:
    """跨多次调用的坐标跟踪器: 把小数余量带到下一次, 绝不系统性漂移.

    为什么需要它: 截图常被缩放后再喂给模型, 模型给回来的坐标要乘一个缩放系数
    才能变回真实像素, 于是目标是浮点。若每次都独立取整, 每步丢掉的 0.4px 会
    累积 —— 1000 步就是 400px 的偏移, 表现为"越点越偏, 最后点到屏幕外面"。

    >>> from hidlink.trajectory import Pointer
    >>> p = Pointer(0, 0, seed=1)
    >>> for _ in range(50):
    ...     p.move_to(p.x + 37.4, p.y)      # 每步只前进 37.4 像素
    >>> p.sent_x                            # 50 步之后恰好走到 round(1870.0)
    1870
    """

    def __init__(self, x: float = 0.0, y: float = 0.0, seed: Optional[int] = None) -> None:
        self.x, self.y = float(x), float(y)
        self.sent_x, self.sent_y = int(round(x)), int(round(y))
        self.rng = random.Random(seed)

    def sync(self, x: float, y: float) -> None:
        """用读到的真实坐标校正 (例如软件后端用 GetCursorPos 读回光标位置)."""
        self.x, self.y = float(x), float(y)
        self.sent_x, self.sent_y = int(round(x)), int(round(y))

    def move_to(self, x: float, y: float, **kw) -> List[Step]:
        """算出到 (x,y) 的拟人化轨迹; 末步微调, 保证绝对整数位置精确落在 round(x), round(y)."""
        x, y = float(x), float(y)
        steps = human_path(self.x, self.y, x, y,
                           seed=self.rng.randrange(1 << 30), **kw)
        if steps:
            want = (int(round(x)), int(round(y)))
            got = (sum(s.dx for s in steps), sum(s.dy for s in steps))
            last = steps[-1]
            steps[-1] = replace(last, dx=last.dx + want[0] - got[0],
                                dy=last.dy + want[1] - got[1])
            self.sent_x, self.sent_y = want
        self.x, self.y = x, y
        return steps

    def send(self, backend, x: float, y: float, **kw) -> List[Step]:
        """把轨迹按延时喂给后端, 并更新内部状态."""
        steps = self.move_to(x, y, **kw)
        for s in steps:
            backend.move_rel(s.dx, s.dy)
            time.sleep(s.delay)
        return steps
