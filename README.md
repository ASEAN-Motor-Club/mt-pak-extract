# MotorTown PAK Asset Extractor

Extract and parse game data from MotorTown's Unreal Engine 5.5 PAK files, then aggregate into a normalized SQLite database.

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

## Decal Pack Creation

Create mod PAKs that add custom decal textures to the in-game decal selection.

```bash
# Quick: one command from images to mod PAK
nix develop --command bash -c '
python3 scripts/create_decal_pack.py --input logos/ --output MyPack_P.pak
'
```

Each image in `logos/` becomes a decal named after its filename. Images are automatically resized to 512×512 and compressed to DXT5.

### Options

```
--input, -i      Directory of images (PNG/TGA/BMP/JPG) [required]
--output, -o     Output .pak file path [required]
--category, -c   Category folder name (default: Custom)
--cost           In-game price (default: 100)
--template, -t   Override template texture (auto-detects from out/)
--decals, -d     Override Decals.uasset (auto-detects from out/)
```

### How It Works

1. **Extract** a base game decal texture as template (512×512 PF_DXT5)
2. **Inject** each image into the template using [UE4-DDS-Tools](https://github.com/hypermodule/UE4-DDS-Tools/tree/5.5) (auto-resizes to 512×512, compresses to DXT5)
3. **Patch** uasset internal metadata (asset path, name, hashes)
4. **Generate** Decals DataTable entries — adds a row per decal with texture reference, material, cost
5. **Package** into a UE5 V11 mod PAK with mount point `../../../`

### PAK Structure

```
MyPack_P.pak
└── MotorTown/
    └── Content/
        ├── DataAsset/
        │   ├── Decals.uasset      # DataTable with decal entries
        │   └── Decals.uexp
        └── Materials/
            └── Decal/
                └── DecalTextures/
                    └── Custom_01/
                        ├── Driftweld.uasset  # Texture asset
                        └── Driftweld.uexp    # Texture pixel data (512×512 DXT5)
```

### Mod PAK Tools

```bash
# List files in a mod PAK
nix develop --command bash -c 'cargo build --release --bin mod_explore && LD_LIBRARY_PATH=$(echo $LIBRARY_PATH | tr : \n | xargs -I{} echo {}/lib | tr \n :) ./target/release/mod_explore MyMod.pak --list'

# Search for files in a mod PAK
./target/release/mod_explore MyMod.pak --search "decal"

# Extract all files from a mod PAK
./target/release/mod_explore MyMod.pak --extract-all

# Create a mod PAK from a directory
./target/release/mod_pack input_dir/ output.pak
```

### Decal Assets (423 base game decals)

```bash
# Extract all base game decal textures
nix develop --command bash -c 'cargo run --release --quiet -- --config decal_assets.json'
```

Extracts the Decals DataTable + all 423 decal texture assets (512×512 PF_DXT5) from the game PAK.

## Advanced Usage

### Manual Commands

Enter the development shell:
```bash
nix develop
```

**Search for assets:**
```bash
cargo run -- --search "Delivery"  # Find cargo blueprints
cargo run -- --list               # List all DataAssets
```

**Extract specific asset:**
```bash
cargo run -- "MotorTown/Content/DataAsset/Cargos"
cargo run -- "MotorTown/Content/Objects/Mission/Delivery/SmallBox"
```

**Parse single file:**
```bash
cd csharp/CargoExtractor
dotnet run -- --batch              # Parse all in out/
dotnet run -- ../../Cargos.uasset  # Parse single file
```

## Output Structure

```
out/
├── manifest.json                  # List of extracted assets
├── Cargos_parsed.json            # Cargo data (84 rows)
├── Vehicles_parsed.json          # Vehicle data (162 rows)
├── Engines_parsed.json           # Engine parts (34 rows)
├── SmallBox_parsed.json          # Cargo blueprint (weight: 5kg)
└── ...

motortown.db                       # SQLite database
motortown_data.sql                 # SQL dump
```

## Database Schema

**Core Tables:**
- `vehicles` - Vehicle metadata (name, cost, type, blueprint path)
- `vehicle_parts` - Part metadata (cost, mass, type, asset paths)
- `cargos` - Cargo metadata (type, volume, payment rates)
- `delivery_points` - Delivery locations (Supermarket, Factories, Farms, Mines)
- `production_configs` - Production recipes (inputs, outputs, timing)
- `production_inputs` / `production_outputs` - Input/output cargos for production

**Relationships:**
- `vehicle_default_parts` - Vehicle → Part mappings (slot-based)
- `vehicle_tags` - Vehicle GameplayTags
- `cargo_space_types` - Cargo compatible space types
- `part_compatible_types` - Part → Vehicle type compatibility

**Aggregation:**
- `cargo_weights` - Total weight per cargo (summed from blueprint components)
- `cargo_weight_components` - Individual component masses
- `vehicle_weights` - Chassis mass from vehicle blueprints
- `cargo_bed_specs` - Cargo bed dimensions and capacity

**Views:**
- `cargos_with_weights` - Cargos with actual weights (blueprint or fallback)
- `active_cargos` - Valid, non-deprecated cargos with weights
- `vehicles_with_engines` - Vehicles joined with default engines
- `vehicles_with_cargo_space` - Vehicles with cargo bed dimensions
- `vehicles_with_weight` - Vehicles with total weight (chassis + parts)

## How It Works

1. **Rust extractor** (`src/main.rs`) decrypts PAK with AES, decompresses with Oodle, extracts `.uasset`/`.uexp` files
2. **C# parser** (`csharp/CargoExtractor/`) uses UAssetAPI with `.usmap` to deserialize UE5.5 properties into JSON
3. **Python aggregator** (`scripts/aggregate_to_sqlite.py`) normalizes JSON into SQLite with proper relationships and computed values

## Project Structure

```
├── src/main.rs                      # Rust PAK extractor
├── src/bin/mod_pack.rs              # Rust mod PAK creator
├── src/bin/mod_explore.rs           # Rust mod PAK reader/explorer
├── csharp/CargoExtractor/           # C# UAsset parser (UAssetAPI)
├── scripts/
│   ├── aggregate_to_sqlite.py       # Python aggregator
│   └── create_decal_pack.py         # Decal pack creator (full pipeline)
├── tools/
│   └── ue4-dds-tools/               # Vendored UE4-DDS-Tools (texture injection)
│       └── src/directx/libtexconv.so # Pre-built DXT5 compressor
├── assets.json                      # Config: assets to extract
├── decal_assets.json                # Config: decal texture assets
├── pyproject.toml                   # Python project (uv2nix)
├── uv.lock                          # Python lock file
├── flake.nix                        # Nix build/dev environment
└── out/                             # Extracted & parsed data
```

## Data Quality Notes

- **Cargo weights**: Aggregated from blueprint `MassInKgOverride` values
- **Vehicle weights**: Extracted from vehicle blueprints (chassis mass + default parts mass)
- **Enum values**: Cleaned (`EMTVehicleType::Small` → `Small`)
- **Object references**: Resolved to full paths where available
- **Active cargos**: Filtered view excludes deprecated and invalid entries

## License

MIT
