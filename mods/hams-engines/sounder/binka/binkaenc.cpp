// Minimal WAV(16-bit PCM) -> Bink Audio (.binka) encoder using UE's own encoder SDK.
// API is C++ (mangled symbols in libbinka_ue_encode_lnx64_static.a), so this is .cpp.
#define TEXT(x) x
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include "binka_ue_encode.h"

static void* Alloc(uintptr_t n) { return malloc(n); }
static void Free(void* p) { free(p); }

int main(int argc, char** argv)
{
    if (argc < 3) { fprintf(stderr, "usage: %s in.wav out.binka [quality 0-9]\n", argv[0]); return 2; }
    int quality = (argc > 3) ? atoi(argv[3]) : 4;

    FILE* f = fopen(argv[1], "rb");
    if (!f) { perror("open wav"); return 1; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 0, SEEK_SET);
    unsigned char* buf = (unsigned char*)malloc(sz);
    if (fread(buf, 1, sz, f) != (size_t)sz) { fprintf(stderr, "read failed\n"); return 1; }
    fclose(f);

    if (memcmp(buf, "RIFF", 4) || memcmp(buf + 8, "WAVE", 4)) { fprintf(stderr, "not a RIFF/WAVE file\n"); return 1; }

    uint16_t channels = 0, bits = 0;
    uint32_t rate = 0;
    unsigned char* pcm = nullptr; uint32_t pcmLen = 0;
    long pos = 12;
    while (pos + 8 <= sz)
    {
        char id[5] = {0}; memcpy(id, buf + pos, 4);
        uint32_t len; memcpy(&len, buf + pos + 4, 4);
        long body = pos + 8;
        if (!memcmp(id, "fmt ", 4) && body + 16 <= sz)
        {
            memcpy(&channels, buf + body + 2, 2);
            memcpy(&rate, buf + body + 4, 4);
            memcpy(&bits, buf + body + 14, 2);
        }
        else if (!memcmp(id, "data", 4))
        {
            pcm = buf + body;
            pcmLen = (uint32_t)((body + len <= sz) ? len : (sz - body));
            break;
        }
        pos = body + len + (len & 1);
    }

    if (!pcm || !channels || !rate) { fprintf(stderr, "bad wav (ch=%u rate=%u pcm=%p)\n", channels, rate, (void*)pcm); return 1; }
    if (bits != 16) { fprintf(stderr, "needs 16-bit PCM, got %u\n", bits); return 1; }
    printf("in: %u Hz, %u ch, %u bytes pcm\n", rate, channels, pcmLen);

    void* out = nullptr; uint32_t outLen = 0;
    uint8_t rc = UECompressBinkAudio(pcm, pcmLen, rate, (uint8_t)channels, (uint8_t)quality,
                                     1, 2048, Alloc, Free, &out, &outLen);
    if (rc != BINKA_COMPRESS_SUCCESS) { fprintf(stderr, "compress failed rc=%u\n", rc); return 1; }

    FILE* o = fopen(argv[2], "wb");
    fwrite(out, 1, outLen, o);
    fclose(o);
    printf("out: %u bytes -> %s (q%d, %.1f:1)\n", outLen, argv[2], quality, (double)pcmLen / (double)outLen);
    return 0;
}
