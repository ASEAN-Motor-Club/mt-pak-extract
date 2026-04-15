# AGENTS.md

## Build & Run

Always use the Nix dev shell — do not rely on system tools:

```bash
# Enter dev shell
/run/current-system/sw/bin/nix develop

# Or run commands inside it
/run/current-system/sw/bin/nix develop --command bash -c '<command>'
```

**nix binary**: `/run/current-system/sw/bin/nix` (not in default PATH on this system).

## Full Pipeline

```bash
# 1. Extract assets from PAK (Rust)
nix develop --command bash -c 'cargo run --release --quiet -- --config assets.json'

# 2. Parse extracted .uasset files (C#)
nix develop --command bash -c 'cd csharp/CargoExtractor && dotnet run --configuration Release --verbosity quiet -- --batch'

# 3. Aggregate to SQLite (Python)
nix develop --command bash -c 'python3 scripts/aggregate_to_sqlite.py'
```

Output: `motortown.db` (SQLite), `out/*_parsed.json`.

## Required Files

- **`MotorTown-Windows.pak`** — game PAK file (2.9 GB, already in repo root)
- **`.env`** — AES key (`KEY=0x...`), gitignored
- **`Mappings.usmap`** — UE5 type mappings, gitignored. Source: `/tmp/UAssetAPI-source/UAssetAPI.Tests/TestAssets/TestJson/MotorTown.usmap` (clone https://github.com/atenfyr/UAssetAPI to `/tmp/UAssetAPI-source`)
- **UAssetAPI** — C# dependency at `/tmp/UAssetAPI-source/UAssetAPI/UAssetAPI.csproj`. Clone if missing:
  ```bash
  git clone --depth 1 https://github.com/atenfyr/UAssetAPI /tmp/UAssetAPI-source
  ```

## Decal Pack Creation

Create decal mod PAKs from images in one command:

```bash
nix develop --command bash -c '
python3 scripts/create_decal_pack.py --input images/ --output MyPack_P.pak
'
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--input, -i` | (required) | Directory of images (PNG/TGA/BMP/JPG) |
| `--output, -o` | (required) | Output .pak path |
| `--category, -c` | `Custom` | Category folder name |
| `--cost` | `100` | In-game decal price |
| `--template, -t` | auto from `out/` | Template decal texture .uasset |
| `--decals, -d` | auto from `out/` | Template Decals.uasset |

### Image Requirements

- **Resolution**: Source PNGs should be **2048×2048**. Smaller images are auto-resized with transparent padding (preserves aspect ratio). Square images give best results.
- **Format**: PNG with transparency (RGBA). JPG/BMP also accepted but PNG preferred.
- **Colorspace**: sRGB. The pipeline converts through linear RGB before DXT5 compression to prevent gamma darkening.
- **Filenames**: Must not contain spaces, parentheses, or dashes. Use underscores instead (e.g., `Group_108_1.png` not `Group 108 (1).png`).
- **No extraneous files**: Remove any `.py`, `.txt`, or non-image files from the source directories.

### Image Preprocessing (before injection)

Before injecting, upscale all images to 2048×2048 with transparent padding and fix gamma:

```bash
CONVERT="/path/to/imagemagick/convert"
for img in source_images/*.png; do
  "$CONVERT" "$img" \
    -colorspace RGB \
    -resize 2048x2048 \
    -gravity center \
    -background none \
    -extent 2048x2048 \
    -colorspace sRGB \
    PNG32:"processed/$name.png"
done
```

The `-colorspace RGB` converts to linear before resize, then `-colorspace sRGB` converts back. This compensates for texconv's DXT5 sRGB→linear gamma conversion during compression, preventing darkened colors in-game.

### Pipeline (automated by script)

1. **Preprocess** images: sanitize filenames, upscale to 2048×2048 with transparent padding, fix gamma colorspace
2. **Inject** each image into a base game decal texture template (auto-resizes to 512×512 via texconv DXT5)
3. **Modify** uasset metadata via C# UAssetAPI: set `FolderName` to new path, set `Export.ObjectName` to new name (uses `FName.FromString` — does NOT modify NameMap directly)
4. **Generate** Decals DataTable entries via C# `--add-decals` mode (uses ASEAN-Motor-Club/UAssetAPI fork)
5. **Package** into mod PAK with `mod_pack` binary (V11, mount `../../../`)

### Texture Modification (CRITICAL)

**NEVER use binary patching** to modify texture `.uasset` files. It corrupts non-string bytes and breaks textures (white squares in-game).

**NEVER use `SetNameReference`** on NameMap entries — it corrupts hash integrity and breaks `.uexp` deserialization.

The correct approach uses C# UAssetAPI:

```csharp
// Load the injected texture
var asset = new UAsset(input, EngineVersion.VER_UE5_4, mappings);

// Set FolderName — this is what the engine uses to resolve the texture
asset.FolderName = FString.FromString(newPath);

// Rename export ObjectName — adds NEW FName entry, doesn't corrupt existing
foreach (var export in asset.Exports)
{
    if (export.ObjectName != null && export.ObjectName.Value.Value != newName)
        export.ObjectName = FName.FromString(asset, newName);
}

// Write — preserves existing NameMap entries (no corruption)
asset.Write(output);
```

This preserves hash integrity. Old NameMap entries remain but are harmless unused references.

### Decal Texture Format

- **Source resolution**: **2048×2048** PNG with transparent background and transparent padding for non-square images
- **Injection resolution**: **512×512** (auto-resized by texconv during DXT5 compression)
- **Pixel format**: **PF_DXT5** (BC3_UNORM, compressed with alpha)
- **Colorspace**: Source PNGs must be sRGB. Pipeline converts through linear RGB during resize to prevent gamma darkening
- **Filename requirement**: No spaces, parentheses, or dashes — use underscores only
- **Template**: Any base game decal texture from `out/` (prefers `GeomShape_01/001-circle`)
- uasset metadata must match PAK file path (FolderName + Export.ObjectName via C# UAssetAPI)

### Working Pipeline

```
images/ (498 PNGs, 2048×2048, sanitized filenames)
  → ImageMagick: -colorspace RGB -resize 2048x2048 -gravity center -extent 2048x2048 -colorspace sRGB
  → UE4-DDS-Tools: inject into template .uasset (DXT5, 512×512)
  → C# TexturePathFix: set FolderName + Export.ObjectName
  → C# --add-decals: generate Decals DataTable
  → mod_pack: create PAK file
```

### How the Engine Resolves Textures

Each decal needs a row in `Decals.uasset` with:
- `RowName`: `{Category}_{Name}` (e.g. `Custom_01_Driftweld`)
- `Texture`: SoftObject path to `/Game/Materials/Decal/DecalTextures/{Category}/{Name}`
- `BrushMaterial`: `M_DecalBounds_Test` import reference
- `Flags`: integer (usually 0)
- `Cost`: integer (in-game price)

### C# Tool (for manual DataTable editing)

```bash
cd csharp/CargoExtractor
dotnet run -- --add-decals decal_entries.json Decals.uasset output_dir/
```

`decal_entries.json` format:
```json
{
  "entries": [
    {"row_name": "Custom_01_MyDecal", "folder": "Custom_01", "file": "MyDecal", "cost": 100, "flags": 0}
  ]
}
```

### Decal Compatibility Patches

When two decal mods both override `Decals.uasset`, only one loads. A **compatibility patch** merges both DataTables into a single file so all decals from both mods appear in-game.

#### How It Works

Motor Town loads mod PAKs alphabetically. Each decal mod contains:
- **Textures** at unique paths (`/Game/Materials/Decal/DecalTextures/{Category}/{Name}`)
- **Decals.uasset** at the same path (`MotorTown/Content/DataAsset/Decals.uasset`)

Textures don't conflict (different paths), but `Decals.uasset` does — the last-loaded PAK wins. A compatibility patch creates a single `Decals.uasset` referencing textures from both mods.

#### Pipeline

```bash
# 1. Parse texture paths from both PAKs (extract folder/file pairs)
python3 -c "
import re
pak = open('ModA_P.pak', 'rb').read()
paths = set(m.group(0).decode() for m in re.finditer(rb'DecalTextures/([A-Za-z0-9_]+/[A-Za-z0-9_\- ()]+)', pak))
for p in sorted(paths): print(p)
"

# 2. Generate decal_entries.json for both mods
# Row name format: {Folder}_{File}
# Example: Testun/brand10 → row_name: Testun_brand10, folder: Testun, file: brand10

# 3. Merge entries into one JSON
python3 -c "
import json
a = json.load(open('modA_entries.json'))['entries']
b = json.load(open('modB_entries.json'))['entries']
seen = set()
merged = []
for e in a + b:
    if e['row_name'] not in seen:
        seen.add(e['row_name'])
        merged.append(e)
json.dump({'entries': merged}, open('merged_entries.json', 'w'), indent=2)
print(f'Merged: {len(merged)} entries')
"

# 4. Run C# tool to create merged Decals.uasset — TWO STEPS REQUIRED
# IMPORTANT: Do NOT add all entries at once. UAssetAPI corrupts the file if you
# add too many entries (>~500) in a single pass. Always merge in two steps.

# Step 4a: Add first mod's entries to base game Decals.uasset
cd csharp/CargoExtractor
dotnet run --configuration Release --verbosity quiet -- \
  --add-decals modA_entries.json out/Decals.uasset /tmp/merge_step1/

# Step 4b: Add second mod's entries on top of step 4a output
dotnet run --configuration Release --verbosity quiet -- \
  --add-decals modB_entries.json /tmp/merge_step1/Decals.uasset /tmp/merge_step2/

# Step 4c: Verify the merged file is readable (if this fails, the file is corrupt)
dotnet run --configuration Release --verbosity quiet -- \
  /tmp/merge_step2/Decals.uasset /tmp/verify/

# 5. Build compatibility PAK (Decals.uasset + .uexp only)
mkdir -p pak_root/MotorTown/Content/DataAsset
cp /tmp/merge_step2/Decals.uasset pak_root/MotorTown/Content/DataAsset/
cp /tmp/merge_step2/Decals.uexp pak_root/MotorTown/Content/DataAsset/
cargo build --release --bin mod_pack
target/release/mod_pack pak_root/ CompatPatch_P.pak
```

#### Requirements

- **Base game Decals.uasset** — from `out/Decals.uasset` (extraction pipeline output)
- **Both mods' PAK files** — to parse their texture paths via regex
- **Mappings.usmap** — for C# UAssetAPI DataTable editing
- **Pre-built `mod_pack` binary** — or build with `cargo build --release --bin mod_pack`

#### PAK Structure

A compatibility PAK contains only 2 files:
```
MotorTown/Content/DataAsset/Decals.uasset   # Merged DataTable
MotorTown/Content/DataAsset/Decals.uexp     # Binary export data
```

File is typically <200 KB. The textures remain in their original mod PAKs.

#### Loading Order

The compatibility PAK must load **last** (alphabetically after both mods) to override `Decals.uasset`. Example naming:
- `PatosDecals_P.pak` (original mod)
- `PatosReEnvision_P.pak` (second mod)
- `ZZZ_PatosCompat_P.pak` (compatibility — loads last)

Or merge textures + DataTable into a single combined PAK if you want one file.

#### NixOS Gotchas

- **`libgomp.so.1`** required by texconv DLL for image injection:
  ```bash
  LIBGOMP="/nix/store/bmi5znnqk4kg2grkrhk6py0irc8phf6l-gcc-14.2.1.20250322-lib/lib"
  LD_LIBRARY_PATH="$LIBGOMP" python3 ...
  ```
- **`dotnet` not in PATH** — install via nix: `nix profile install nixpkgs#dotnet-sdk`
- **`mod_pack` dynamic linker** — NixOS can't run generic ELF. Use:
  ```bash
  LD="/nix/store/l0l2ll1lmylczj1ihqn351af2kyp5x19-glibc-2.42-51/lib/ld-linux-x86-64.so.2"
  $LD target/release/mod_pack input_dir/ output.pak
  ```
- **`patch_uasset` binary patching** — DO NOT USE. Corrupts texture files by overwriting bytes outside string sites. Use C# UAssetAPI FolderName approach instead.
- **Python3 path** — nix store path changes between builds. Use `find /nix/store -path "*/python3-3.12*/bin/python3" | head -1` to find it.
- **Texture `FolderName`** — must match DataTable's `PackageName` exactly. The engine resolves textures by FolderName, not by NameMap entries.
- **`SetNameReference` corruption** — modifying NameMap entries directly corrupts hash integrity and breaks `.uexp` deserialization. Use `FName.FromString` instead (safely adds new entries).

#### Example: Merging Pato's Decals + ReEnvision

```bash
# Parse original PAK entries (367 textures across 4 categories)
python3 -c "
import re
from collections import defaultdict
pak = open('PatosDecals_P.pak', 'rb').read()
paths = set(m.group(0).decode() for m in re.finditer(rb'DecalTextures/([A-Za-z0-9_]+/[A-Za-z0-9_\- ()]+)', pak))
entries = [{'row_name': f'{p.split(\"/\")[0]}_{p.split(\"/\")[1]}', 'folder': p.split('/')[0], 'file': p.split('/')[1], 'cost': 100, 'flags': 0} for p in sorted(paths)]
json.dump({'entries': entries}, open('original_entries.json', 'w'), indent=2)
"

# Parse ReEnvision PAK entries (673 textures)
# (same approach)

# Merge + generate Decals.uasset + build PAK
dotnet run -- --add-decals merged.json out/Decals.uasset merged_out/
mod_pack pak_root/ CompatPatch_P.pak
```

### Mod PAK Explorer

```bash
cargo build --release --bin mod_explore  # List/extract mod PAKs
cargo build --release --bin mod_pack     # Create mod PAKs

mod_explore MyMod.pak --list             # List files
mod_explore MyMod.pak --search "decal"   # Search files
mod_pack input_dir/ output.pak           # Pack directory to PAK
```

### Image Tools

Available in the devShell for preparing decal images:

```bash
# Resize to 512x512 (exact, may distort)
convert input.png -resize 512x512! output.png

# Resize + pad to 512x512 square (preserves aspect, transparent padding)
convert input.png -resize 512x512 -gravity center -background none -extent 512x512 output.png

# SVG → PNG
rsvg-convert logo.svg -w 512 -h 512 -o output.png

# Remove white background, make transparent
convert input.png -fuzz 10% -transparent white output.png

# Batch resize a folder
mogrify -resize 512x512! -path prepared/ input/*.png
```

Packages: `imagemagick` (convert/mogrify/identify), `librsvg` (rsvg-convert + SVG delegate for ImageMagick).

### Key Files

- `tools/ue4-dds-tools/` — Vendored [UE4-DDS-Tools](https://github.com/hypermodule/UE4-DDS-Tools/tree/5.5) (MIT) with UE5.5 support
- `tools/ue4-dds-tools/src/directx/libtexconv.so` — Pre-built [Texconv-Custom-DLL](https://github.com/matyalatte/Texconv-Custom-DLL/releases/tag/v0.6.0) for DXT5 compression
- `scripts/create_decal_pack.py` — Main decal pack creator script
- `src/bin/mod_pack.rs` — PAK creator binary
- `src/bin/mod_explore.rs` — PAK reader/explorer binary
- `decal_assets.json` — Config for batch extraction of 423 base game decal textures

### Dependency Management

Python dependencies managed via **uv2nix** (not pip/venv):
- `pyproject.toml` — Project metadata (empty deps, UE4-DDS-Tools is stdlib-only)
- `uv.lock` — Lock file
- `flake.nix` — uv2nix inputs create virtualenv via `pythonSet.mkVirtualEnv()`
- `UV_NO_SYNC=1` in devShell prevents uv from managing the venv (Nix handles it)

C# dependency: ASEAN-Motor-Club fork of UAssetAPI at `/tmp/UAssetAPI-fork` (fix/unversioned-header-serialization branch).

## Gotchas

- **Oodle/libstdc++**: The Rust extractor uses Oodle decompression via `repak`, which `dlopen`s `libstdc++.so.6`. The dev shell includes `gcc.cc.lib` for this, but `LD_LIBRARY_PATH` may need to be set if running outside `nix develop`:
  ```bash
  export LD_LIBRARY_PATH=$(nix develop --command bash -c 'echo $LIBRARY_PATH' | tr : '\n' | xargs -I{} echo {}/lib | tr '\n' :)
  ```
- **Large output**: Parser output is massive. Redirect to file: `> /tmp/parser-output.log 2>&1`
- **`Mappings.usmap` permissions**: Must be owned by `opencode`. If copied from git clone, re-copy: `rm Mappings.usmap && cp /tmp/UAssetAPI-source/.../MotorTown.usmap Mappings.usmap`

## Lint / Typecheck

No lint or typecheck commands defined for this project. Rust is checked by `cargo build`, C# by `dotnet build`, Python has no type checking.

## Project Structure

```
src/main.rs                    # Rust PAK extractor (AES decrypt + Oodle decompress)
csharp/CargoExtractor/         # C# UAsset parser (uses UAssetAPI)
csharp/LevelExtractor/         # C# map/level actor extractor
scripts/aggregate_to_sqlite.py # Python: parsed JSON → normalized SQLite
assets.json                    # List of 264 asset paths to extract
blueprint_assets.json          # Blueprint variant paths for weight aggregation
flake.nix                      # Nix dev environment + apps
```
