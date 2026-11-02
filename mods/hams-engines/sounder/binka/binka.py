"""Parse UE (RAD) Bink Audio files: header, seek table, framed blocks.

Encoder output layout (from UECompressBinkAudio):
  header 28 bytes  <4sBBHIIHHIHH
      tag 'ABEU', version, channels, pad, sample_rate, sample_count,
      max_compressed_block, flags, file_size, seek_table_entries, blocks_per_entry
  seek table      seek_table_entries * 2 bytes
  frames          [0x9999][u16 size][payload] ... a final frame may use size
                  0xFFFF, which means "runs to end of file".

The decoder (UEBinkAudioDecodeInterface) wants payloads back-to-back with no
0x9999 framing - that is what split_frames() + payload_bytes() give you.
Feeding it framed data does NOT error: it emits full-scale clipped noise.
"""
import struct

HDR = struct.Struct('<4sBBHIIHHIHH')
SEEK_CONST = 491520


def read_header(path_or_bytes):
    d = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, 'rb').read()
    (tag, ver, ch, pad, rate, samples, maxcomp, flags, fsize,
     seekcnt, blocksper) = HDR.unpack_from(d, 0)
    assert tag == b'ABEU', f'not a UE bink audio file: {tag!r}'
    return dict(version=ver, channels=ch, rate=rate, samples=samples,
                max_block=maxcomp, flags=flags, file_size=fsize,
                seek_entries=seekcnt, blocks_per_entry=blocksper,
                data_offset=HDR.size + seekcnt * 2, raw=d)


def split_frames(path):
    h = read_header(path)
    d, i, out = h['raw'], h['data_offset'], []
    while i + 4 <= len(d):
        magic, sz = struct.unpack_from('<HH', d, i)
        if magic != 0x9999:
            raise ValueError(f'frame magic 0x{magic:04x} != 0x9999 at offset {i}')
        if sz == 0xFFFF:
            out.append(d[i + 4:])
            i = len(d)
            break
        out.append(d[i + 4:i + 4 + sz])
        i += 4 + sz
    h.pop('raw')
    return h, out


def payload_bytes(path):
    _, frames = split_frames(path)
    return b''.join(frames)


# --- cooked .ubulk container -------------------------------------------------------
# One SEEK stream (a multi-chunk wave = N of these concatenated, each at the byte
# offset the .uexp chunk table declares):
#   0..3    'SEEK'
#   4..7    u32 LE 491520 (constant across rates)
#   8..10   3 zero bytes
#   11..14  u32 LE frame count OF THIS CHUNK
#   15..16  2 zero bytes
#   17..    (frames-1) * u16 LE = frame payload size + 4
#   then    [0x9999][u16 size][payload] frames. The last frame of the FILE uses
#           [0x9999][0xFFFF][u16 size][u16 samples_left] and then its payload.
# Verified by rebuilding a vanilla .ubulk byte for byte.
def emit_stream(frames, total_samples, final_trim=True, hop=1920, capacity=SEEK_CONST):
    n = len(frames)
    out = bytearray(b'SEEK')
    out += struct.pack('<I', capacity) + b'\x00\x00\x00' + struct.pack('<I', n) + b'\x00\x00'
    for f in frames[:-1]:
        out += struct.pack('<H', len(f) + 4)
    for k, f in enumerate(frames):
        if k == n - 1 and final_trim:
            left = total_samples - hop * (n - 1)
            out += b'\x99\x99' + struct.pack('<HH', 0xFFFF, len(f)) + struct.pack('<H', left) + f
        else:
            out += b'\x99\x99' + struct.pack('<H', len(f)) + f
    return bytes(out)


def to_ubulk(abeu_path, out_path, hop=1920):
    """Single-stream cooked .ubulk from an ABEU file."""
    hdr, frames = split_frames(abeu_path)
    data = emit_stream(frames, hdr['samples'], True, hop)
    with open(out_path, 'wb') as fh:
        fh.write(data)
    return dict(frames=len(frames), bytes=len(data))
