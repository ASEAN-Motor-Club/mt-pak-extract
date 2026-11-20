#!/usr/bin/env python3
"""uv_atlas_probe.py -- check that a mesh's UVs point at sensible atlas texels.

Renders an overlay of where each polygon's UV centroid lands on the material's
texture and prints the colour statistics of the sampled texels. Use it before
cooking: a body that samples "near-white 60%" is usually sampling atlas padding
or signage instead of its paint ramps, which is the signature of a flipped V.

Usage:
  python3 uv_atlas_probe.py mesh.fbx atlas.png out_overlay.png
"""
import sys
from PIL import Image, ImageDraw


def fbx_uv0_and_mats(path):
    src = open(path, newline='').read()

    def arr(tag, start=0):
        i = src.find(tag, start)
        if i < 0:
            raise SystemExit(f'missing {tag}')
        a = src.find('a: ', i) + 3
        return src[a:src.find('\n', a)].split(','), i

    mat_ids, _ = arr('Materials: *')
    uv, i_uv = arr('UV: *', src.find('LayerElementUV: 0 '))
    names = [ln.split('"Material::')[1].split('"')[0]
             for ln in src.splitlines() if '"Material::' in ln]
    uv = [float(x) for x in uv]
    tris = [names[int(m)] for m in mat_ids]
    return names, tris, uv


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    mesh, atlas, out = sys.argv[1:4]
    names, tris, uv = fbx_uv0_and_mats(mesh)
    im = Image.open(atlas).convert('RGB')
    W, H = im.size
    overlay = im.copy()
    d = ImageDraw.Draw(overlay)

    per_mat = {}
    for t, name in enumerate(tris):
        su = sv = 0.0
        for k in range(3):
            c = t * 3 + k
            su += (uv[2 * c] % 1.0) / 3.0
            # UE/FBX v grows upward; image rows grow downward.
            sv += (1.0 - (uv[2 * c + 1] % 1.0)) / 3.0
        u, v = su, sv
        r, g, b = im.getpixel((min(W - 1, int(u * W)), min(H - 1, int(v * H))))[:3]
        acc = per_mat.setdefault(name, {'r': 0, 'g': 0, 'b': 0, 'n': 0, 'white': 0})
        acc['r'] += r
        acc['g'] += g
        acc['b'] += b
        acc['n'] += 1
        if r > 240 and g > 240 and b > 240:
            acc['white'] += 1
        d.ellipse([u * W - 2, v * H - 2, u * W + 2, v * H + 2], fill=(255, 0, 255))

    print(f'{len(tris)} polys over {len(names)} material slots')
    for name in sorted(per_mat):
        a = per_mat[name]
        n = a['n']
        print(f"  {name:20s} n={n:6d} mean RGB ({a['r'] / n:5.0f},{a['g'] / n:5.0f},"
              f"{a['b'] / n:5.0f})  near-white {100.0 * a['white'] / n:5.1f}%")
    overlay.save(out)
    print('overlay ->', out)


if __name__ == '__main__':
    main()
