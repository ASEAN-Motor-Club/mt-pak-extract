#!/usr/bin/env python3
"""Build the "Test AMC I4 Sounder" engine pak.

What ships (all at our own package paths, nothing vanilla is overridden):

    /Game/Cars/Parts/Engine/Sound/AMC/amc_i4_low|mid|high   our loops, 96 kHz mono, single chunk
    /Game/Cars/Parts/Engine/Sound/AMC/SC_AMC_I4Engine       our cue, hard imports to those waves
    /Game/Cars/Parts/Engine/AMC/Test_AMC_I4Sounder          I4_50HP clone, cue swapped to ours
    DataAsset/VehicleParts/Engines                          base table + our row

The Engines table is lifted from the already-shipped Hams engines pak and one row is
appended, so this pak supersedes that one by load order (`zzz_`) without dropping the
other custom engines. Only one pak may own the Engines DataTable - last to load wins.

Pipeline, in order (each step is a separate cuepatch pass so a regression is bisectable):

  1. amci4loops  point the three wave players at our waves and add the hard package
                 imports the cue needs for streamed audio to survive an audio-device reset
  2. amci4tune   one shared rpm->pitch law for all layers, volume-map caps, mixer balance
  3. amci4stack  the 4th mixer input: the LOW loop again, pitched, covering the high section
  4. amci4rpm    scale every rpm breakpoint by 8500/6500 to match the new redline
  5. enginerpm   MaxRPM 8500 / MaxTorque 593000  -> 50.0 hp @ ~7900 rpm

Env (all optional, defaults assume a checkout with `target/release` built):

  VANILLA     dir with the extracted vanilla assets (see below)          [required]
  MAPPINGS    Mappings.usmap                            <repo>/Mappings.usmap
  MODPACK     mod_pack binary                           <repo>/target/release/mod_pack
  MODEXPLORE  mod_explore binary                        <repo>/target/release/mod_explore
  BASE_PAK    Hams engines pak to lift the Engines table from
                                                        mods/hams-engines/builds/zzz_AMC_HamsEngines_Test_v0.4.1_0.7.19_P.pak
  BINKA_DIR   dir with the binkaenc binary + binka.py    mods/hams-engines/sounder/binka
  WORK        scratch dir                               a fresh temp dir
  OUT         output pak                                mods/hams-engines/builds/zzz_AMC_Test_I4Sounder_<ver>_0.7.19_P.pak
  DOTNET      dotnet SDK 8 binary                       dotnet
  MODPACK_LD  LD_LIBRARY_PATH for mod_pack/mod_explore  (unset = inherited)

VANILLA must contain, extracted for the target game version:
  482826-Mazda_Miata_MX5_NBFL_1_0k.{uasset,uexp,ubulk}   wave template (96 kHz mono, single chunk)
  SC_I4SportEngine.{uasset,uexp}                          cue template
  I4_50HP.{uasset,uexp}                                   engine template
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
MODS = os.path.join(REPO, "mods", "hams-engines")

VANILLA = os.environ.get("VANILLA", "")
MAP = os.environ.get("MAPPINGS", os.path.join(REPO, "Mappings.usmap"))
MODPACK = os.environ.get("MODPACK", os.path.join(REPO, "target", "release", "mod_pack"))
MODEXPLORE = os.environ.get("MODEXPLORE", os.path.join(REPO, "target", "release", "mod_explore"))
MODPACK_LD = os.environ.get("MODPACK_LD", "")
BASE_PAK = os.environ.get(
    "BASE_PAK",
    os.path.join(MODS, "builds", "zzz_AMC_HamsEngines_Test_v0.4.1_0.7.19_P.pak"),
)
BK = os.environ.get("BINKA_DIR", os.path.join(HERE, "binka"))
DOTNET = os.environ.get("DOTNET", "dotnet")
UATOOL = os.path.join(REPO, "csharp", "UAssetTool")
CUEPATCH = os.path.join(MODS, "tooling", "cuepatch")
AUDIO = os.path.join(HERE, "audio")

VERSION = "0.8.0"
DISPLAY_NAME = os.environ.get("DISPLAY_NAME", "Binka 500cc 50hp")

# When building INTO an existing pak stage (the hams-engines pak), point these at it:
#   SOUNDER_STAGE       stage root (…/build/stage) to write our assets into
#   SOUNDER_BASE_TABLE  Engines.uasset with the other engine rows already in it
#   SOUNDER_OUT_TABLE   where to write the table with our row appended
#   SOUNDER_NO_PACK=1   don't try to pack
STAGE_OVERRIDE = os.environ.get("SOUNDER_STAGE")
BASE_TABLE = os.environ.get("SOUNDER_BASE_TABLE")
OUT_TABLE = os.environ.get("SOUNDER_OUT_TABLE")
NO_PACK = os.environ.get("SOUNDER_NO_PACK") == "1"
PAK = os.environ.get(
    "OUT", os.path.join(MODS, "builds", f"zzz_AMC_Test_I4Sounder_v{VERSION}_0.7.19_P.pak")
)
WORK = os.environ.get("WORK") or tempfile.mkdtemp(prefix="amc-sounder-")
STAGE = os.path.join(STAGE_OVERRIDE or os.path.join(WORK, "stage"), "MotorTown", "Content")
WAVE_DIR = "Cars/Parts/Engine/Sound/AMC"
ENG_DIR = "Cars/Parts/Engine/AMC"
CUE_PKG = "/Game/" + WAVE_DIR + "/SC_AMC_I4Engine"
ENGINE_NAME = "Test_AMC_I4Sounder"
TEMPLATE = "482826-Mazda_Miata_MX5_NBFL_1_0k"

# asset names must stay amc_i4_low|mid|high - the cue hard-references those exact names
WAVES = [(f"amc_i4_{n}", os.path.join(AUDIO, f"amc_i4_{n}.wav"))
         for n in ("low", "mid", "high")]

# the sample rate MUST match the vanilla wave in the same cue slot (96 kHz here).
# a 48 kHz loop plays once and then dies at the loop point / engine off-on / tab-out.
SAMPLE_RATE = 96000
HOP = 1920

sys.path.insert(0, BK)
import binka  # noqa: E402
from binka import emit_stream  # noqa: E402


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-2000:])
        raise SystemExit("FAILED: " + " ".join(cmd))
    return r.stdout


def env():
    e = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    # a dotnet given as an absolute path needs its SDK bin on PATH too, otherwise the
    # CLI fails on CultureInfo/ICU init before it ever loads the project
    if os.sep in DOTNET:
        e["PATH"] = os.path.dirname(DOTNET) + os.pathsep + e.get("PATH", "")
    return e


def ld_env():
    """LD_LIBRARY_PATH for the Rust pak tools only - dotnet needs the default ICU libs."""
    e = env()
    if MODPACK_LD:
        e["LD_LIBRARY_PATH"] = MODPACK_LD
    return e


def req(path, what):
    if not path or not os.path.exists(path):
        raise SystemExit(f"missing {what}: {path}\n"
                         f"set VANILLA=/path/to/extracted/vanilla and retry")


def clone(old_asset, cfg, outdir):
    shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir)
    cfg_path = os.path.join(outdir, "clone.json")
    json.dump(cfg, open(cfg_path, "w"), indent=2)
    sh([DOTNET, "run", "-c", "Release", "--no-build", "--project", ".",
        "--", "--clone-asset", cfg_path, old_asset, outdir], cwd=UATOOL, env=env())
    # clone-asset nests its output one dir deeper; flatten it
    sub = os.path.join(outdir, cfg["new_name"])
    if os.path.isdir(sub):
        for f in os.listdir(sub):
            shutil.copy(os.path.join(sub, f), os.path.join(outdir, f))


def cuepass(profile, src, tag, extra=()):
    out = os.path.join(WORK, "cue_" + tag)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    sh([DOTNET, "run", "-c", "Release", "--project", ".",
        "--", profile, src, out, MAP, *extra], cwd=CUEPATCH, env=env())
    return os.path.join(out, "SC_AMC_I4Engine.uasset")


def build_waves():
    os.makedirs(os.path.join(STAGE, WAVE_DIR), exist_ok=True)
    tpl_ua = os.path.join(VANILLA, TEMPLATE + ".uasset")
    req(tpl_ua, "wave template")
    tpl_old_total = os.path.getsize(os.path.join(VANILLA, TEMPLATE + ".ubulk"))

    for name, wav in WAVES:
        req(wav, f"source wav {name}")
        d = os.path.join(WORK, "wav_" + name)
        clone(tpl_ua, {"new_name": name, "old_name": TEMPLATE,
                       "new_path": "/Game/" + WAVE_DIR + "/" + name,
                       "rename_exports": True, "rename_imports": False}, d)

        w96 = os.path.join(d, name + "_96k.wav")
        sh(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
            "-ar", str(SAMPLE_RATE), "-ac", "1", w96])

        abeu = os.path.join(d, name + ".binka")
        sh([os.path.join(BK, "binkaenc"), w96, abeu, "1"])
        hdr, frames = binka.split_frames(abeu)
        rate, samples = hdr["rate"], hdr["samples"]
        maxblock = max(len(f) for f in frames)
        hop = None
        for cand in (HOP, HOP * 2, HOP // 2, 2048, 4096):
            last = samples - cand * (len(frames) - 1)
            if 0 < last <= cand:
                hop = cand
                break
        assert hop, f"could not derive hop for {samples} samples / {len(frames)} frames"
        final_trim = (samples % hop) != 0
        payload = emit_stream(frames, samples, final_trim, hop)
        total = len(payload)

        pc = {"output_filename": name, "patches": [
            {"path": "SampleRate", "op": "set", "value": rate},
            {"path": "NumChannels", "op": "set", "value": 1},
            {"path": "TotalSamples", "op": "set", "value": float(samples)},
            {"path": "Duration", "op": "set", "value": round(samples / float(rate), 4)},
        ]}
        pc_path = os.path.join(d, "props.json")
        json.dump(pc, open(pc_path, "w"), indent=2)
        sh([DOTNET, "run", "-c", "Release", "--no-build", "--project", ".",
            "--", "--patch-export-props", pc_path, os.path.join(d, name + ".uasset"), d],
           cwd=UATOOL, env=env())

        # FObjectDataResource SerialSize = the real .ubulk length, in both entries
        ua_path = os.path.join(d, name + ".uasset")
        ua = bytearray(open(ua_path, "rb").read())
        for i in [i for i in range(len(ua) - 7)
                  if struct.unpack_from("<Q", ua, i)[0] == tpl_old_total]:
            struct.pack_into("<Q", ua, i, total)
        open(ua_path, "wb").write(bytes(ua))

        # .uexp Bink header: rate / samples / file size / largest compressed block
        ue_path = os.path.join(d, name + ".uexp")
        ud = bytearray(open(ue_path, "rb").read())
        o = ud.find(b"ABEU")
        assert o >= 0, "ABEU header not found in " + ue_path
        binka.HDR.pack_into(ud, o, b"ABEU", 1, 1, 0, rate, samples, maxblock, 1,
                            total + 13, 0, 1)
        tail = o + 28
        struct.pack_into("<I", ud, tail + 16, total)
        struct.pack_into("<I", ud, tail + 20, total)
        open(ue_path, "wb").write(bytes(ud))

        for ext in ("uasset", "uexp"):
            shutil.copy(os.path.join(d, name + "." + ext),
                        os.path.join(STAGE, WAVE_DIR, name + "." + ext))
        open(os.path.join(STAGE, WAVE_DIR, name + ".ubulk"), "wb").write(payload)
        print(f"  {name}: {rate} Hz {samples / rate:.2f}s {total} B "
              f"maxblk {maxblock} hop {hop} trim {final_trim}")


def build_cue():
    cue_tpl = os.path.join(VANILLA, "SC_I4SportEngine.uasset")
    req(cue_tpl, "cue template")
    cd = os.path.join(WORK, "cue_clone")
    clone(cue_tpl, {"new_name": "SC_AMC_I4Engine", "old_name": "SC_I4SportEngine",
                    "new_path": CUE_PKG, "rename_exports": True, "rename_imports": False}, cd)

    cur = os.path.join(cd, "SC_AMC_I4Engine.uasset")
    for profile, tag, extra in (
        ("amci4loops", "loops", ("hardrefs",)),   # wave assignment + hard imports
        ("amci4tune", "tune", ()),                # shared pitch law + volume caps
        ("amci4stack", "stack", ()),              # 4th input: low loop over the high section
        ("amci4rpm", "rpm", ()),                  # scale breakpoints to the 8500 rpm redline
    ):
        cur = cuepass(profile, cur, tag, extra)

    for ext in ("uasset", "uexp"):
        shutil.copy(os.path.join(os.path.dirname(cur), "SC_AMC_I4Engine." + ext),
                    os.path.join(STAGE, WAVE_DIR, "SC_AMC_I4Engine." + ext))


def build_engine():
    eng_tpl = os.path.join(VANILLA, "I4_50HP.uasset")
    req(eng_tpl, "engine template")
    ed = os.path.join(WORK, "engine")
    clone(eng_tpl, {
        "new_name": ENGINE_NAME, "old_name": "I4_50HP",
        "new_path": "/Game/" + ENG_DIR, "rename_exports": True, "rename_imports": False,
        "import_replacements": [{
            "match_class": "SoundCue", "match_name": "SC_I4SportEngine",
            "new_package_path": CUE_PKG, "new_name": "SC_AMC_I4Engine"}],
    }, ed)

    out = os.path.join(ed, "rpm")
    sh([DOTNET, "run", "-c", "Release", "--project", ".",
        "--", "enginerpm", os.path.join(ed, ENGINE_NAME + ".uasset"), out, MAP],
       cwd=CUEPATCH, env=env())
    os.makedirs(os.path.join(STAGE, ENG_DIR), exist_ok=True)
    for ext in ("uasset", "uexp"):
        shutil.copy(os.path.join(out, ENGINE_NAME + "." + ext),
                    os.path.join(STAGE, ENG_DIR, ENGINE_NAME + "." + ext))


def build_table():
    if BASE_TABLE:
        req(BASE_TABLE, "base Engines table (SOUNDER_BASE_TABLE)")
        return _add_row(BASE_TABLE, OUT_TABLE or os.path.join(WORK, "table_rows"))
    req(BASE_PAK, "base Engines pak (BASE_PAK)")
    ex = os.path.join(WORK, "table")
    os.makedirs(ex)
    for ext in ("uasset", "uexp"):
        sh([MODEXPLORE, BASE_PAK, "--extract",
            "MotorTown/Content/DataAsset/VehicleParts/Engines." + ext], cwd=ex, env=ld_env())
    src = os.path.join(ex, "mod_out", "Engines.uasset")
    if not os.path.exists(src):
        src = os.path.join(ex, "Engines.uasset")
    assert os.path.exists(src), "Engines table not extracted from BASE_PAK"
    _add_row(src, os.path.join(ex, "rows"))


def _add_row(src, out):
    cfg = {"output_filename": "Engines",
           "template_row_match": {"RowName": "I4_50HP"},
           "rows": [{"row_name": "TestEngine_AMCI4Sounder", "patches": [
               {"op": "set", "path": "Name", "value": DISPLAY_NAME},
               {"op": "set", "path": "Cost", "value": 5000},
               {"op": "set_soft_ref", "path": "EngineAsset",
                "package_path": "/Game/" + ENG_DIR + "/" + ENGINE_NAME,
                "asset_name": ENGINE_NAME}]}]}
    os.makedirs(out, exist_ok=True)
    cfg_path = os.path.join(out, "add_row.json")
    json.dump(cfg, open(cfg_path, "w"), indent=2)
    sh([DOTNET, "run", "-c", "Release", "--no-build", "--project", ".",
        "--", "--add-rows", cfg_path, src, out], cwd=UATOOL, env=env())

    tgt = os.path.join(out, "Engines.uasset")
    if not os.path.exists(tgt):
        for root, _, files in os.walk(out):
            if "Engines.uasset" in files:
                tgt = os.path.join(root, "Engines.uasset")
                break
    dst = os.path.join(STAGE, "DataAsset/VehicleParts")
    os.makedirs(dst, exist_ok=True)
    for ext in ("uasset", "uexp"):
        shutil.copy(tgt.replace(".uasset", "." + ext), os.path.join(dst, "Engines." + ext))
    print("  Engines table ->", tgt)


def main():
    req(VANILLA, "vanilla asset dir (VANILLA)")
    build_waves()
    build_cue()
    build_engine()
    build_table()
    if NO_PACK:
        print("  (SOUNDER_NO_PACK=1 - staged into", STAGE, ")")
        return
    os.makedirs(os.path.dirname(PAK), exist_ok=True)
    sh([MODPACK, os.path.join(WORK, "stage"), PAK], env=ld_env())
    print("PAK:", PAK, os.path.getsize(PAK), "bytes")
    print("sha256", hashlib.sha256(open(PAK, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
