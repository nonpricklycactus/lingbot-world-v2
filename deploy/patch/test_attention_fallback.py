"""验证 attention.py 的本地补丁: 语义是否等价, 以及原版缺 flash-attn 时到底坏在哪.

全部离线, 只用 PyTorch。参考实现用 float64 手写 softmax attention。
"""
import importlib.machinery
import importlib.util
import os
import unittest
import warnings

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ORIG = os.path.join(HERE, 'attention.py.orig')
PATCHED = os.path.join(HERE, 'attention.py.patched')


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ATT = load(PATCHED, 'wan_attention_patched')
ORIG_ATT = load(ORIG, 'wan_attention_orig')

DT = torch.float32


def ref_attention(q, k, v, q_lens=None, k_lens=None, causal=False,
                  window=(-1, -1), scale=None):
    """float64 参考实现: 逐样本局部下标 + 屏蔽 -> softmax -> 加权和."""
    q = q.double(); k = k.double(); v = v.double()
    b, lq, nq, d = q.shape
    lk, nk = k.shape[1], k.shape[2]
    q_ = q.transpose(1, 2); k_ = k.transpose(1, 2); v_ = v.transpose(1, 2)
    if nq != nk:
        rep = nq // nk
        k_ = k_.repeat_interleave(rep, dim=1)
        v_ = v_.repeat_interleave(rep, dim=1)
    s = (q_ * (scale if scale is not None else d ** -0.5)) @ k_.transpose(-1, -2)
    i = torch.arange(lq).view(1, 1, lq, 1)
    j = torch.arange(lk).view(1, 1, 1, lk)
    blocked = torch.zeros(1, 1, lq, lk, dtype=torch.bool)
    if k_lens is not None:
        blocked = blocked | (j >= k_lens.view(-1, 1, 1, 1))
    if q_lens is not None:
        blocked = blocked | (i >= q_lens.view(-1, 1, 1, 1))
    if causal:
        blocked = blocked | (j > i)
    left, right = window
    if left >= 0:
        blocked = blocked | ((i - j) > left)
    if right >= 0:
        blocked = blocked | ((j - i) > right)
    s = s.masked_fill(blocked, float('-inf'))
    p = torch.nan_to_num(torch.softmax(s, dim=-1))
    return (p @ v_).transpose(1, 2).to(torch.float32)


def rand(*shape, seed=0, dtype=DT):
    g = torch.Generator().manual_seed(seed)
    return torch.randn(*shape, generator=g, dtype=torch.float32).to(dtype)


class TestPatchedNumerics(unittest.TestCase):
    """补丁版与 float64 参考实现逐元素对齐 (走内部 SDPA 实现, float32 精度)."""

    def _cmp(self, q, k, v, **kw):
        mkw = dict(kw)
        if 'window' in mkw:                       # 模块参数名是 window_size
            mkw['window_size'] = mkw.pop('window')
        got = ATT._sdpa_varlen_attention(q, k, v, dtype=DT, **mkw)
        want = ref_attention(q, k, v, **kw)
        lq = q.shape[1]
        q_lens = kw.get('q_lens')
        if q_lens is None:
            self.assertTrue(torch.allclose(got, want, atol=2e-5, rtol=2e-5),
                            f'最大误差 {(got - want).abs().max().item():.3e}')
        else:
            for b in range(q.shape[0]):                 # 只比有效 query 行
                n = int(q_lens[b])
                self.assertTrue(torch.allclose(got[b, :n], want[b, :n], atol=2e-5, rtol=2e-5))

    def test_plain(self):
        self._cmp(rand(2, 16, 4, 32, seed=1), rand(2, 16, 4, 32, seed=2), rand(2, 16, 4, 32, seed=3))

    def test_gqa(self):
        self._cmp(rand(2, 16, 8, 32, seed=1), rand(2, 16, 2, 32, seed=2), rand(2, 16, 2, 32, seed=3))

    def test_causal(self):
        self._cmp(rand(1, 24, 4, 16, seed=4), rand(1, 24, 4, 16, seed=5),
                  rand(1, 24, 4, 16, seed=6), causal=True)

    def test_k_lens(self):
        self._cmp(rand(3, 12, 4, 16, seed=7), rand(3, 20, 4, 16, seed=8),
                  rand(3, 20, 4, 16, seed=9), k_lens=torch.tensor([5, 20, 13]))

    def test_q_lens_and_k_lens(self):
        self._cmp(rand(3, 12, 4, 16, seed=10), rand(3, 20, 4, 16, seed=11),
                  rand(3, 20, 4, 16, seed=12),
                  q_lens=torch.tensor([12, 7, 1]), k_lens=torch.tensor([9, 20, 4]))

    def test_window(self):
        self._cmp(rand(1, 24, 4, 16, seed=13), rand(1, 24, 4, 16, seed=14),
                  rand(1, 24, 4, 16, seed=15), causal=True, window=(4, 0))

    def test_custom_scale_and_q_scale(self):
        q, k, v = rand(1, 10, 4, 8, seed=16), rand(1, 10, 4, 8, seed=17), rand(1, 10, 4, 8, seed=18)
        got = ATT._sdpa_varlen_attention(q, k, v, dtype=DT, softmax_scale=0.25)
        self.assertTrue(torch.allclose(got, ref_attention(q, k, v, scale=0.25), atol=2e-5))
        got2 = ATT._sdpa_varlen_attention(q, k, v, dtype=DT, q_scale=0.5)
        self.assertTrue(torch.allclose(got2, ref_attention(q * 0.5, k, v), atol=2e-5))

    def test_output_shape_and_dtype(self):
        q = rand(2, 7, 4, 16, seed=19)
        out = ATT._sdpa_varlen_attention(q, rand(2, 5, 4, 16, seed=20),
                                         rand(2, 5, 4, 16, seed=21), dtype=DT)
        self.assertEqual(tuple(out.shape), (2, 7, 4, 16))
        self.assertEqual(out.dtype, torch.float32)


class TestPaddingMaskIsReal(unittest.TestCase):
    """padding 区里放垃圾数据, 有效 query 的输出必须一字不变。"""

    def _pair(self, fn, dtype):
        lk, kl = 12, 8
        k = rand(1, lk, 4, 16, seed=30, dtype=dtype)
        v = rand(1, lk, 4, 16, seed=31, dtype=dtype)
        q = rand(1, 6, 4, 16, seed=32, dtype=dtype)
        k_junk = k.clone(); k_junk[:, kl:] = 100.0
        v_junk = v.clone(); v_junk[:, kl:] = 100.0
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            a = fn(q, k, v, k_lens=torch.tensor([kl]))
            b = fn(q, k_junk, v_junk, k_lens=torch.tensor([kl]))
        return a, b

    def test_patched_masks_padding(self):
        a, b = self._pair(lambda q, k, v, k_lens: ATT.attention(q, k, v, k_lens=k_lens, dtype=DT), DT)
        self.assertTrue(torch.equal(a, b), '补丁版仍然没有屏蔽 padding')

    def test_original_ignores_padding(self):
        a, b = self._pair(lambda q, k, v, k_lens: ORIG_ATT.attention(q, k, v, k_lens=k_lens, dtype=DT), DT)
        self.assertFalse(torch.allclose(a, b, atol=1e-6), '原版居然屏蔽了 padding? 那这个补丁就没必要了')

    def test_original_warns_about_disabled_padding(self):
        q, k, v = rand(1, 4, 4, 8, seed=33), rand(1, 6, 4, 8, seed=34), rand(1, 6, 4, 8, seed=35)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')
            ORIG_ATT.attention(q, k, v, k_lens=torch.tensor([3]), dtype=DT)
        self.assertTrue(any('Padding mask is disabled' in str(x.message) for x in w))


class TestOriginalIsHardBlocked(unittest.TestCase):

    def test_sources(self):
        with open(ORIG, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('assert FLASH_ATTN_2_AVAILABLE', src)
        self.assertIn('assert q.device.type ==', src)

    def test_no_flash_attn_on_this_machine(self):
        self.assertFalse(ORIG_ATT.FLASH_ATTN_2_AVAILABLE)
        self.assertFalse(ORIG_ATT.FLASH_ATTN_3_AVAILABLE)

    def test_original_raises(self):
        q, k, v = rand(1, 4, 4, 8, seed=36), rand(1, 4, 4, 8, seed=37), rand(1, 4, 4, 8, seed=38)
        with self.assertRaises(AssertionError):
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                ORIG_ATT.flash_attention(q, k, v, dtype=torch.bfloat16)


class TestPublicEntry(unittest.TestCase):

    def test_bf16_entry_shapes(self):
        q = rand(2, 9, 4, 16, seed=40, dtype=torch.bfloat16)
        out = ATT.flash_attention(q, rand(2, 9, 4, 16, seed=41, dtype=torch.bfloat16),
                                  rand(2, 9, 4, 16, seed=42, dtype=torch.bfloat16),
                                  dtype=torch.bfloat16)
        self.assertEqual(tuple(out.shape), (2, 9, 4, 16))
        self.assertEqual(out.dtype, torch.bfloat16)

    def test_attention_delegates_to_same_result(self):
        q, k, v = rand(1, 6, 4, 8, seed=43), rand(1, 6, 4, 8, seed=44), rand(1, 6, 4, 8, seed=45)
        kl = torch.tensor([4])
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            a = ATT.attention(q, k, v, k_lens=kl, dtype=DT)
            b = ATT.flash_attention(q, k, v, k_lens=kl, dtype=DT)
        self.assertTrue(torch.equal(a, b))

    def test_impl_switch(self):
        self.assertEqual(ATT._attention_impl(), 'sdpa')          # 本机没有 flash-attn
        ATT.FLASH_ATTN_2_AVAILABLE = True
        try:
            os.environ.pop('WAN_ATTENTION_IMPL', None)
            self.assertEqual(ATT._attention_impl(), 'flash')      # auto + 有 FA -> flash
            os.environ['WAN_ATTENTION_IMPL'] = 'sdpa'
            self.assertEqual(ATT._attention_impl(), 'sdpa')       # 强制 SDPA
            ATT.FLASH_ATTN_2_AVAILABLE = False
            os.environ['WAN_ATTENTION_IMPL'] = 'flash'
            self.assertEqual(ATT._attention_impl(), 'flash')      # 强制 flash (会 assert)
        finally:
            os.environ.pop('WAN_ATTENTION_IMPL', None)
            ATT.FLASH_ATTN_2_AVAILABLE = False


if __name__ == '__main__':
    unittest.main(verbosity=2)