#!/usr/bin/env python3
"""Bake a BeamNG-style separate opacity map into the alpha channel of a cooked BaseColor texture.

TEXTURES: Mat:MT can't sample two textures through a masked master (M_AlphaTest takes one
`Color`), but BeamNG splits many materials into `<x>_d.color` + `<x>_o.data`. The faithful port is
to move the mask into the colour texture's alpha and let the masked master cut on it.

No cook involved: the platform format stays the same (BC7 or BC3), so every level re-encodes to
the same byte count and is written straight over the `.ubulk`. RGB is untouched; only alpha is
rewritten, and at every mip it is re-decided rather than averaged (see `bake()`).

Dependencies (runtime, not repackaged here): `texture2ddecoder` and `etcpak` — the same wheels the
scratch baker used, importable from the venv that ships them (C1_BAKE_PYTHON_SITE below).
"""
import os
import shutil
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

# Alpha at every mip is re-decided (0 or 255) instead of stored as the box-filtered average.
# 0.45 rather than the material's 0.5 clip: downsampling loses a little coverage on thin strokes,
# so cutting slightly low keeps them alive while still blocking the averaged background.
MASK_THRESHOLD = 0.45
# Below this resolution the chain stops being re-derived and reuses the thresholded mask, so the
# tail cannot degenerate into per-texel noise (which reads as shimmer where the leak used to be).
MASK_MIN_PX = 64
DILATE = True

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


def _dilate(vals, w, h, r=1):
    """3x3 max filter.

    Downsampling a thin stroke leaves it at ~40% coverage; a straight threshold then deletes it,
    so a 2-texel marking line would fade out at range instead of thinning. Dilate before the
    threshold keeps stroke width honest at the cost of at most one texel of growth.
    """
    if r <= 0:
        return vals
    out = [0] * (w * h)
    for y in range(h):
        y0, y1 = max(0, y - r), min(h, y + r + 1)
        for x in range(w):
            x0, x1 = max(0, x - r), min(w, x + r + 1)
            best = 0
            for yy in range(y0, y1):
                row = yy * w
                for xx in range(x0, x1):
                    v = vals[row + xx]
                    if v > best:
                        best = v
            out[y * w + x] = best
    return out


def _coverage_mask(vals, coverage):
    """Keep exactly `coverage` of the texels, the ones with the most coverage.

    Castano solves this with a scale factor (scale = A_r / a_r) found by bisection. A discrete
    threshold on the raw values can't hit the target when the downsample saturates (at 128px over
    half the texels are exactly 255, so the achievable fractions jump from 0.47 straight to 0),
    which silently erased the whole last mip. Ranking instead of thresholding is the same intent
    and lands exactly on the target: opaque = the top k values, k = round(coverage * n).
    """
    n = len(vals)
    k = int(round(coverage * n))
    if k <= 0:
        return [0] * n
    if k >= n:
        return [255] * n
    order = sorted(range(n), key=lambda i: vals[i], reverse=True)
    hard = [0] * n
    for i in order[:k]:
        hard[i] = 255
    return hard


def _nearest(vals, w, h, nw, nh):
    """Nearest-neighbour resample, used to carry a capped mask down the rest of the chain."""
    if (nw, nh) == (w, h):
        return vals
    out = [0] * (nw * nh)
    for y in range(nh):
        sy = min(h - 1, y * h // nh)
        for x in range(nw):
            out[y * nw + x] = vals[sy * w + min(w - 1, x * w // nw)]
    return out


def bake(base_noext, op_noext, out_dir, rel_path, threshold=MASK_THRESHOLD,
         min_mask=MASK_MIN_PX, dilate=DILATE):
    """Write the baked texture (uasset/uexp/ubulk) under out_dir/rel_path. Returns stats.

    Every mip is rebaked, not just level 0: the source colour maps carry alpha = 0 everywhere, so
    leaving the lower mips alone makes the whole surface disappear as soon as the GPU stops
    sampling mip 0 - which on a big flat quad is almost immediately.

    Each mip's alpha is a DECISION, not an average. Storing the box-filtered coverage (the old
    behaviour) means a gap between two marking bars averages to >0.5 at some mip and the masked
    blend then draws the quad's background at exactly that range - the region that fills in is the
    iso-LOD contour where the average crosses OpacityMaskClipValue, which is why it looks like half
    the decal is visible at a distance and the boundary sweeps when the camera tilts. Thresholding
    every level keeps coverage binary, so no mip can leak: paint erodes inward slightly instead of
    the background filling in.
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
    cut = int(round(threshold * 255))
    target_coverage = None  # set from mip 0, then held at every level below

    holes = 0
    level = 0
    mip_alphas: list[list] = []
    for cw, ch, off, size in chain:
        px, _ = decode_level0(bfmt, cw, ch, bblob[off : off + size])
        # Build the decision at no lower than min_mask, so the tail of the chain reuses a clean
        # thresholded mask instead of turning into per-texel noise that shimmers at range.
        mw, mh = max(cw, min_mask), max(ch, min_mask)
        mv = _downsample(mask, ow, oh, mw, mh)
        if dilate:
            mv = _dilate(mv, mw, mh)
        if target_coverage is None:
            # Castano, "Computing Alpha Mipmaps": the defect is that the fraction of texels passing
            # the alpha test DRIFTS with mip level (foliage erodes below the clip; a dense marking
            # mask creeps above it and closes up). Measure mip 0, then hold that coverage exactly
            # at every level below.
            hard = [255 if v >= cut else 0 for v in mv]
            target_coverage = sum(hard) / (255 * len(hard))
        else:
            hard = _coverage_mask(mv, target_coverage)
        if (mw, mh) != (cw, ch):
            hard = _nearest(hard, mw, mh, cw, ch)
        for i in range(cw * ch):
            px[i * 4 + 3] = hard[i]
        opaque = sum(1 for v in hard if v > 245) / (cw * ch)
        mip_alphas.append([cw, round(opaque, 4)])
        if off == 0:
            holes = 1.0 - opaque
        data = enc(px, cw, ch)
        if len(data) != size:
            raise RuntimeError(f"mip {cw}x{ch}: encoded {len(data)} != {size}")
        bblob[off : off + size] = data
        level += 1

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
        "mip_alphas": mip_alphas,
        "threshold": threshold,
        "min_mask": min_mask,
    }


def bake_g8(tex_noext: str, out_dir: str, rel_dir: str, clip: int = 128) -> dict:
    """Rewrite a PF_G8 opacity map's whole mip chain with constant coverage.

    The masked master binds its `Opacity` parameter to a separate G8 texture, NOT to the alpha of
    the colour map, so baking into the colour map's alpha has no effect on what the shader sees.
    G8 is uncompressed (one byte per texel), so this needs no encoder: every level is decided and
    written straight over the .ubulk.

    Castano's invariant: the fraction of texels passing the material clip is held at mip 0's value
    at every level below, so the mask can neither creep above the clip (background fills in) nor
    below it (paint disappears) as the distance grows.
    """
    fmt, w, h, blob = read_tex(tex_noext)
    if fmt != "PF_G8":
        return {"error": f"expected PF_G8, got {fmt}"}
    chain = _mip_chain(fmt, w, h, len(blob))
    out = bytearray(blob)
    levels = []
    cov = None
    prev_hard = None
    pw = ph = 0
    for idx, (cw, ch, off, size) in enumerate(chain):
        if idx == 0:
            vals = list(blob[off : off + size])
            hard = [255 if v >= clip else 0 for v in vals]
            cov = sum(hard) / (255 * len(hard))
        else:
            avg = _downsample(prev_hard, pw, ph, cw, ch)
            hard = _coverage_mask(avg, cov)
        if len(hard) != size:
            return {"error": f"mip {cw} size {len(hard)} != {size}"}
        out[off : off + size] = bytes(hard)
        levels.append([cw, round(sum(1 for v in hard if v >= 128) / len(hard), 4)])
        prev_hard, pw, ph = hard, cw, ch
    dstdir = os.path.join(out_dir, rel_dir)
    os.makedirs(dstdir, exist_ok=True)
    name = os.path.basename(tex_noext)
    for ext in (".uasset", ".uexp"):
        srcf = tex_noext + ext
        if os.path.exists(srcf):
            shutil.copy(srcf, os.path.join(dstdir, name + ext))
    open(os.path.join(dstdir, name + ".ubulk"), "wb").write(bytes(out))
    return {"format": fmt, "size": [w, h], "mips": len(chain),
            "coverage": round(cov, 4), "levels": levels}
