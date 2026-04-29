---
name: cargo-mod-creation
description: Create MotorTown cargo mods — new cargo types with blueprints, DataTable rows, and delivery point recipes
---

# Cargo Mod Creation

Create mod PAKs that add new cargo types to MotorTown. This skill covers the full pipeline from JSON config to working `.pak` file.

## Quick Start

```bash
nix develop --command bash -c '
python3 scripts/mods.py build schedule-i
'

# Or directly:
nix develop --command bash -c '
python3 scripts/create_cargopack.py \
  --config mods/schedule-i/cargo_entries.json \
  --recipes mods/schedule-i/recipe_entries.json \
  --output CarPartsImport_P.pak
'
```

## Pipeline Overview

| Step | Tool | Input | Output |
|------|------|-------|--------|
| 1. Add cargo rows | C# `--add-cargos` | `mods/schedule-i/cargo_entries.json` + `Cargos.uasset` | Modified `Cargos.uasset` |
| 2. Patch blueprints | C# `--patch-blueprint` | `mods/schedule-i/cargo_entries.json` + `SmallBox.uasset` | Per-cargo `.uasset/.uexp` |
| 3. Add recipes | C# `--add-recipes` | `mods/schedule-i/recipe_entries.json` + delivery point templates | Modified delivery point assets |
| 4. Assemble PAK | Python | All outputs | Directory structure |
| 5. Build PAK | Rust `mod_pack` | Directory | `.pak` file |

## Configuration Files

### `mods/schedule-i/cargo_entries.json`

```json
{
  "entries": [
    {
      "row_name": "Money",
      "display_name": ["Money", "Stack"],
      "cargo_type": "None",
      "cargo_space_types": ["Flatbed", "Box"],
      "weight_min": 5,
      "weight_max": 10,
      "volume_size": 1,
      "payment_per_km": 1000,
      "payment_multiplier": 5.0,
      "spawn_probability": 10,
      "mesh_path": "/Game/Models/PolygonHeist/Meshes/Props/SM_Prop_Money_Stack_01",
      "mass_kg": 8,
      "blueprint_name": "Money",
      "cargo_flags": 11,
      "allow_stacking": true
    }
  ]
}
```

#### Key Fields

| Field | Default | Description |
|-------|---------|-------------|
| `cargo_type` | — | `SmallPackage`, `LargePackage`, `None`, `Furniture`, `Stone`, `Log`. **Use `None` for modded cargos** to prevent wildcard demand matching |
| `cargo_space_types` | — | Vehicle bed types: `Flatbed`, `Box`, `Container`, `Dump`, `Tanker`, `CarCarrier` |
| `cargo_flags` | `11` | **Must be 11** for loadable cargo (forklift/crane). `0` = hand-carry only |
| `payment_multiplier` | `2.0` | `PaymentPer1KmMultiplierByMaxWeight` — higher = more penalty on large vehicles. Base game: 1.0–2.0. Use high values (3–5) to discourage bulk loading on flatbeds |
| `num_cargo_min` | `0` | Minimum quantity per delivery job |
| `num_cargo_max` | `1` | Maximum quantity per delivery job |
| `mesh_path` | — | UE asset path to a `StaticMesh`. **Must use `SM_Prop_*` meshes** (see Gotcha #9) |
| `blueprint_name` | — | Name for the generated blueprint class |
| `blueprint_template` | `out/SmallBox.uasset` | Override the template blueprint for multi-mesh cargos (e.g. pallets) |
| `replace_all_meshes` | `false` | If `true`, replaces ALL `StaticMesh` imports (not just the last). Needed when template has multiple distinct meshes (e.g. pallet + items) |
| `allow_stacking` | `false` | If `true`, sets `bAllowStacking` so cargo stacks on top of each other |
| `extra_export_patches` | — | Per-component position/rotation adjustments (see Multi-Mesh Pallets) |

### `mods/schedule-i/recipe_entries.json`

Four recipe sections: `sources`, `sinks`, `transforms`, `catalysts`.

```json
{
  "sources": [
    {
      "delivery_point": "Harbor_Export",
      "template_path": "out/Harbor_Export.uasset",
      "recipes": [{"cargo": "Money", "production_time": 60}]
    }
  ],
  "sinks": [
    {
      "delivery_point": "Resident",
      "template_path": "out/Resident.uasset",
      "recipes": [{"cargo": "Ganja", "production_time": 600, "hidden": false}]
    }
  ],
  "transforms": [
    {
      "delivery_point": "Factory_Toy",
      "template_path": "out/Factory_Toy.uasset",
      "recipes": [{
        "input_cargo": "GanjaPallet", "input_count": 5,
        "output_cargo": "Ganja", "output_count": 10,
        "production_time": 180, "hidden": false
      }]
    }
  ],
  "catalysts": [
    {
      "delivery_point": "Factory_Toy",
      "template_path": "out/Factory_Toy.uasset",
      "recipes": [
        {"cargo": "Money", "count": 1, "production_time": 600, "speed_multiplier": 2, "hidden": false}
      ]
    }
  ],
  "storage": [
    {
      "delivery_point": "Factory_Toy",
      "template_path": "out/Factory_Toy.uasset",
      "entries": [
        {"cargo_key": "Money", "max_storage": 30}
      ]
    }
  ]
}
```

#### Recipe Fields

| Field | Default | Description |
|-------|---------|-------------|
| `hidden` | `!isSource` | **Set `false` for sinks** to make demand visible at delivery point |
| `production_time` | — | Seconds between production cycles |
| `speed_multiplier` | 1 (2 for catalysts) | `ProductionSpeedMultiplier` — catalysts use this to boost all production at a delivery point |

#### Catalyst Pattern

Catalysts are fuel-like inputs (matching Farm_Hemp's `Fuel` mechanic): cargo is consumed, no direct output, but production speed at the delivery point is boosted. The base game uses this for Fuel and QuicklimePallet at farms.

## Critical Rules (Gotchas)

### 1. Blueprint PAK Path — NO Subfolder

> [!CAUTION]
> Blueprints MUST be placed directly in the `Delivery/` folder, **not** in a subfolder.

The DataTable's `ActorClass` import uses package path `/Game/Objects/Mission/Delivery/{name}`, which the engine maps to **`Content/Objects/Mission/Delivery/{name}.uasset`**.

```
✅ Delivery/Rims_Sport.uasset          ← engine finds it
❌ Delivery/Rims_Sport/Rims_Sport.uasset  ← engine can't find it
```

The proxy mod (reference implementation) uses the flat convention. The base game uses subfolders — but modded blueprints must follow the import path convention.

### 2. Never Modify NameMap In-Place

> [!CAUTION]
> **Never** use `SetNameReference()` to modify NameMap entries. This corrupts hash integrity and makes the `.uasset` unloadable.

Use `FName.FromString(asset, newName)` instead — it safely adds new NameMap entries. Stale old entries are harmless (unreferenced).

### 3. Deep-Clone Serialization

> [!IMPORTANT]
> All DataTable rows and `MTProductionConfig` structs must be **deep-cloned** from existing entries. Constructing properties from scratch corrupts unversioned header serialization.

```csharp
var newRow = (StructPropertyData)templateRow.Clone();
// Then modify properties in-place
```

### 4. FolderName Must Match

The `.uasset`'s `FolderName` field must match the PAK path identity:

```csharp
asset.FolderName = FString.FromString($"/Game/Objects/Mission/Delivery/{blueprintName}");
```

### 5. Import Replacement — In-Place Only

When replacing the `StaticMesh` import, update the existing import AND its parent Package import in-place. Don't append new imports (leaves orphaned entries):

```csharp
// Find mesh import + its parent package via OuterIndex chain
asset.Imports[meshPkgImportIdx].ObjectName = FName.FromString(asset, meshPath);
asset.Imports[meshImportIdx].ObjectName = FName.FromString(asset, meshName);
```

### 6. ActorClass Requires Import Entries

Each new cargo in the Cargos DataTable needs two Import entries added to the asset:
1. **Package import**: `/Game/Objects/Mission/Delivery/{blueprintName}`
2. **BlueprintGeneratedClass import**: `{blueprintName}_C` with outer pointing to the package

### 7. Sink Visibility

Set `hidden: false` in `mods/schedule-i/recipe_entries.json` for sinks where you want the cargo demand to appear as a visible delivery task. Default for sinks is `hidden: true` (invisible demand).

### 8. CargoFlags = 11

The standard value for loadable cargo (forklift/crane compatible). 58 of 61 proxy mod cargos use this. Without it, cargo appears greyed-out and can't be loaded.

### 9. Mesh Collision — Use `SM_Prop_*` Only

> [!CAUTION]
> **Never use vehicle part meshes** (`/Game/Cars/Parts/...`) as cargo meshes. They have NO collision geometry — cargo will fall through trucks and the ground.

Vehicle part meshes (wheels, spoilers, steering wheels) are skeletal attachments designed for cars. They have visual geometry but no collision hull.

**Use `SM_Prop_*` meshes** from Polygon asset packs (PolygonTown, PolygonHeist, PolygonCity, etc.). These are standalone world props with built-in collision. See `sm_prop_meshes.txt` (2,894 meshes) for the full catalog, generated via:

```bash
cargo run --release --quiet -- --search SM_Prop
```

Adding collision components (e.g. `BoxComponent`) via cross-asset `Clone()` **crashes the game** due to incompatible unversioned header schemas between assets. The only safe collision source is the StaticMesh asset itself.

### 10. Blueprint `_C` Suffix Must Be Preserved

> [!CAUTION]
> UE5 BlueprintGeneratedClass exports **must** retain the `_C` suffix (e.g. `Money_C`, `Default__Money_C`).

The `--clone-asset` autodetection picks up the full class name (`SmallBox_C`) instead of the base name (`SmallBox`), causing `SmallBox_C → Money` (missing `_C`). **Always pass `old_name` explicitly** in the clone config. Without `_C`, the engine gets `EXCEPTION_ACCESS_VIOLATION reading address 0x...0110` (null class pointer).

### 11. Source-Only Delivery Points Cannot Be Sinks

> [!CAUTION]
> Delivery points like `LiveFishSupplier` that only have `OutputCargos` (sources) **cannot** be used as sinks.

Adding `InputCargos` to a source-only blueprint crashes the game when the player interacts with it. Before adding a sink recipe, check `out/{name}_parsed.json` and verify the CDO has existing `InputCargos` entries (see base game sinks list in `motortown.db`).

### 12. CargoType `None` — Use for Modded Cargo

> [!IMPORTANT]
> Use `cargo_type: "None"` for all modded cargos to prevent unwanted wildcard demand matching.

`SmallPackage` causes modded cargo to appear at Supermarkets and Warehouses (which have wildcard `DemandConfig` for `SmallPackage`). `LargePackage` has the same issue with some delivery points. `None` ensures cargo only appears at delivery points you explicitly configure.

> [!NOTE]
> Despite what AGENTS.md previously documented, `cargo_type: "None"` does NOT crash UE5. The `set_enum` op correctly serializes `"None"` as enum index 0. This was confirmed working in the Schedule I mod.

### 13. Cooked Assets Cannot Be Loaded by UE5 Editor

> [!CAUTION]
> Game `.uasset` files extracted from PAKs are **unversioned** (cooked/shipping format). The UE5 editor **cannot load them** — it rejects unversioned packages. This prevents using UE5 editor tools (Merge Actors, material assignment) on base game assets. See Custom Merged Meshes section for details on what was tried and what failed.

## Multi-Mesh Pallet Templates

For palletized cargo (multiple items stacked as one cargo unit), use an existing multi-mesh blueprint as `blueprint_template`.

### Available Templates

| Template | Components | Z Spacing | Root Collision | Notes |
|----------|------------|-----------|----------------|-------|
| `out/SmallBox.uasset` | 1 mesh | — | Yes | Default single-mesh cargo |
| `out/Pizza_05.uasset` | 5 meshes (Mesh + 4 PizzaBox) | 0,5,10,15,20 | Yes | Small stacked items, no pallet base |
| `out/HempSackPallet.uasset` | 7 meshes (Mesh + 6 Sack) | 27,27,54,54,86,86 | Yes (Mesh root) | With wooden pallet base (Pallet_110x80) |
| `out/CheesePallet.uasset` | 5 meshes | 14,14,49,49 | Yes | 2×2 layout with wooden pallet |
| `out/BoxPalletA.uasset` | 9 meshes (Mesh + 8 boxes) | 2×2 grid × 2 layers | Yes (Mesh root) | 8 child components with `NoCollision`, good for `import_index` targeting |
| `out/AirlineMealPallet.uasset` | 8 meshes | varied | Yes | Mixed mesh types |

### Component Positioning with `extra_export_patches`

**Supported patch ops**: `set`, `set_enum`, `set_import_ref`, `null_ref`, `set_soft_object`, `set_name`, `clear_array`, `clear_map`, `clear_tags`.

> [!CAUTION]
> `set_vector` and `set_rotator` are **NOT implemented**. They produce "Unknown op" warnings and are silently skipped. Component positions are fixed at the template's default values. To change positions, the template `.uasset` must be modified directly (e.g. via UAssetGUI).

### Per-Component Mesh Targeting with `import_index`

The `import_replacements` config supports `import_index` to target specific import slots by index, enabling different meshes for different components within the same template:

```json
"import_replacements": [
  {
    "match_class": "StaticMesh",
    "import_index": 0,
    "new_package_path": "/Game/Models/PolygonHeist/Meshes/Props/SM_Prop_Money_Stack_01",
    "new_name": "SM_Prop_Money_Stack_01"
  },
  {
    "match_class": "StaticMesh",
    "import_index": 1,
    "new_package_path": "/Game/Objects/Mission/Delivery/Mesh/Pallet_110x80",
    "new_name": "Pallet_110x80"
  }
]
```

| Field | Description |
|-------|-------------|
| `import_index` | 0-based index among imports matching `match_class`. Without this, replaces the LAST match. |
| `replace_all` | If `true`, replaces ALL matching imports with the same mesh (legacy behavior). |
| `match_name` | Match by import ObjectName in addition to class. |

Use `--dump` to find the import indices:
```bash
dotnet run -- --dump template.uasset | grep "Import.*StaticMesh"
```

**Example: BoxPalletA with money mesh** — replaces root pallet mesh (index 1) with money stack and child box meshes (index 0) with money stack, giving root collision + visual-only child components.

## Custom Merged Meshes (Blender → FBX → UE5) — EXPERIMENTAL

> [!CAUTION]
> This approach has significant limitations and is **not recommended** for MotorTown mods. The game expects **unversioned cooked assets** but UE5 editor produces **versioned assets**. The resulting mesh renders with **no texture** (default material) and the game reports "corrupt data found." Use multi-mesh templates instead (see above).

### What Works

1. **Blender geometry creation** — headless Blender can create custom mesh geometry and export as FBX
2. **UE5 FBX import** — the editor imports the FBX and creates a proper `StaticMesh` with auto-generated collision
3. **UE5 cook** (`-run=Cook -TargetPlatform=Windows`) — converts versioned editor assets to unversioned cooked format

### What Doesn't Work

1. **Materials** — the FBX import creates a default material. Game materials (`MI_PolygonHeist_01_A` etc.) can't be loaded by UE5 editor because they're in the game's cooked PAKs. The cooked mesh renders untextured.
2. **UE5 editor can't load cooked game assets** — tried `load_asset`, `EditorAssetLibrary`, `AssetRegistry`. Only `load_package` works but the loaded objects aren't accessible via the standard Python API.
3. **Versioned→unversioned conversion** — attempted via C# UAssetAPI's `IsUnversioned = false` trick. The resulting file has correct version headers but empty custom version container (all versions are 0 from `.usmap` mappings). UE5 warns "Asset has been saved with empty engine version."
4. **UE5 Merge Actors on cooked mesh** — can't load the original money mesh into the editor to merge.
5. **JsonAsAsset** — doesn't support `StaticMesh` asset type. Only supports Materials, Textures, Data, Sound, Animation, Physics. Also not available for UE 5.5 (latest release: 5.4.4).
6. **`set_vector`/`set_rotator` patch ops** — never implemented in the C# tool.

### If You Need a Single Combined Mesh

The only viable path requires:
1. A UE5 project with the source mesh imported as a proper editor asset (not cooked)
2. Merge Actors in the editor to combine instances
3. Cook the merged mesh
4. Include cooked output in mod PAK

This requires having the source FBX/PSK files for the mesh, which are not available from cooked game assets.

### Blender Install (Windows)

```powershell
Invoke-WebRequest -Uri 'https://download.blender.org/release/Blender4.2/blender-4.2.19-windows-x64.zip' -OutFile 'D:\blender.zip'
Expand-Archive -Path 'D:\blender.zip' -DestinationPath 'D:\'
# Blender at D:\blender-4.2.19-windows-x64\blender.exe
```

## Payment Multiplier Tuning

`PaymentPer1KmMultiplierByMaxWeight` controls how per-unit pay scales with vehicle cargo capacity:

| Multiplier | Behavior | Use Case |
|------------|----------|----------|
| 1.0 | No penalty for large vehicles | Bulk cargo (Cement, GroceryBag) |
| 1.5 | Mild penalty | Logs, GroceryBox |
| 2.0 (default) | Standard scaling | Most cargos (76 in base game) |
| 3.0–5.0 | Heavy penalty | Small-car-only cargo (discourages flatbed loading) |

**Higher = more penalty on large vehicles.** Use high values (3–5) for small cargo that shouldn't be bulk-loaded on flatbeds, and low values (1.0) for pallet cargo designed for large vehicles.

## Base Game Reference Data

### Delivery Point Types

| MissionPointType | Examples | Role |
|------------------|----------|------|
| `None` | Harbor_Export, GrainExport | Defined by ProductionConfigs |
| `Factory` | Factory_Raven, Factory_Bakery | Consumes inputs → produces output |
| `Store` | Supermarket, BurgerCounter | Consumer endpoint |
| `Warehouse` | Warehouse, MilitaryBase | Storage hub |
| `DropOff` | CoalDrop_Harbor, FuelDemand | Drop-off only |

### CargoSpaceTypes

| Type | Vehicle Bed |
|------|-------------|
| `Flatbed` | Open flatbed trucks |
| `Box` | Enclosed box trucks |
| `Container` | Container carriers |
| `Dump` | Dump trucks |
| `Tanker` | Liquid tankers |
| `Grain` | Grain trailers |
| `Log` | Log carriers |
| `CarCarrier` | Vehicle transporters |
| `LiveFishTanker` | Fish transport |
| `ConcreteMixer` | Concrete mixers |
| `DryBulk` | Dry bulk carriers |
| `Garbage` | Garbage trucks |

### Useful Mesh Paths (with collision ✓)

Props from Polygon asset packs (standalone world objects):
- `/Game/Models/PolygonHeist/Meshes/Props/SM_Prop_Money_Stack_01` — Money stack
- `/Game/Models/PolygonShops/Meshes/Props/SM_Prop_Bag_Paper_01` — Paper bag
- `/Game/Models/PolygonGangWarfare/Meshes/Props/SM_Prop_Packet_Stack_Large_01` — Drug packet stack
- `/Game/PolygonTown/Meshes/Props/SM_Prop_ToolCabinet_01` — Tool cabinet
- `/Game/Models/PolygonCity/Meshes/Props/SM_Prop_PowerBox_01` — Metal power box
- `/Game/Models/PolygonConstruction/Meshes/Props/SM_Prop_CardboardBox_05` — Cardboard box
- `/Game/Models/PolygonMilitary/Meshes/Props/SM_Prop_Pallet_03` — Pallet
- `/Game/Models/PolygonStreetRacer/Meshes/Props/SM_Prop_Container_Large_01` — Large container

Full catalog: `sm_prop_meshes.txt` (2,894 meshes across 9 asset packs).

## Version Awareness

The build pipeline uses templates from `out/` (e.g., `out/SmallBox.uasset`, `out/Cargos.uasset`), which come from the game PAK and change between game updates.

Before building, verify the active game version:
```bash
scripts/mt-version.sh status
```

To build against a different version:
```bash
# Switch to old version (archives current first)
scripts/mt-version.sh switch v0.7.17

# Or use a worktree for parallel building
cd ../mt-v0.7.17 && python3 scripts/create_cargopack.py ...
```

Include game version in mod filenames: `MoneyRun_v0.7.19_P.pak`

## Verifying a Built PAK

```bash
# List PAK contents
cargo run --release --bin mod_explore --quiet -- MyMod_P.pak --list

# Dump asset structure for debugging
cd csharp/UAssetTool
dotnet run --quiet -- --dump /path/to/asset.uasset

# Binary scan for stale references
python3 -c "
import re
with open('path/to/Blueprint.uasset', 'rb') as f:
    data = f.read()
paths = re.findall(r'/Game/[A-Za-z0-9/_]+', data.decode('ascii', errors='ignore'))
for p in paths: print(p)
"
```

## Key Files

| File | Purpose |
|------|---------|
| `scripts/create_cargopack.py` | Orchestrates the full build pipeline |
| `csharp/UAssetTool/Program.cs` | C# tool: `--add-rows`, `--clone-asset` (supports `import_index`), `--patch-cdo-arrays`, `--dump` |
| `mods/schedule-i/cargo_entries.json` | Cargo definitions (types, weights, meshes, patches) |
| `mods/schedule-i/recipe_entries.json` | Delivery point source/sink/transform/catalyst recipes |
| `out/SmallBox.uasset` | Default blueprint template (single mesh) |
| `out/Pizza_05.uasset` | Multi-mesh template (5 stacked, no pallet) |
| `out/BoxPalletA.uasset` | Multi-mesh template (root mesh + 8 child, `NoCollision` on children) |
| `out/HempSackPallet.uasset` | Multi-mesh template (6 sacks on wooden pallet) |
| `out/Cargos.uasset` | Base game Cargos DataTable template |
| `sm_prop_meshes.txt` | Full catalog of 2,894 collision-safe `SM_Prop_*` meshes |
