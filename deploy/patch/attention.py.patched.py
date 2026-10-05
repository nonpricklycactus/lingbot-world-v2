import torch
import os

try:
    import flash_attn_interface
    FLASH_ATTN_3_AVAILABLE = True
except ModuleNotFoundError:
    FLASH_ATTN_3_AVAILABLE = False

try:
    import flash_attn
    FLASH_ATTN_2_AVAILABLE = True
except ModuleNotFoundError:
    FLASH_ATTN_2_AVAILABLE = False

import warnings

__all__ = [
    'flash_attention',
    'attention',
]


def flash_attention(
    q,
    k,
    v,
    q_lens=None,
    k_lens=None,
    dropout_p=0.,
    softmax_scale=None,
    q_scale=None,
    causal=False,
    window_size=(-1, -1),
    deterministic=False,
    dtype=torch.bfloat16,
    version=None,
):
    """
    q:              [B, Lq, Nq, C1].
    k:              [B, Lk, Nk, C1].
    v:              [B, Lk, Nk, C2]. Nq must be divisible by Nk.
    q_lens:         [B].
    k_lens:         [B].
    dropout_p:      float. Dropout probability.
    softmax_scale:  float. The scaling of QK^T before applying softmax.
    causal:         bool. Whether to apply causal attention mask.
    window_size:    (left right). If not (-1, -1), apply sliding window local attention.
    deterministic:  bool. If True, slightly slower and uses more memory.
    dtype:          torch.dtype. Apply when dtype of q/k/v is not float16/bfloat16.
    """
    if _attention_impl() == 'sdpa':
        return _sdpa_varlen_attention(q, k, v, q_lens=q_lens, k_lens=k_lens,
                                      dropout_p=dropout_p, softmax_scale=softmax_scale,
                                      q_scale=q_scale, causal=causal,
                                      window_size=window_size, dtype=dtype)

    half_dtypes = (torch.float16, torch.bfloat16)
    assert dtype in half_dtypes
    assert q.device.type == 'cuda' and q.size(-1) <= 256

    # params
    b, lq, lk, out_dtype = q.size(0), q.size(1), k.size(1), q.dtype

    def half(x):
        return x if x.dtype in half_dtypes else x.to(dtype)

    # preprocess query
    if q_lens is None:
        q = half(q.flatten(0, 1))
        q_lens = torch.tensor(
            [lq] * b, dtype=torch.int32).to(
                device=q.device, non_blocking=True)
    else:
        q = half(torch.cat([u[:v] for u, v in zip(q, q_lens)]))

    # preprocess key, value
    if k_lens is None:
        k = half(k.flatten(0, 1))
        v = half(v.flatten(0, 1))
        k_lens = torch.tensor(
            [lk] * b, dtype=torch.int32).to(
                device=k.device, non_blocking=True)
    else:
        k = half(torch.cat([u[:v] for u, v in zip(k, k_lens)]))
        v = half(torch.cat([u[:v] for u, v in zip(v, k_lens)]))

    q = q.to(v.dtype)
    k = k.to(v.dtype)

    if q_scale is not None:
        q = q * q_scale

    if version is not None and version == 3 and not FLASH_ATTN_3_AVAILABLE:
        warnings.warn(
            'Flash attention 3 is not available, use flash attention 2 instead.'
        )

    # apply attention
    if (version is None or version == 3) and FLASH_ATTN_3_AVAILABLE:
        # Note: dropout_p, window_size are not supported in FA3 now.
        x = flash_attn_interface.flash_attn_varlen_func(
            q=q,
            k=k,
            v=v,
            cu_seqlens_q=torch.cat([q_lens.new_zeros([1]), q_lens]).cumsum(
                0, dtype=torch.int32).to(q.device, non_blocking=True),
            cu_seqlens_k=torch.cat([k_lens.new_zeros([1]), k_lens]).cumsum(
                0, dtype=torch.int32).to(q.device, non_blocking=True),
            seqused_q=None,
            seqused_k=None,
            max_seqlen_q=lq,
            max_seqlen_k=lk,
            softmax_scale=softmax_scale,
            causal=causal,
            deterministic=deterministic).unflatten(0, (b, lq))
    else:
        assert FLASH_ATTN_2_AVAILABLE
        x = flash_attn.flash_attn_varlen_func(
            q=q,
            k=k,
            v=v,
            cu_seqlens_q=torch.cat([q_lens.new_zeros([1]), q_lens]).cumsum(
                0, dtype=torch.int32).to(q.device, non_blocking=True),
            cu_seqlens_k=torch.cat([k_lens.new_zeros([1]), k_lens]).cumsum(
                0, dtype=torch.int32).to(q.device, non_blocking=True),
            max_seqlen_q=lq,
            max_seqlen_k=lk,
            dropout_p=dropout_p,
            softmax_scale=softmax_scale,
            causal=causal,
            window_size=window_size,
            deterministic=deterministic).unflatten(0, (b, lq))

    # output
    return x.type(out_dtype)


def attention(
    q,
    k,
    v,
    q_lens=None,
    k_lens=None,
    dropout_p=0.,
    softmax_scale=None,
    q_scale=None,
    causal=False,
    window_size=(-1, -1),
    deterministic=False,
    dtype=torch.bfloat16,
    fa_version=None,
):
    # [本地补丁] 统一走 flash_attention(): 没有 flash-attn 时它会退到等价的 SDPA 实现,
    # 原来的官方回退会静默忽略 padding mask, 那会改变结果。
    return flash_attention(
        q=q,
        k=k,
        v=v,
        q_lens=q_lens,
        k_lens=k_lens,
        dropout_p=dropout_p,
        softmax_scale=softmax_scale,
        q_scale=q_scale,
        causal=causal,
        window_size=window_size,
        deterministic=deterministic,
        dtype=dtype,
        version=fa_version,
    )


def _attention_impl():
    want = (os.environ.get('WAN_ATTENTION_IMPL') or 'auto').strip().lower()
    if want == 'sdpa':
        return 'sdpa'
    if want == 'flash':
        return 'flash'
    return 'flash' if (FLASH_ATTN_2_AVAILABLE or FLASH_ATTN_3_AVAILABLE) else 'sdpa'


def _sdpa_varlen_attention(q, k, v, q_lens=None, k_lens=None, dropout_p=0., softmax_scale=None, q_scale=None, causal=False, window_size=(-1, -1), dtype=torch.bfloat16):
    b, lq, nq = q.shape[0], q.shape[1], q.shape[2]
    lk, nk = k.shape[1], k.shape[2]
    out_dtype = q.dtype
    half_dtypes = (torch.float16, torch.bfloat16)
    q_ = q.transpose(1, 2)
    k_ = k.transpose(1, 2)
    v_ = v.transpose(1, 2)
    if q_.dtype not in half_dtypes or k_.dtype not in half_dtypes or v_.dtype not in half_dtypes:
        q_, k_, v_ = q_.to(dtype), k_.to(dtype), v_.to(dtype)
    if q_scale is not None:
        q_ = q_ * q_scale
    if nq != nk:
        rep = nq // nk
        k_ = k_.repeat_interleave(rep, dim=1)
        v_ = v_.repeat_interleave(rep, dim=1)
    left, right = window_size if window_size is not None else (-1, -1)
    need_mask = (q_lens is not None) or (k_lens is not None) or (left >= 0) or (right >= 0)
    if not need_mask:
        out = torch.nn.functional.scaled_dot_product_attention(q_, k_, v_, attn_mask=None, is_causal=bool(causal), dropout_p=dropout_p, scale=softmax_scale)
    else:
        idx_q = torch.arange(lq, device=q.device).view(1, 1, lq, 1)
        idx_k = torch.arange(lk, device=q.device).view(1, 1, 1, lk)
        blocked = torch.zeros((1, 1, lq, lk), dtype=torch.bool, device=q.device)
        if k_lens is not None:
            blocked = blocked | (idx_k >= k_lens.to(torch.long).view(-1, 1, 1, 1))
        if q_lens is not None:
            blocked = blocked | (idx_q >= q_lens.to(torch.long).view(-1, 1, 1, 1))
        if causal:
            blocked = blocked | (idx_k > idx_q)
        if left >= 0:
            blocked = blocked | ((idx_q - idx_k) > left)
        if right >= 0:
            blocked = blocked | ((idx_k - idx_q) > right)
        empty_row = blocked.all(dim=-1, keepdim=True)
        blocked = blocked & ~(empty_row & (idx_k == 0))
        out = torch.nn.functional.scaled_dot_product_attention(q_, k_, v_, attn_mask=~blocked, is_causal=False, dropout_p=dropout_p, scale=softmax_scale)
    out = out.transpose(1, 2).contiguous()
    return out.type(out_dtype)
