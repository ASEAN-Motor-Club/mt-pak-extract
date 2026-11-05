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


def bake(base_noext, op_noext, out_dir, rel_path):
    """Write the baked texture (uasset/uexp/ubulk) under out_dir/rel_path. Returns stats."""
    bfmt, bw, bh, bblob = read_tex(base_noext)
    ofmt, ow, oh, oblob = read_tex(op_noext)
    if (bw, bh) != (ow, oh):
        raise RuntimeError(f"dim mismatch {bw}x{bh} vs {ow}x{oh}")
    if bfmt not in FMT or FMT[bfmt][2] is None:
        raise RuntimeError("base format not encodable: " + bfmt)

    bpx, need = decode_level0(bfmt, bw, bh, bblob)
    opx, _ = decode_level0(ofmt, ow, oh, oblob)

    alpha = opx[3::4]
    use_alpha = (max(alpha) - min(alpha)) > 8
    holes = 0
    for i in range(bw * bh):
        if use_alpha:
            v = opx[i * 4 + 3]
        else:
            v = (opx[i * 4] * 299 + opx[i * 4 + 1] * 587 + opx[i * 4 + 2] * 114) // 1000
        bpx[i * 4 + 3] = v
        if v < 10:
            holes += 1

    enc = FMT[bfmt][2](bpx, bw, bh)
    if len(enc) != need:
        raise RuntimeError(f"encoded {len(enc)} != {need}")
    bblob[:need] = enc

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
        "alpha_source": "mask-alpha" if use_alpha else "mask-luma",
        "holes": round(holes / (bw * bh), 3),
    }
