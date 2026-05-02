# AGENTS.md

> **⛔ NEVER restart the Motor Town game server (`systemctl restart motortown-server` or similar). It is a LIVE server with active players. Only the user may restart it.**

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

Or run all steps at once for a new game version:
```bash
nix develop --command bash -c 'scripts/new-version.sh v0.7.19 v0.7.19.pak'
```

## Required Files

- **`MotorTown-Windows.pak`** — game PAK file (symlinked to versioned PAK, e.g. `v0.7.18.pak`)
- **`.env`** — AES key (`KEY=0x...`), gitignored
- **`Mappings.usmap`** — UE5 type mappings, gitignored. Versioned per game version in `versions/<version>/Mappings.usmap`, symlinked at repo root. Pull from Windows: `scp freeman@100.85.236.98:'D:/SteamLibrary/steamapps/common/Motor Town/MotorTown/Binaries/Win64/ue4ss/MotorTown-5.5.4-0+UE5-unknown.usmap' Mappings.usmap`
- **UAssetAPI** — C# dependency, included as a git submodule at `csharp/UAssetAPI` (fork: `ASEAN-Motor-Club/UAssetAPI`). Initialize with:
  ```bash
  git submodule update --init
  ```

## Intake Pack Creation

Create intake/supercharger mod PAKs from a JSON config:

```bash
nix develop --command bash -c '
python3 scripts/create_intakepack.py --config mods/police-sc/intake_entries.json --output MySC_P.pak
'
```

Or using the mod management CLI:

```bash
nix develop --command bash -c 'python3 scripts/mods.py build police-sc'
```

### How It Works

Unlike tire mods, intake parts have **no separate physics DataAsset** — all tuning (Slope, BaseRPMRatio, IntakeSpeedEfficencyMultiplier) is inline in the VehicleParts row. The build pipeline only modifies `VehicleParts0`.

1. **Clone** an existing Intake row from VehicleParts0 via `--add-rows` with `template_row_match: {"PartType": "*Intake*"}`
2. **Patch** Intake sub-struct fields via dot-path notation (`Intake.Slope`, `Intake.BaseRPMRatio`, `Intake.IntakeSpeedEfficencyMultiplier`)
3. **Package** into mod PAK with `mod_pack` binary

### Intake Tuning Fields

| Field | Effect | Supercharger feel |
|-------|--------|-------------------|
| `Slope` | Torque curve slope (higher = more torque bias) | 0.05–0.15 (positive for power) |
| `BaseRPMRatio` | RPM ratio where effect begins (lower = earlier) | 0.1–0.3 (instant response) |
| `IntakeSpeedEfficencyMultiplier` | Overall HP multiplier | 2.0–2.5+ (high HP) |

### Vanilla Game Values (v0.7.18+1)

| Row | Slope | BaseRPMRatio | EfficiencyMult |
|-----|-------|-------------|----------------|
| Intake Row 201 | 0.1 | 0.7 | 1.5 |
| Intake Row 202 | -0.1 | 0.8 | 0.7 |
| Turbo Stock (Small) | TorqueMult=1.1, TurbineWeight=30 | — | — |
| Turbo Stage1 (Small) | TorqueMult=1.2, TurbineWeight=100 | — | — |

### Compat-Mod Support

```bash
# Build compatible with MoreTuning + AMC Tires
nix develop --command bash -c '
python3 scripts/create_intakepack.py \
  --config mods/police-sc/intake_entries.json \
  --output zzz_AMC_PDParts_MoreTuningCompat_P.pak \
  --compat-mod path/to/zzz_ASEAN_PoliceTyres_v0.2.0_MoreTuningCompat_P.pak
'
```

## Decal Pack Creation

Create decal mod PAKs from images in one command:

```bash
nix develop --command bash -c '
python3 scripts/create_decal_pack.py --input images/ --output MyPack_P.pak
'
```

Or using the mod management CLI:

```bash
nix develop --command bash -c 'python3 scripts/mods.py build custom-decals --input images/'
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--input, -i` | (required) | Directory of images (PNG/TGA/BMP/JPG) |
| `--output, -o` | auto from `mod.json` | Output .pak path |
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

The C# tool provides 5 generic operations driven by JSON configs:

```bash
cd csharp/UAssetTool

# Add rows to any DataTable (clone or construct mode)
dotnet run -- --add-rows config.json template.uasset output_dir/

# Patch existing DataTable rows in-place by RowName
dotnet run -- --patch-rows config.json template.uasset output_dir/

# Clone and rename any asset with property patches
dotnet run -- --clone-asset config.json template.uasset output_dir/

# Patch CDO properties and arrays in blueprint exports
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
- `scripts/mods.py` — Mod management CLI (build, list, show)
- `scripts/modbase.py` — Shared ModBuilder base class + mod.json utilities
- `src/bin/mod_pack.rs` — PAK creator binary
- `src/bin/mod_explore.rs` — PAK reader/explorer binary
- `decal_assets.json` — Config for batch extraction of 423 base game decal textures
- `mods/truck-horn/horn_patch.json` — Config for patching vehicle CDO HornSound property

### Dependency Management

Python dependencies managed via **uv2nix** (not pip/venv):
- `pyproject.toml` — Project metadata (empty deps, UE4-DDS-Tools is stdlib-only)
- `uv.lock` — Lock file
- `flake.nix` — uv2nix inputs create virtualenv via `pythonSet.mkVirtualEnv()`
- `UV_NO_SYNC=1` in devShell prevents uv from managing the venv (Nix handles it)

C# dependency: ASEAN-Motor-Club fork of UAssetAPI at `/tmp/UAssetAPI-fork` (fix/unversioned-header-serialization branch).

## Game Versioning

When a new Motor Town update drops, the game PAK changes and all mods need rebuilding. The system uses **git tags + worktrees + a data archive** to manage multiple game versions in parallel.

### Quick Reference: New Game Version

**Step 1 — Download PAK from Windows:**
```bash
scp freeman@100.85.236.98:'D:/SteamLibrary/steamapps/common/Motor Town/MotorTown/Content/Paks/MotorTown-Windows.pak' v0.7.19.pak
```

**Step 2 — Run the pipeline (one command):**
```bash
nix develop --command bash -c 'scripts/new-version.sh v0.7.19 v0.7.19.pak'
```

This single command archives the old version, extracts the new PAK, archives the new data, git tags, and creates a worktree for the old version.

**Step 3 — Rebuild mods:**
```bash
nix develop --command bash -c '
python3 scripts/mods.py build police-tyres
python3 scripts/mods.py build schedule-i
'
```

Or using individual scripts directly:
```bash
nix develop --command bash -c '
python3 scripts/create_tirepack.py --config mods/police-tyres/tire_entries.json --output mods/police-tyres/builds/zzz_ASEAN_PoliceTyres_v0.2.0_0.7.19_P.pak
python3 scripts/create_cargopack.py --config mods/schedule-i/cargo_entries.json --recipes mods/schedule-i/recipe_entries.json --output mods/schedule-i/builds/Schedule_I_v0.3.0_0.7.19_P.pak
'
```

### Full Workflow Detail

#### Obtaining the PAK

The game PAK lives on the Windows machine at:
```
D:\SteamLibrary\steamapps\common\Motor Town\MotorTown\Content\Paks\MotorTown-Windows.pak
```

Download via SCP, naming it after the game version:
```bash
scp freeman@100.85.236.98:'D:/SteamLibrary/steamapps/common/Motor Town/MotorTown/Content/Paks/MotorTown-Windows.pak' v0.7.19.pak
```

Place the PAK in the repo root. The filename should be `<version>.pak` (e.g., `v0.7.19.pak`). The script symlinks it as `MotorTown-Windows.pak` — no 2.6GB copy.

#### What `new-version.sh` Does

| Step | Action | Details |
|------|--------|---------|
| 1 | Archive current | Saves `out/`, `motortown.db`, `*_parsed.json` → `versions/<current>/` |
| 2 | Register new PAK | Updates `game_versions.json`, symlinks PAK as `MotorTown-Windows.pak` |
| 3 | Extract assets | Rust extractor (AES decrypt + Oodle decompress) |
| 4 | Parse .uasset files | C# UAssetTool batch parser |
| 5 | Aggregate to SQLite | Python `aggregate_to_sqlite.py` |
| 6 | Archive + tag | Saves new data, git commits + tags, creates worktree for old version |

#### Building Mods Against Old Versions

**Option A — Worktree (parallel, recommended):**
```bash
cd ../mt-v0.7.18
python3 scripts/mods.py build police-tyres
```

**Option B — Switch in main repo:**
```bash
scripts/mt-version.sh switch v0.7.18
python3 scripts/mods.py build police-tyres
scripts/mt-version.sh switch v0.7.19  # switch back
```

### Version Management CLI: `scripts/mt-version.sh`

```bash
scripts/mt-version.sh status          # current version + archived versions
scripts/mt-version.sh list            # all known versions with PAK details
scripts/mt-version.sh archive v0.7.18 # archive current extracted data
scripts/mt-version.sh tag v0.7.18     # git commit + tag
scripts/mt-version.sh switch v0.7.17  # switch active version (symlinks data)
scripts/mt-version.sh worktree v0.7.17 # create parallel worktree
scripts/mt-version.sh diff v0.7.17 v0.7.18 # compare two versions
```

### Artifacts by Category

| Type | Examples | Tracked? |
|------|----------|----------|
| **Game data** (from PAK) | `out/`, `motortown.db`, `*_parsed.json` | gitignored, archived in `versions/` |
| **Mod definitions** | `mods/*/mod.json`, `mods/*/*.json` | tracked |
| **Mod scripts** | `scripts/create_*.py`, `scripts/modbase.py`, `scripts/mods.py` | tracked |
| **Mod outputs** | `mods/*/builds/*_P.pak` | gitignored |
| **Version metadata** | `game_versions.json` | tracked |

### Mod Management CLI: `scripts/mods.py`

```bash
python3 scripts/mods.py list                    # List all mods
python3 scripts/mods.py build police-tyres     # Build a mod (auto-resolves game version)
python3 scripts/mods.py build schedule-i        # Build another mod
python3 scripts/mods.py show police-tyres       # Show mod details
python3 scripts/mods.py game-version            # Show active game version
```

Each mod is defined by `mods/<name>/mod.json`:

```json
{
  "name": "police-tyres",
  "display_name": "ASEAN_PoliceTyres",
  "version": "0.1.9",
  "type": "tire",
  "prefix": "zzz_",
  "script": "scripts/create_tirepack.py",
  "configs": ["tire_entries.json"],
  "compat_suffix": "MoreTuningCompat",
  "extra_args": {}
}
```

Output PAK naming: `{prefix}{display_name}_v{mod_version}_{game_version}[_{compat_suffix}]_P.pak`

Example: `zzz_ASEAN_PoliceTyres_v0.1.9_0.7.18+1_P.pak`

Built PAKs go to `mods/<name>/builds/` — gitignored but versioned in the filename.

### Directory Layout

```
mods/                         # Mod definitions + outputs
  police-tyres/
    mod.json                  # Mod identity (name, version, type, script)
    tire_entries.json          # Tire physics + part config
    builds/                   # Built PAK outputs (gitignored)
  schedule-i/
    mod.json
    cargo_entries.json
    recipe_entries.json
    builds/
  truck-horn/
    mod.json
    horn_patch.json
    builds/
versions/                    # Archived game data (gitignored)
  v0.7.18/
    out/                     # Extracted .uasset templates
    motortown.db             # SQLite database
    *_parsed.json            # Parsed game data
    Mappings.usmap           # UE5 type mappings (version-specific)
    pak.sha256               # PAK file hash
Mappings.usmap               # Symlink → versions/<active>/Mappings.usmap
v0.7.18.pak                  # Game PAK (gitignored, symlinked as MotorTown-Windows.pak)
game_versions.json           # Version manifest (tracked)
scripts/mt-version.sh        # Version management CLI
scripts/new-version.sh       # New version pipeline (one command)
scripts/mods.py              # Mod management CLI (build, list, show)
```

### Tips

- Mod PAK filenames include both mod version and game version: `zzz_ASEAN_PoliceTyres_v0.1.9_0.7.18+1_P.pak`
- Use `mods.py build <name>` for consistent, versioned output paths
- Each mod's output PAK is independent — rebuilding one doesn't affect others
- Worktrees share the same git history; any commit is visible from all worktrees
- The `versions/` directory uses ~1-2GB per version (out/ + db + parsed JSON)
- Use `mt-version diff` to see what changed between game versions (row counts, new/removed assets)

## Gotchas

- **Blueprint `_C` suffix**: UE5 BlueprintGeneratedClass exports **must** retain the `_C` suffix (e.g. `Money_C`, `Default__Money_C`). The `--clone-asset` autodetection can pick up the full class name (`SmallBox_C`) instead of the base name (`SmallBox`), causing replacements that strip the suffix. **Always pass `old_name` explicitly** in clone configs to prevent this. Without `_C`, the engine gets a null pointer (`EXCEPTION_ACCESS_VIOLATION reading address 0x...0110`).
- **Source-only delivery points**: Delivery points like `LiveFishSupplier` that only have `OutputCargos` (sources) **cannot** be used as sinks. Adding `InputCargos` to a source-only Warehouse blueprint crashes the game when the player interacts with it. Check `out/*_parsed.json` CDO properties before adding recipes.
- **`cargo_type: None` for modded cargo**: Use `cargo_type: "None"` for all modded cargos to prevent unwanted wildcard demand matching. `SmallPackage` causes modded cargo to appear at Supermarkets and Warehouses (wildcard `DemandConfig`). `None` ensures cargo only appears at delivery points you explicitly configure. Despite earlier concerns, `"None"` serializes correctly via `set_enum`.
- **Blueprint CDO schema resolution**: When patching blueprint CDOs (e.g. vehicle blueprints like `Jemusi.uasset`), UAssetAPI needs the **parent blueprint** (e.g. `MTVehicleBaseBP.uasset`) in the same directory to resolve the unversioned property schema. Without it, CDO reparse fails with `"Failed to find a valid property for schema index N in the class X_C"`. Copy the parent `.uasset` + `.uexp` alongside the target before running `--patch-cdo-arrays`.
- **Inherited CDO properties**: Vehicle CDOs only serialize properties that **differ from the parent default**. If a property like `HornSound` is inherited (same as parent), it won't exist in the CDO data. Use `set_or_create_import_ref` (not `set_import_ref`) to create the property if missing.
- **DataTable map property types**: When adding entries to DataTable maps (e.g. `Parts` in vehicle rows), the map values are **NamePropertyData** (FName references), NOT StrPropertyData (FString). The parsed JSON shows them as plain strings, but UAssetAPI internally stores them as FName. Constructing StrPropertyData values from scratch corrupts unversioned header serialization. Always clone from existing map entries and modify the clone's `.Value` field. Debug-log actual C# types with `kvp.Key.GetType().Name` / `kvp.Value.GetType().Name` before cloning.
- **VehicleTypeFlags vs bIsBusable**: Setting `VehicleTypeFlags: 16` (bus flag) on a non-bus vehicle may cause unintended NPC spawning or delivery filtering behavior even without a license equipped. The base Bongo van has `bIsBusable: true` with `VehicleTypeFlags: 0`. Safer to keep flags at 0 and only set the boolean + add the part slot.
- **Oodle/libstdc++**: The Rust extractor uses Oodle decompression via `repak`, which `dlopen`s `libstdc++.so.6`. The dev shell includes `gcc.cc.lib` for this, but `LD_LIBRARY_PATH` may need to be set if running outside `nix develop`:
  ```bash
  export LD_LIBRARY_PATH=$(nix develop --command bash -c 'echo $LIBRARY_PATH' | tr : '\n' | xargs -I{} echo {}/lib | tr '\n' :)
  ```
- **Large output**: Parser output is massive. Redirect to file: `> /tmp/parser-output.log 2>&1`
- **`Mappings.usmap` permissions**: Must be owned by `opencode`. If copied from submodule, re-copy: `rm Mappings.usmap && cp csharp/UAssetAPI/UAssetAPI.Tests/TestAssets/TestJson/MotorTown.usmap Mappings.usmap`. Mappings.usmap is now versioned — the root symlink points to `versions/<active_version>/Mappings.usmap`.
- **CDO imports for new blueprint discovery**: When adding new cargo (or any blueprint-based) rows to a DataTable via `set_import_ref`, you **must** set `"add_cdo_import": true` in the patch config. This creates a `Default__*_C` CDO import (with `ClassPkg=packagePath`, `Class=assetName_C`) that forces the engine to load packages at new paths. Without it, new blueprints are silently ignored — only overrides of existing paths work. The base game's Cargos DataTable has 3 imports per blueprint: Package, BlueprintGeneratedClass, and `Default__*_C` CDO.
- **Blueprint PAK path must match the game's original path exactly**: Variant vehicle blueprints (e.g. `Zydro_Police`) are stored in the **base model's folder** (e.g. `Cars/Models/Zydro/`), NOT in a folder matching the variant name. If you stage `Zydro_Police.uasset` at `Cars/Models/Zydro_Police/Zydro_Police.uasset`, the game won't find it and will load the unmodded original instead. Always verify the original path in the base game's PAK (`MotorTown/Content/Cars/Models/<BaseModel>/<VariantName>.uasset`). Use the `blueprint_folder` field in mod configs to override the staging folder when it differs from the blueprint file name.

## Authoritative Modding Resources

- https://github.com/Dmgvol/UE_Modding/
- https://github.com/donaldwuid/unreal_source_explained/
- https://tempo-organization.github.io/Unreal-Modding-Guides/

## Lint / Typecheck

No lint or typecheck commands defined for this project. Rust is checked by `cargo build`, C# by `dotnet build`, Python has no type checking.

## Project Structure

```
src/main.rs                    # Rust PAK extractor (AES decrypt + Oodle decompress)
csharp/UAssetTool/            # C# generic UAsset SDK (6 operations: --add-rows, --patch-rows, --clone-asset, --patch-cdo-arrays, --patch-export-props, --patch-named-exports, --dump)
csharp/LevelExtractor/         # C# map/level actor extractor
scripts/aggregate_to_sqlite.py # Python: parsed JSON → normalized SQLite
scripts/mods.py               # Mod management CLI (build, list, show)
scripts/modbase.py             # Shared ModBuilder base class + mod.json utilities
scripts/create_tirepack.py    # Tire mod builder
scripts/create_cargopack.py   # Cargo mod builder
scripts/create_decal_pack.py  # Decal mod builder
scripts/create_font_mod.py    # Font replacement mod builder
scripts/create_vehicle_mod.py # Vehicle mod builder (AWD conversion, blueprint patching)
mods/                         # Mod definitions (mod.json + configs)
assets.json                    # List of 264 asset paths to extract
blueprint_assets.json          # Blueprint variant paths for weight aggregation
flake.nix                      # Nix dev environment + apps
```
