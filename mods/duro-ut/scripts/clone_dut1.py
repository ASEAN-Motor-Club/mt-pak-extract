#!/usr/bin/env python3
"""Clone the Duro blueprint class into DUT1 by same-length byte replacement.

Why byte surgery instead of property patching: every string we need to change is
the same length as its replacement, so the file's offsets stay valid and no
re-serialisation happens. That sidesteps the two traps that ate Barracuda
attempts -- a renamed class has no schema in Mappings.usmap (so CDO edits become
no-ops), and re-serialising a cooked BP is where properties silently vanish.

Replacements (all same length):
  /Game/Cars/Models/Duro/Duro      -> /Game/Cars/Models/DUT1/DUT1   (class asset)
  /Game/Cars/Models/Duro/Body      -> /Game/Cars/Models/DUT1/Body   (our bedless body)
  /Game/Cars/Models/Duro/Tailgate  -> /Game/Cars/Models/DUT1/Tailgate (our stub door)
  Default__Duro_C                  -> Default__DUT1_C
  Duro_C                           -> DUT1_C

Anything else (the parent BP import, other Duro assets) is deliberately left
pointing at the vanilla folder.
"""
import os
import shutil
import sys

SRC_DIR = '/opt/data/cache/scratch/clone_src'
OUT_DIR = '/opt/data/cache/scratch/stage_dut1/MotorTown/Content/Cars/Models/DUT1'

REPLACEMENTS = [
    (b'/Game/Cars/Models/Duro/Duro', b'/Game/Cars/Models/DUT1/DUT1'),
    (b'/Game/Cars/Models/Duro/Body', b'/Game/Cars/Models/DUT1/Body'),
    (b'/Game/Cars/Models/Duro/Tailgate', b'/Game/Cars/Models/DUT1/Tailgate'),
    (b'Default__Duro_C', b'Default__DUT1_C'),
    (b'Duro_C', b'DUT1_C'),
]


def clone(ext):
    src = os.path.join(SRC_DIR, 'Duro' + ext)
    if not os.path.exists(src):
        sys.exit(f'missing source {src}')
    data = open(src, 'rb').read()
    total = {}
    for old, new in REPLACEMENTS:
        assert len(old) == len(new), (old, new)
        n = data.count(old)
        if n:
            data = data.replace(old, new)
        total[old.decode()] = n
    dst = os.path.join(OUT_DIR, 'DUT1' + ext)
    os.makedirs(OUT_DIR, exist_ok=True)
    open(dst, 'wb').write(data)
    print(f'{os.path.basename(dst)}: {len(data)} bytes')
    for k, v in total.items():
        print(f'   {v:4d} x {k}')


def main():
    for ext in ('.uasset', '.uexp'):
        clone(ext)


if __name__ == '__main__':
    main()
