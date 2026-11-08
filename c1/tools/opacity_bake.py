#!/usr/bin/env python3
"""Bake a BeamNG-style separate opacity map into the alpha channel of a cooked BaseColor texture.

TEXTURES: Mat:MT can't sample two textures through a masked master (M_AlphaTest takes one
`Color`), but BeamNG splits many materials into `<x>_d.color` + `<x>_o.data`. The faithful port is
to move the mask into the colour texture's alpha and let the masked master cut on it.

No cook involved: the platform format stays the same (BC7 or BC3), so level 0 re-encodes to the
same byte count and is written straight over the `.ubulk`. Lower mips are untouched — RGB is
unchanged, only the far-LOD alpha is slightly stale.

Dependencies (runtime, not repackaged here): `texture2ddecoder` and `etcpak` — the same wheels the
scratch baker used, importable from the venv that ships them (C1_BAKE_PYTHON_SITE below).
"""
import os
import re
import struct

try:
    import texture2ddecoder
    import etcpak
except ImportError:  # pragma: no cover - guidance, not a fallback
    import sys

    sys.exit(
        "opacity_bake: texture2ddecoder/etcpak not importable. "
        "Run with the venv that has them, e.g. "
        "/opt/data/cache/scratch/c1/.bctex/bin/python, or set PYTHONPATH to its site-packages."
    )

FMT = {
    "PF_BC7": (texture2ddecoder.decode_bc7, 16, lambda px, w, h: etcpak.compress_bc7(bytes(px), w, h)),
    "PF_DXT5": (texture2ddecoder.decode_bc3, 16, lambda px, w, h: etcpak.compress_bc3(bytes(px), w, h)),
    "PF_DXT1": (texture2ddecoder.decode_bc1, 8, None),
}


def read_tex(path_noext):
    """Read header from .uexp and mip 0 from .ubulk."""
    ue = open(path_noext + ".uexp", "rb").read()
    m = re.search(rb"PF_[A-Z0-9_]+", ue)
    if not m:
        raise RuntimeError("no pixel format in " + path_noext)
    fmt = m.group().decode()
    w, h = struct.unpack("<ii", ue[m.start() - 16 : m.start() - 8])
    ub = path_noext + ".ubulk"
    if not os.path.exists(ub):
        raise RuntimeError("inline mip data (no .ubulk): " + path_noext)
    return fmt, w, h, bytearray(open(ub, "rb").read())


def decode_level0(fmt, w, h, blob):
    if fmt in ("PF_G8", "PF_A8", "PF_R8"):
        px = bytearray(w * h * 4)
        for i in range(w * h):
            v = blob[i]
            px[i * 4 : i * 4 + 4] = bytes((v, v, v, 255))
        return px, w * h
    dec, bpp, _ = FMT[fmt]
    need = ((w + 3) // 4) * ((h + 3) // 4) * bpp
    return bytearray(dec(bytes(blob[:need]), w, h)), need


def _mip_chain(fmt: str, w: int, h: int, blob_len: int):
    """Offsets and sizes of every mip present in the bulk blob."""
    if fmt in ("PF_G8", "PF_A8", "PF_R8"):
        bpp = 1
    elif fmt in ("PF_DXT1", "PF_BC1"):
        bpp = 8
    else:  # BC3/BC7 and friends: 16 bytes per 4x4 block
        bpp = 16
    chain, off, cw, ch = [], 0, w, h
    while True:
        if bpp == 1:
            size = cw * ch
        else:
            size = max(1, (cw + 3) // 4) * max(1, (ch + 3) // 4) * bpp
        chain.append((cw, ch, off, size))
        off += size
        if off >= blob_len:
            break
        cw, ch = max(1, cw // 2), max(1, ch // 2)
    if off != blob_len:
        raise RuntimeError(f"mip chain does not tile bulk: {off} != {blob_len}")
    return chain


def _mask_values(fmt, w, h, blob):
    """Per-pixel 0-255 visibility from the opacity map, level 0 only."""
    px, _ = decode_level0(fmt, w, h, blob)
    a = px[3::4]
    if (max(a) - min(a)) > 8:
        return list(a), "mask-alpha"
    return [(px[i * 4] * 299 + px[i * 4 + 1] * 587 + px[i * 4 + 2] * 114) // 1000
            for i in range(w * h)], "mask-luma"


def _downsample(vals, w, h, nw, nh):
    """Box filter to the mip's size."""
    if (nw, nh) == (w, h):
        return vals
    out = [0] * (nw * nh)
    sx, sy = w / nw, h / nh
    for y in range(nh):
        y0, y1 = int(y * sy), max(int(y * sy) + 1, int((y + 1) * sy))
        for x in range(nw):
            x0, x1 = int(x * sx), max(int(x * sx) + 1, int((x + 1) * sx))
            tot, n = 0, 0
            for yy in range(y0, min(y1, h)):
                row = yy * w
                for xx in range(x0, min(x1, w)):
                    tot += vals[row + xx]
                    n += 1
            out[y * nw + x] = tot // max(1, n)
    return out


def bake(base_noext, op_noext, out_dir, rel_path):
    """Write the baked texture (uasset/uexp/ubulk) under out_dir/rel_path. Returns stats.

    Every mip is rebaked, not just level 0: the source colour maps carry alpha = 0 everywhere, so
    leaving the lower mips alone makes the whole surface disappear as soon as the GPU stops
    sampling mip 0 - which on a big flat quad is almost immediately.
    """
    bfmt, bw, bh, bblob = read_tex(base_noext)
    ofmt, ow, oh, oblob = read_tex(op_noext)
    if (bw, bh) != (ow, oh):
        raise RuntimeError(f"dim mismatch {bw}x{bh} vs {ow}x{oh}")
    if bfmt not in FMT or FMT[bfmt][2] is None:
        raise RuntimeError("base format not encodable: " + bfmt)

    enc = FMT[bfmt][2]
    mask, alpha_source = _mask_values(ofmt, ow, oh, oblob)
    chain = _mip_chain(bfmt, bw, bh, len(bblob))

    holes = 0
    for cw, ch, off, size in chain:
        px, _ = decode_level0(bfmt, cw, ch, bblob[off : off + size])
        mv = _downsample(mask, ow, oh, cw, ch)
        for i in range(cw * ch):
            px[i * 4 + 3] = mv[i]
        if off == 0:
            holes = sum(1 for v in mv if v < 10) / (cw * ch)
        data = enc(px, cw, ch)
        if len(data) != size:
            raise RuntimeError(f"mip {cw}x{ch}: encoded {len(data)} != {size}")
        bblob[off : off + size] = data

    dst = os.path.join(out_dir, rel_path)
    os.makedirs(dst, exist_ok=True)
    stem = os.path.basename(base_noext)
    with open(os.path.join(dst, stem + ".ubulk"), "wb") as f:
        f.write(bytes(bblob))
    for ext in ("uasset", "uexp"):
        src = base_noext + "." + ext
        if os.path.exists(src):
            with open(src, "rb") as f, open(os.path.join(dst, stem + "." + ext), "wb") as g:
                g.write(f.read())
    return {
        "texture": stem,
        "fmt": bfmt,
        "size": [bw, bh],
        "mips": len(chain),
        "alpha_source": alpha_source,
        "holes": round(holes, 3),
    }
