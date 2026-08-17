"""Parse UE5 versioned Game.locres into {namespace: {key: string}}.

Motor Town ships Game.locres per culture. Format (version 3, "shippable"):

    16-byte magic: 0E 14 74 75 67 4A 03 FC 4A 15 90 9D C3 37 7F 1B
    uint8  version
    int64  strings_array_offset
    if version >= 2: uint32 skip
    uint32 namespace_count
    per namespace:
        if version >= 2: uint32 skip
        FString namespace_name
        uint32 key_count
        per key:
            if version >= 2: uint32 skip
            FString key
            uint32 SourceStringHash
            if version >= 1: int32 str_index          -> value = strings[str_index]
            else:            FString value
            if version >= 4: uint32 skip

    strings array at strings_array_offset:
        uint32 strings_array_count
        per string:
            FString value
            if version >= 2: uint32 skip

FString: int32 length; length==0 -> ""; length<0 -> UTF-16 (|length|*2 bytes);
length>0 -> ANSI/ASCII (length bytes). The null terminator is included in the
length and stored as 1 (ANSI) or 2 (UTF-16) zero bytes.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

MAGIC = bytes([0x0E, 0x14, 0x74, 0x75, 0x67, 0x4A, 0x03, 0xFC,
               0x4A, 0x15, 0x90, 0x9D, 0xC3, 0x37, 0x7F, 0x1B])


class LocresError(Exception):
    pass


def _read_fstring(buf: bytes, off: int) -> tuple[str, int]:
    """Read an FString at buf[off:]. Returns (text, new_offset)."""
    (length,) = struct.unpack_from("<i", buf, off)
    off += 4
    if length == 0:
        return "", off
    if length < 0:
        n = -length
        raw = buf[off : off + n * 2]
        off += n * 2
        text = raw.decode("utf-16-le", errors="replace").rstrip("\x00")
        return text, off
    raw = buf[off : off + length]
    off += length
    text = raw.rstrip(b"\x00").decode("utf-8", errors="replace")
    return text, off


def parse_locres(data: bytes) -> dict[str, dict[str, str]]:
    if not data.startswith(MAGIC):
        raise LocresError("bad magic")
    version = data[len(MAGIC)]
    off = len(MAGIC) + 1

    strings: list[str] = []
    if version >= 1:
        (strings_array_offset,) = struct.unpack_from("<q", data, off)
        off += 8
        restore = off
        off = strings_array_offset
        (count,) = struct.unpack_from("<I", data, off)
        off += 4
        for _ in range(count):
            s, off = _read_fstring(data, off)
            strings.append(s)
            if version >= 2:
                off += 4
        off = restore

    if version >= 2:
        off += 4
    (namespace_count,) = struct.unpack_from("<I", data, off)
    off += 4

    out: dict[str, dict[str, str]] = {}
    for _ in range(namespace_count):
        if version >= 2:
            off += 4
        ns, off = _read_fstring(data, off)
        (key_count,) = struct.unpack_from("<I", data, off)
        off += 4
        table = out.setdefault(ns, {})
        for _ in range(key_count):
            if version >= 2:
                off += 4
            key, off = _read_fstring(data, off)
            off += 4  # SourceStringHash (uint32)
            if version >= 1:
                (sidx,) = struct.unpack_from("<i", data, off)
                off += 4
                val = strings[sidx] if 0 <= sidx < len(strings) else ""
            else:
                val, off = _read_fstring(data, off)
            if version >= 4:
                off += 4
            table[key] = val
    return out


def main() -> None:
    import sys

    root = Path(sys.argv[1] if len(sys.argv) > 1 else "locres")
    out_path = Path(sys.argv[2] if len(sys.argv) > 2 else "locres_map.json")
    langs = sorted(p.name for p in root.iterdir() if p.is_dir())
    combined: dict[str, dict[str, dict[str, str]]] = {}
    for lang in langs:
        f = root / lang / "Game.locres"
        if not f.exists():
            continue
        try:
            combined[lang] = parse_locres(f.read_bytes())
        except LocresError as e:
            print(f"  SKIP {lang}: {e}")
    out_path.write_text(json.dumps(combined, ensure_ascii=False))
    print(f"Parsed {len(combined)} languages -> {out_path.name}")
    for lang in combined:
        print(f"  {lang}: {sum(len(t) for t in combined[lang].values())} strings / {len(combined[lang])} namespaces")


if __name__ == "__main__":
    main()
