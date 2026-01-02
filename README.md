# MotorTown PAK Asset Extractor

Extract and parse game data from MotorTown's Unreal Engine 5.5 PAK files, then aggregate into a normalized SQLite database.

## Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled
- `MotorTown-WindowsServer.pak` file
- `Mappings.usmap` file (generated using [UE4SS](https://github.com/UE4SS-RE/RE-UE4SS) with the Dump Usmap feature)
- `.env` file with AES decryption key

### Setup

1. Place game files in the project root:
   ```
   MotorTown-WindowsServer.pak
   Mappings.usmap
   ```

2. Create `.env` with the AES key:
   ```
   KEY=0xYOUR_AES_KEY_HERE
   ```

## Quick Start

**Full pipeline** (extract → parse → aggregate):
```bash
nix run .#extract                      # Extract & parse assets
python3 scripts/aggregate_to_sqlite.py # Aggregate to database
sqlite3 motortown.db .dump > motortown_data.sql
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
python3 scripts/aggregate_to_sqlite.py
```

**Output:**
- `motortown.db` - SQLite database
- Summary stats printed to console

**Database Contents:**
- 159 vehicles with default parts and tags
- 686 vehicle parts (engines, transmissions, wheels, etc.)
- 84 cargos with aggregated weights from blueprints
- 6,026 vehicle-part relationships
- Views for common queries

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

## Advanced Usage

### Custom Asset List

Edit `assets.json` to specify which assets to extract:

```json
{
  "assets": [
    "MotorTown/Content/DataAsset/Cargos",
    "MotorTown/Content/DataAsset/Vehicles/Vehicles"
  ]
}
```

Cargo actor blueprints are listed in `cargo_actors.json`.

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

**Relationships:**
- `vehicle_default_parts` - Vehicle → Part mappings (slot-based)
- `vehicle_tags` - Vehicle GameplayTags
- `cargo_space_types` - Cargo compatible space types

**Aggregation:**
- `cargo_weights` - Total weight per cargo (summed from blueprint components)
- `cargo_weight_components` - Individual component masses

**Views:**
- `cargos_with_weights` - Cargos with actual weights (blueprint or fallback)
- `vehicles_with_engines` - Vehicles joined with default engines

## How It Works

1. **Rust extractor** (`src/main.rs`) decrypts PAK with AES, decompresses with Oodle, extracts `.uasset`/`.uexp` files
2. **C# parser** (`csharp/CargoExtractor/`) uses UAssetAPI with `.usmap` to deserialize UE5.5 properties into JSON
3. **Python aggregator** (`scripts/aggregate_to_sqlite.py`) normalizes JSON into SQLite with proper relationships and computed values

## Project Structure

```
├── src/main.rs                   # Rust PAK extractor
├── csharp/CargoExtractor/        # C# UAsset parser (UAssetAPI)
├── scripts/
│   └── aggregate_to_sqlite.py    # Python aggregator
├── assets.json                   # Config: DataAssets to extract
├── cargo_actors.json             # Config: Cargo blueprints to extract
├── flake.nix                     # Nix build/dev environment
└── out/                          # Extracted & parsed data
```

## Data Quality Notes

- **Cargo weights**: Aggregated from blueprint `MassInKgOverride` values (35/84 cargos have blueprint data)
- **Vehicle weights**: `CurbWeight` is 0 in DataAssets (would need vehicle blueprint extraction)
- **Enum values**: Cleaned (`EMTVehicleType::Small` → `Small`)
- **Object references**: Resolved to full paths where available

## License

MIT
