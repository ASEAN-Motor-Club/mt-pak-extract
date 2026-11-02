// Decode Bink Audio blocks (back-to-back) to WAV, using UE's decoder SDK.
#define TEXT(x) x
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include "binka_ue_decode.h"

int main(int argc, char** argv)
{
    if (argc < 4) { fprintf(stderr, "usage: %s in.bin out.wav rate chans [offset]\n", argv[0]); return 2; }
    uint32_t rate = (uint32_t)atoi(argv[3]);
    uint32_t ch = (uint32_t)atoi(argv[4]);
    long off = (argc > 5) ? atol(argv[5]) : 0;
    int v2 = (argc > 6) ? atoi(argv[6]) : 1;

    FILE* f = fopen(argv[1], "rb"); if (!f) { perror("open"); return 1; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, off, SEEK_SET);
    uint8_t* buf = (uint8_t*)malloc(sz - off + BINK_UE_DECODER_EXTRA_INPUT_SPACE);
    long n = fread(buf, 1, sz - off, f); fclose(f);
    memset(buf + n, 0, BINK_UE_DECODER_EXTRA_INPUT_SPACE);

    UEBinkAudioDecodeInterface* itf = UnrealBinkAudioDecodeInterface();
    uint32_t bytes = itf->MemoryFn(rate, ch);
    void* dec = malloc(bytes);
    if (!itf->OpenFn(dec, rate, ch, 1, v2 != 0)) { fprintf(stderr, "open failed\n"); return 1; }

    FILE* o = fopen(argv[2], "wb");
    uint32_t dataBytes = 0;
    fseek(o, 44, SEEK_SET);

    uint8_t const* p = buf;
    uint8_t const* end = buf + n;
    int blocks = 0;
    while (p < end)
    {
        static uint8_t out[BinkAudioDecodeOutputMaxSize()];
        uint32_t got = itf->DecodeFn(dec, out, BinkAudioDecodeOutputMaxSize(), &p, end);
        if (!got) break;
        fwrite(out, 1, got, o); dataBytes += got; blocks++;
    }

    // patch wav header
    uint32_t u32; uint16_t u16;
    fseek(o, 0, SEEK_SET);
    fwrite("RIFF", 1, 4, o); u32 = 36 + dataBytes; fwrite(&u32, 4, 1, o);
    fwrite("WAVEfmt ", 1, 8, o); u32 = 16; fwrite(&u32, 4, 1, o);
    u16 = 1; fwrite(&u16, 2, 1, o); u16 = (uint16_t)ch; fwrite(&u16, 2, 1, o);
    u32 = rate; fwrite(&u32, 4, 1, o); u32 = rate * ch * 2; fwrite(&u32, 4, 1, o);
    u16 = (uint16_t)(ch * 2); fwrite(&u16, 2, 1, o); u16 = 16; fwrite(&u16, 2, 1, o);
    fwrite("data", 1, 4, o); u32 = dataBytes; fwrite(&u32, 4, 1, o);
    fclose(o);

    printf("decoded %d blocks, %u bytes pcm, %.2f s, from offset %ld\n", blocks, dataBytes,
           (double)dataBytes / (double)(rate * ch * 2), off);
    return 0;
}
