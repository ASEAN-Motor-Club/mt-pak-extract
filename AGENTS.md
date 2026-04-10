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
nix develop --command bash -c 'cd csharp/UAssetTool && dotnet run --configuration Release --verbosity quiet -- --batch'

# 3. Aggregate to SQLite (Python)
nix develop --command bash -c 'python3 scripts/aggregate_to_sqlite.py'
```

Output: `motortown.db` (SQLite), `out/*_parsed.json`.

## Required Files

- **`MotorTown-Windows.pak`** — game PAK file (2.9 GB, already in repo root)
- **`.env`** — AES key (`KEY=0x...`), gitignored
- **`Mappings.usmap`** — UE5 type mappings, gitignored. Source: `csharp/UAssetAPI/UAssetAPI.Tests/TestAssets/TestJson/MotorTown.usmap`
- **UAssetAPI** — C# dependency, included as a git submodule at `csharp/UAssetAPI` (fork: `ASEAN-Motor-Club/UAssetAPI`). Initialize with:
  ```bash
  git submodule update --init
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

### Pipeline (automated by script)

1. **Inject** each image into a base game decal texture template (auto-resizes to 512×512 via texconv)
2. **Patch** uasset internal metadata (asset path, name, hashes from template)
3. **Generate** Decals DataTable entries via C# `--add-rows` construct mode (uses ASEAN-Motor-Club/UAssetAPI fork)
4. **Package** into mod PAK with `mod_pack` binary (V11, mount `../../../`)

### Decal Texture Format

- Resolution: **512×512** (auto-resized if different)
- Pixel format: **PF_DXT5** (BC3_UNORM, compressed with alpha)
- Template: Any base game decal texture from `out/` (prefers `GeomShape_01/001-circle`)
- uasset metadata must match PAK file path (script patches automatically)

### Decals DataTable

Each decal needs a row in `Decals.uasset` with:
- `RowName`: `{Category}_{Name}` (e.g. `Custom_01_Driftweld`)
- `Texture`: SoftObject path to `/Game/Materials/Decal/DecalTextures/{Category}/{Name}`
- `BrushMaterial`: `M_DecalBounds_Test` import reference
- `Flags`: integer (usually 0)
- `Cost`: integer (in-game price)

### C# UAssetTool (generic UAsset SDK)

The C# tool provides 3 generic operations driven by JSON configs:

```bash
cd csharp/UAssetTool

# Add rows to any DataTable (clone or construct mode)
dotnet run -- --add-rows config.json template.uasset output_dir/

# Clone and rename any asset with property patches
dotnet run -- --clone-asset config.json template.uasset output_dir/

# Patch arrays in blueprint CDO exports
dotnet run -- --patch-cdo-arrays config.json template.uasset output_dir/

# Diagnostic: dump asset structure
dotnet run -- --dump path/to/asset.uasset
```

Python mod builder scripts generate the JSON configs and call these operations.
See `scripts/create_tirepack.py`, `scripts/create_cargopack.py`, `scripts/create_decal_pack.py`.

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

- **Blueprint `_C` suffix**: UE5 BlueprintGeneratedClass exports **must** retain the `_C` suffix (e.g. `Money_C`, `Default__Money_C`). The `--clone-asset` autodetection can pick up the full class name (`SmallBox_C`) instead of the base name (`SmallBox`), causing replacements that strip the suffix. **Always pass `old_name` explicitly** in clone configs to prevent this. Without `_C`, the engine gets a null pointer (`EXCEPTION_ACCESS_VIOLATION reading address 0x...0110`).
- **Source-only delivery points**: Delivery points like `LiveFishSupplier` that only have `OutputCargos` (sources) **cannot** be used as sinks. Adding `InputCargos` to a source-only Warehouse blueprint crashes the game when the player interacts with it. Check `out/*_parsed.json` CDO properties before adding recipes.
- **`cargo_type: None` crashes**: Setting `CargoType` enum to `"None"` via `set_enum` crashes UE5's ByteProperty serializer. Use a valid type like `SmallPackage` or `LargePackage`. To avoid Resident wildcard demand (which matches `SmallPackage`), use `LargePackage` — no delivery point has a wildcard DemandConfig for it.
- **Oodle/libstdc++**: The Rust extractor uses Oodle decompression via `repak`, which `dlopen`s `libstdc++.so.6`. The dev shell includes `gcc.cc.lib` for this, but `LD_LIBRARY_PATH` may need to be set if running outside `nix develop`:
  ```bash
  export LD_LIBRARY_PATH=$(nix develop --command bash -c 'echo $LIBRARY_PATH' | tr : '\n' | xargs -I{} echo {}/lib | tr '\n' :)
  ```
- **Large output**: Parser output is massive. Redirect to file: `> /tmp/parser-output.log 2>&1`
- **`Mappings.usmap` permissions**: Must be owned by `opencode`. If copied from submodule, re-copy: `rm Mappings.usmap && cp csharp/UAssetAPI/UAssetAPI.Tests/TestAssets/TestJson/MotorTown.usmap Mappings.usmap`

## Lint / Typecheck

No lint or typecheck commands defined for this project. Rust is checked by `cargo build`, C# by `dotnet build`, Python has no type checking.

## Project Structure

```
src/main.rs                    # Rust PAK extractor (AES decrypt + Oodle decompress)
csharp/UAssetTool/            # C# generic UAsset SDK (3 operations: --add-rows, --clone-asset, --patch-cdo-arrays)
csharp/LevelExtractor/         # C# map/level actor extractor
scripts/aggregate_to_sqlite.py # Python: parsed JSON → normalized SQLite
assets.json                    # List of 264 asset paths to extract
blueprint_assets.json          # Blueprint variant paths for weight aggregation
flake.nix                      # Nix dev environment + apps
```
