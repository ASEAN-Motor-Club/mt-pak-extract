# MotorTown Mod Toolchain

Extract, parse, and create mods for MotorTown's Unreal Engine 5.5 PAK files. The pipeline covers asset extraction, data aggregation, and mod PAK creation for tires, cargo, decals, fonts, and more.

## Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled
- `MotorTown-Windows.pak` file (full client PAK)
- `Mappings.usmap` file (generated using [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) with the Dump Usmap feature)
- `.env` file with AES decryption key

### Setup

1. Place game files in the project root:
   ```
   MotorTown-Windows.pak           # Full client PAK from game installation
   Mappings.usmap                  # Generated via UE4SS
   ```
   
   > **Note:** The PAK file can be found at:
   > `C:\Program Files (x86)\Steam\steamapps\common\MotorTown\MotorTown\Content\Paks\MotorTown-Windows.pak`
   >
   > You can also use `MotorTown-WindowsServer.pak` (smaller, server-only data) if you don't need vehicle blueprint weights.

2. Create `.env` with the AES key:
   ```
   KEY=0xYOUR_AES_KEY_HERE
   ```

## Quick Start

**Full pipeline** (extract → parse → aggregate):
```bash
nix run .#extract      # Extract & parse assets
nix run .#aggregate    # Aggregate to database & export SQL
```

**Output**: `motortown.db` (SQLite) and `motortown_data.sql` (8,423 lines)

## Usage

### 1. Extract Assets from PAK

Extract all assets listed in `assets.json`:

```bash
nix run .#extract
```

Output: `out/` directory with `.uasset`, `.uexp`, and `*_parsed.json` files.

### 2. Aggregate to Database

Transform JSON into normalized SQLite database:

```bash
nix run .#aggregate
```

**Output:**
- `motortown.db` - SQLite database
- Summary stats printed to console

**Database Contents:**
- Vehicles with default parts, tags, and chassis weights
- Vehicle parts (engines, transmissions, wheels, cargo beds, etc.)
- Cargos with aggregated weights from blueprints
- Cargo bed specifications (dimensions, volume, capacity)
- Delivery points with production configurations
- Production configs with input/output cargo recipes
- Vehicle-part relationships
- Views for common queries (weights, cargo space, etc.)

### 3. Export to SQL

```bash
sqlite3 motortown.db .dump > motortown_data.sql
```

### Query Examples

```bash
# Find cheap vehicles
sqlite3 motortown.db "SELECT name, cost FROM vehicles WHERE cost < 15000 ORDER BY cost LIMIT 5;"

# Heaviest cargos (aggregated from blueprint components)
sqlite3 motortown.db "SELECT id, actual_weight_kg FROM cargos_with_weights WHERE actual_weight_kg > 0 ORDER BY actual_weight_kg DESC LIMIT 10;"

# Vehicles with their default engines
sqlite3 motortown.db "SELECT v.name, vp.id as engine, vp.mass_kg FROM vehicles_with_engines v JOIN vehicle_parts vp ON v.engine_id = vp.id LIMIT 5;"
```

## Mod Creation

Create and build mod PAKs using the unified mod management CLI:

```bash
# List all mods
python3 scripts/mods.py list

# Build a mod (auto-resolves game version + output path)
python3 scripts/mods.py build police-tyres
python3 scripts/mods.py build schedule-i

# Show mod details
python3 scripts/mods.py show police-tyres
```

Each mod is defined in `mods/<name>/mod.json` with its own version, build script, and config files:

```json
{
  "name": "police-tyres",
  "display_name": "ASEAN_PoliceTyres",
  "version": "0.1.9",
  "type": "tire",
  "prefix": "zzz_",
  "script": "scripts/create_tirepack.py",
  "configs": ["tire_entries.json"],
  "compat_suffix": "MoreTuningCompat"
}
```

Output PAKs are versioned: `zzz_ASEAN_PoliceTyres_v0.1.9_0.7.18+1_P.pak`

### Mod Types

| Type | Script | Description |
|------|--------|-------------|
| **Tire** | `scripts/create_tirepack.py` | Custom tire physics + VehicleParts rows |
| **Cargo** | `scripts/create_cargopack.py` | New cargo types, blueprints, delivery recipes |
| **Decal** | `scripts/create_decal_pack.py` | Custom decal textures from images |
| **Font** | `scripts/create_font_mod.py` | Font replacement PAKs |

### Decal Pack Creation

Create decal mod PAKs from images:

```bash
python3 scripts/create_decal_pack.py --input logos/ --output MyPack_P.pak
```

Each image becomes a decal named after its filename. Images are automatically resized to 512×512 and compressed to DXT5.

### Preparing Images

```bash
# Resize + pad to 512x512 (preserves aspect, transparent padding)
convert input.png -resize 512x512 -gravity center -background none -extent 512x512 prepared.png

# SVG → PNG
rsvg-convert logo.svg -w 512 -h 512 -o logo.png

# Batch resize a folder
mogrify -resize 512x512! -path prepared/ input/*.png
```

### Mod PAK Tools

```bash
# List files in a mod PAK
mod_explore MyMod.pak --list

# Search for files
mod_explore MyMod.pak --search "decal"

# Extract all files from a mod PAK
mod_explore MyMod.pak --extract-all

# Create a mod PAK from a directory
mod_pack input_dir/ output.pak
```

## How It Works

1. **Rust extractor** (`src/main.rs`) decrypts PAK with AES, decompresses with Oodle, extracts `.uasset`/`.uexp` files
2. **C# parser** (`csharp/UAssetTool/`) uses UAssetAPI with `.usmap` to deserialize UE5.5 properties into JSON
3. **Python aggregator** (`scripts/aggregate_to_sqlite.py`) normalizes JSON into SQLite with proper relationships and computed values
4. **Python mod builders** (`scripts/create_*.py`) orchestrate asset cloning, patching, and PAK packaging via the C# tool
5. **Rust mod_pack/mod_explore** create and inspect UE5 V11 mod PAKs

## Project Structure

```
├── src/main.rs                      # Rust PAK extractor
├── src/bin/mod_pack.rs              # Rust mod PAK creator
├── src/bin/mod_explore.rs           # Rust mod PAK reader/explorer
├── csharp/UAssetTool/              # C# generic UAsset SDK (5 operations)
├── scripts/
│   ├── aggregate_to_sqlite.py      # Python: parsed JSON → SQLite
│   ├── mods.py                     # Mod management CLI (build, list, show)
│   ├── modbase.py                  # Shared ModBuilder base + mod.json utilities
│   ├── create_tirepack.py         # Tire mod builder
│   ├── create_cargopack.py        # Cargo mod builder
│   ├── create_decal_pack.py       # Decal mod builder
│   └── create_font_mod.py         # Font replacement mod builder
├── mods/                           # Mod definitions (mod.json + configs)
├── tools/
│   └── ue4-dds-tools/              # Vendored UE4-DDS-Tools (texture injection)
├── assets.json                      # Config: assets to extract
├── decal_assets.json                # Config: decal texture assets
├── game_versions.json              # Game version manifest
├── pyproject.toml                   # Python project (uv2nix)
├── uv.lock                          # Python lock file
├── flake.nix                        # Nix build/dev environment
└── out/                             # Extracted & parsed data
```

## Data Quality Notes

## Game Versioning

When a new Motor Town update drops, the game PAK changes and all mods need rebuilding.

```bash
# Download new PAK from Windows
scp freeman@100.85.236.98:'D:/SteamLibrary/steamapps/common/Motor Town/MotorTown/Content/Paks/MotorTown-Windows.pak' v0.7.19.pak

# Run full pipeline: archive old → extract new → parse → aggregate
nix develop --command bash -c 'scripts/new-version.sh v0.7.19 v0.7.19.pak'

# Rebuild all mods
nix develop --command bash -c 'python3 scripts/mods.py build police-tyres'
nix develop --command bash -c 'python3 scripts/mods.py build schedule-i'
```

### Version Management CLI

```bash
scripts/mt-version.sh status          # Current version + data state
scripts/mt-version.sh switch v0.7.18  # Switch active version
scripts/mt-version.sh list            # All known versions
scripts/mt-version.sh diff v0.7.17 v0.7.18  # Compare versions
```

## License

MIT
