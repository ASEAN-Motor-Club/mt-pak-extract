---
name: general-modding
description: General MotorTown modding — PAK architecture, DataTable mechanics, mod compatibility, and the mt-pak-extract toolchain
---

# General MotorTown Modding

This skill covers the foundational architecture of MotorTown modding — how PAKs work, how DataTables override, how to build compatibility with other mods, and the available toolchain. For specific mod types, see the `cargo-mod` and `tire-mod` skills.

## PAK Architecture

### How UE5 PAK Loading Works

MotorTown runs on Unreal Engine 5.5. Mods are shipped as `_P.pak` files (the `_P` suffix is critical — UE loads these as "patch" PAKs that override base game assets).

```
MotorTown/
├── Content/
│   └── Paks/
│       ├── MotorTown-Windows.pak          ← base game (2.9 GB)
│       └── Mods/
│           ├── qxZap_MoreTuning_P.pak     ← community mod
│           └── ASEAN_PoliceTyres_P.pak    ← our mod
```

**Load order is alphabetical.** If two PAKs contain the same file (e.g., `VehicleParts0.uasset`), the **alphabetically-last PAK wins**. This is how compatibility conflicts happen.

### Override Rules

| Scenario | Result |
|----------|--------|
| Only base game has the file | Base game version loads |
| One mod has the file | Mod version loads (overrides base) |
| Multiple mods have the same file | **Last alphabetically wins**, others are ignored |
| Mod has a NEW file (not in base) | File is added to the virtual filesystem |

> [!CAUTION]
> There is **no merging**. If your mod includes `VehicleParts0.uasset` with 54 rows, and another mod includes it with 320 rows, one wins completely and the other is discarded.

### PAK Structure

Every PAK file mirrors the base game directory layout:

```
MotorTown/Content/
├── Cars/Parts/Tire/              ← tire physics assets
├── DataAsset/VehicleParts/       ← VehicleParts, VehicleParts0, Engines, etc.
├── Objects/Mission/Delivery/     ← cargo blueprints
├── Materials/Decal/              ← decal textures
└── ...                           ← any other game path
```

The mount point is `../../../` (three levels up from the PAK file location), which resolves to the game's root `Content/` directory.

## DataTable System

DataTables are the backbone of MotorTown's data-driven design. Most mod types work by adding rows to or overriding these tables.

### Key DataTables

| DataTable | Location | Rows (base) | Purpose |
|-----------|----------|-------------|---------|
| `VehicleParts` | `DataAsset/VehicleParts/` | 713 | Full vehicle parts catalog (engines, transmissions, tires, aero, etc.) |
| `VehicleParts0` | `DataAsset/VehicleParts/` | 50 | **Override/addon table** — supersedes `VehicleParts` for shared categories |
| `Engines` | `DataAsset/VehicleParts/` | varies | Engine DataAsset refs |
| `Transmissions` | `DataAsset/VehicleParts/` | varies | Transmission DataAsset refs |
| `AeroParts` | `DataAsset/VehicleParts/` | varies | Aero body kits |
| `LSD` | `DataAsset/VehicleParts/` | varies | Limited-slip differential configs |
| `Cargos` | `DataAsset/` | ~100 | Cargo type definitions |
| `Vehicles` | `DataAsset/` | ~80 | Vehicle definitions, types, flags |
| `Decals` | `Materials/Decal/` | ~423 | Decal texture catalog |

### VehicleParts Override Hierarchy

> [!IMPORTANT]
> The game loads **both** `VehicleParts.uasset` and `VehicleParts0.uasset`. For any part type (e.g., "Tire") that exists in both tables, `VehicleParts0` entries **take precedence**.

This means:
- The base `VehicleParts` has 713 rows covering ALL part types
- `VehicleParts0` has 50 rows that **override** specific categories
- If you add a tire only to `VehicleParts` but `VehicleParts0` has its own tire list, yours won't appear

**Strategy:** For tire mods, only modify `VehicleParts0` (50 rows). This avoids touching the massive 713-row `VehicleParts` table, which other mods also modify.

### DataTable Row Structure

Every VehicleParts row contains ALL part fields (tire, engine, aero, suspension, etc.), with `PartType` determining which fields are active:

```
PartType: Tire
├── Tire.TirePhysicsDataAsset → import reference to tire physics
├── VehicleTypes: [Small, Medium]
├── VehicleKeys: [Elisa_Police, Muhan_Police]   ← vehicle restriction
├── LevelRequirementToBuy: {CL_Police: 10}      ← career level gate
├── Cost: 2000
├── MassKg: 10
├── Name2.Texts: ["AMC Police 78"]               ← display name
└── ... (hundreds of other fields, inactive for tires)
```

## Vehicle Restriction System

### VehicleKeys — Restrict to Specific Cars

`VehicleKeys` is an array of vehicle key strings. If non-empty, **only** those vehicles can equip the part.

```json
"vehicle_keys": ["Elisa_Police", "Muhan_Police", "Zydro_Police", "Nuke_Police", "Police_01", "PoliceInterceptor_01"]
```

| Vehicle | Key | Type |
|---------|-----|------|
| Elisa Police | `Elisa_Police` | Small |
| Muhan Police | `Muhan_Police` | Small |
| Zydro Police | `Zydro_Police` | Small |
| Nuke Police | `Nuke_Police` | Small |
| Police 01 | `Police_01` | Small |
| Police Interceptor | `PoliceInterceptor_01` | Small |
| Gunthoo Police | `Gunthoo_Police` | Bike |

### LevelRequirementToBuy — Career Level Gate

Map of `{CareerLine: MinLevel}`. Player must reach the specified level to purchase.

```json
"level_requirement": {"CL_Police": 10}
```

Career lines: `CL_Driver`, `CL_Truck`, `CL_Police`, `CL_Racer`, `CL_Bus`, `CL_Taxi`.

### VehicleTypes — Vehicle Class Filter

Array of vehicle size classes. Part only appears for vehicles of matching type.

```json
"vehicle_types": ["Small"]
```

Values: `Small`, `Medium`, `Large`, `HeavyMachine`, `MotorCycle`.

### OverrideAllowedVehicleKeys — Whitelist Override

Lets a part appear on vehicles it normally wouldn't fit (bypasses VehicleType restrictions).

## Mod Compatibility

### The Problem

When two mods modify the same DataTable (e.g., `VehicleParts0.uasset`), the alphabetically-last PAK wins and the other's changes are completely lost.

**Example conflict:**
```
qxZap_MoreTuning_P.pak  → VehicleParts0 with 320 rows (engines, tires, LSD, etc.)
ASEAN_PoliceTyres_P.pak  → VehicleParts0 with 54 rows (base 50 + 4 tires)
```
Result: Our 54-row version loads (alphabetically last), MoreTuning's 320 rows are lost.

### The Solution: `--compat-mod`

The build tools support a `--compat-mod` flag that **extracts a DataTable from another mod's PAK** and uses it as the base template. Your additions are layered on top.

```bash
# Build standalone (base game only)
python3 scripts/create_tirepack.py \
  --config tire_entries.json \
  --output ASEAN_PoliceTyres_P.pak

# Build compatible with MoreTuning
python3 scripts/create_tirepack.py \
  --config tire_entries.json \
  --output ASEAN_PoliceTyres_MoreTuningCompat_P.pak \
  --compat-mod path/to/qxZap_MoreTuning_P.pak
```

**How it works internally:**
1. `mod_explore` extracts `VehicleParts0.uasset` from the compat mod PAK
2. This extracted DataTable (with all its rows) becomes the template
3. Your new rows are added on top → final DataTable has ALL rows
4. Output PAK contains the merged DataTable

### Multiple Compat Mods

You can chain multiple `--compat-mod` flags. They're processed in order — the **last one that contains VehicleParts0** wins as the base template:

```bash
python3 scripts/create_tirepack.py \
  --config tire_entries.json \
  --output output.pak \
  --compat-mod MoreTuning_P.pak \
  --compat-mod NoLimits_P.pak
```

If `NoLimits_P.pak` doesn't contain `VehicleParts0`, it's skipped (with a warning) and `MoreTuning_P.pak`'s version is used.

### Minimizing Conflict Surface Area

> [!TIP]
> **Only include the DataTables you actually modify.** Every DataTable in your PAK is a potential conflict point.

| Mod Goal | Only touch | Don't touch |
|----------|-----------|-------------|
| Add tires | `VehicleParts0` | `VehicleParts`, `Engines`, `Transmissions`, `AeroParts` |
| Add cargo | `Cargos`, delivery point assets | `VehicleParts*` |
| Add decals | `Decals`, texture assets | `VehicleParts*`, `Cargos` |

MoreTuning v2.2 modifies: `VehicleParts0`, `AeroParts`, `Engines`, `LSD`, `License*`, `Transmissions`.
NoLimits v2.2 modifies: `AeroParts`, `Headlights`, `Wheels` (no VehicleParts0 conflict).

### PAK Naming Convention

The recommended naming pattern includes mod source, version, and compatibility variant:

```
{Studio}_{ModName}_v{Version}[_CompatMod]_P.pak
```

Examples:
```
ASEAN_PoliceTyres_v0.1.5_P.pak                          ← standalone
ASEAN_PoliceTyres_v0.1.5_MoreTuningCompat_P.pak          ← MoreTuning compat
ASEAN_PoliceTyres_v0.1.5_MoreTuningNoLimitsCompat_P.pak  ← MoreTuning + NoLimits
```

> [!WARNING]
> Users should install **only one variant** of a mod. Installing both standalone and compat versions causes a double-override conflict.

### Analyzing Another Mod's Contents

Before building a compat version, analyze what DataTables the other mod modifies:

```bash
# List all files in a mod PAK
cargo run --release --bin mod_explore --quiet -- OtherMod_P.pak --list

# Search for specific DataAsset types
cargo run --release --bin mod_explore --quiet -- OtherMod_P.pak --list | grep DataAsset

# Extract a specific file for inspection
cargo run --release --bin mod_explore --quiet -- OtherMod_P.pak --extract \
  MotorTown/Content/DataAsset/VehicleParts/VehicleParts0.uasset
# → extracts to mod_out/VehicleParts0.uasset

# Parse and count rows
cd csharp/CargoExtractor
dotnet run --configuration Release --verbosity quiet -- /path/to/mod_out/VehicleParts0.uasset
```

## Toolchain Reference

### Rust Tools

| Binary | Command | Purpose |
|--------|---------|---------|
| `mt-pak-extract` | `cargo run --release --quiet --` | Base game PAK extraction (AES decrypt + Oodle decompress) |
| `mod_explore` | `cargo run --release --quiet --bin mod_explore --` | List, search, and extract from mod PAKs |
| `mod_pack` | `cargo run --release --quiet --bin mod_pack --` | Pack a directory into a mod PAK |

### C# Tool (CargoExtractor)

Located in `csharp/CargoExtractor/`. Run via:

```bash
cd csharp/CargoExtractor
dotnet run --configuration Release --verbosity quiet -- <command> [args]
```

| Command | Purpose |
|---------|---------|
| `--batch` | Parse all extracted `.uasset` files |
| `--dump <file>` | Debug dump of a `.uasset` file |
| `--patch-tire <config> <template> <outdir>` | Create tire physics asset |
| `--add-tire-parts <config> <template> <outdir>` | Add tire row to VehicleParts DataTable |
| `--add-cargos <config> <template> <outdir>` | Add cargo rows to Cargos DataTable |
| `--patch-blueprint <config> <template> <outdir>` | Create cargo blueprint from template |
| `--add-recipes <config> <template> <outdir>` | Add delivery recipes |
| `--add-decals <config> <template> <outdir>` | Add decal entries |

### Python Build Scripts

| Script | Purpose |
|--------|---------|
| `scripts/create_tirepack.py` | Tire mod PAK builder (supports `--compat-mod`) |
| `scripts/create_cargopack.py` | Cargo mod PAK builder |
| `scripts/create_decal_pack.py` | Decal mod PAK builder |
| `scripts/aggregate_to_sqlite.py` | Parsed JSON → SQLite database |

### SQLite Database

`motortown.db` is generated by `aggregate_to_sqlite.py` and contains normalized game data:

```sql
-- Find all police vehicles
SELECT id, name, vehicle_type FROM vehicles
WHERE id IN (SELECT vehicle_id FROM vehicle_tags WHERE tag LIKE '%Police%');

-- Find all tire parts
SELECT name, cost, mass_kg FROM vehicle_parts WHERE part_type = 'Tire';

-- Find delivery points
SELECT * FROM delivery_points;
```

Key tables: `vehicles`, `vehicle_parts`, `vehicle_default_parts`, `vehicle_tags`, `cargos`, `cargo_weights`, `delivery_points`.

## UAssetAPI Gotchas

These apply to ALL mod types when working with `UAssetAPI` in the C# tool.

### FName Number Suffix Trap

UE's FName system parses trailing `_NN` as an instance Number. `BasicTire_45` is stored as FName(`"BasicTire"`, Number=46).

```csharp
// ✅ Correct — explicit Number=0
export.ObjectName = new FName(asset, "APF_78", 0);

// ❌ Wrong — may parse _78 as Number=79
export.ObjectName = FName.FromString(asset, "APF_78");
```

### Deep-Clone All Structs

Never construct DataTable rows from scratch. Always clone from an existing template row:

```csharp
var newRow = (StructPropertyData)templateRow.Clone();
// Then modify properties in-place
```

Constructing properties manually corrupts unversioned header serialization.

### NameMap Handling (Tire vs Cargo)

- **Tire assets:** NameMap[0] is the self-package reference and MUST be updated (see tire-mod skill)
- **Cargo blueprints:** NameMap stale entries are harmless — blueprints reference their class via imports

### Import References

When adding new assets to a DataTable, you must add corresponding Import entries:

```csharp
// 1. Package import
var pkgImport = new Import("/Script/CoreUObject", "Package",
    FPackageIndex.FromRawIndex(0), "/Game/Cars/Parts/Tire/APF_78_Tire", false, asset);
asset.Imports.Add(pkgImport);

// 2. Asset import (outer = package)
var assetImport = new Import("/Script/MotorTown", "MTTirePhysicsDataAsset",
    FPackageIndex.FromImport(pkgImportIdx - 1), "APF_78_Tire", false, asset);
asset.Imports.Add(assetImport);
```

## Diagnostic Workflow

### Mod doesn't load at all
1. Check PAK filename ends with `_P.pak`
2. Check mount point with `mod_explore --list` (should be `../../../`)
3. Verify PAK version is V11

### DataTable changes not visible
1. Check if another mod overrides the same DataTable (alphabetical conflict)
2. Use `mod_explore --list | grep DataAsset` to identify conflicts
3. Rebuild with `--compat-mod` pointing to the conflicting mod

### Part doesn't appear in-game
1. Check `VehicleTypes` matches the vehicle class
2. Check `VehicleKeys` includes the specific vehicle
3. Check `LevelRequirementToBuy` — player may not have required level
4. Check `bIsHidden` is `false`
5. For tires: verify `VehicleParts0` contains the row (override table takes precedence)

### Asset loads but has wrong values
1. Check flat PAK path (no subfolders for physics/blueprint assets)
2. Check NameMap[0] matches new asset path (tire assets only)
3. Check export name doesn't have stale `_NN` suffix
4. Binary scan for stale template references:
   ```bash
   python3 -c "
   with open('asset.uasset', 'rb') as f:
       data = f.read()
   import re
   for m in re.finditer(rb'BasicTire|SmallBox|OldTemplate', data):
       print(f'Stale ref at offset {m.start()}: {m.group()}')
   "
   ```

## Key Files

| File | Purpose |
|------|---------|
| `AGENTS.md` | Build commands, Nix dev shell, full pipeline docs |
| `src/bin/mod_pack.rs` | PAK creator (V11, mount `../../../`) |
| `src/bin/mod_explore.rs` | PAK reader/extractor for mod analysis |
| `csharp/CargoExtractor/Program.cs` | Core UAsset manipulation tool |
| `motortown.db` | SQLite database of parsed game data |
| `out/` | Extracted base game assets (templates) |
| `scripts/` | Python build pipeline scripts |
