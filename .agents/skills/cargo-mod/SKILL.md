---
name: cargo-mod-creation
description: Create MotorTown cargo mods — new cargo types with blueprints, DataTable rows, and delivery point recipes
---

# Cargo Mod Creation

Create mod PAKs that add new cargo types to MotorTown. This skill covers the full pipeline from JSON config to working `.pak` file.

## Quick Start

```bash
nix develop --command bash -c '
python3 scripts/create_cargopack.py \
  --config cargo_entries.json \
  --recipes recipe_entries.json \
  --output CarPartsImport_P.pak
'
```

## Pipeline Overview

| Step | Tool | Input | Output |
|------|------|-------|--------|
| 1. Add cargo rows | C# `--add-cargos` | `cargo_entries.json` + `Cargos.uasset` | Modified `Cargos.uasset` |
| 2. Patch blueprints | C# `--patch-blueprint` | `cargo_entries.json` + `SmallBox.uasset` | Per-cargo `.uasset/.uexp` |
| 3. Add recipes | C# `--add-recipes` | `recipe_entries.json` + delivery point templates | Modified delivery point assets |
| 4. Assemble PAK | Python | All outputs | Directory structure |
| 5. Build PAK | Rust `mod_pack` | Directory | `.pak` file |

## Configuration Files

### `cargo_entries.json`

```json
{
  "entries": [
    {
      "row_name": "Money",
      "display_name": ["Money", "Stack"],
      "cargo_type": "SmallPackage",
      "cargo_space_types": ["Flatbed", "Box"],
      "weight_min": 5,
      "weight_max": 10,
      "volume_size": 1,
      "payment_per_km": 1000,
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
| `cargo_type` | — | `SmallPackage`, `LargePackage`, `None`, `Furniture`, `Stone`, `Log` |
| `cargo_space_types` | — | Vehicle bed types: `Flatbed`, `Box`, `Container`, `Dump`, `Tanker`, `CarCarrier` |
| `cargo_flags` | `11` | **Must be 11** for loadable cargo (forklift/crane). `0` = hand-carry only |
| `num_cargo_min` | `0` | Minimum quantity per delivery job |
| `num_cargo_max` | `1` | Maximum quantity per delivery job |
| `mesh_path` | — | UE asset path to a `StaticMesh`. **Must use `SM_Prop_*` meshes** (see Gotcha #9) |
| `blueprint_name` | — | Name for the generated blueprint class |
| `allow_stacking` | `false` | If `true`, sets `bAllowStacking` so cargo stacks on top of each other |

### `recipe_entries.json`

```json
{
  "sources": [
    {
      "delivery_point": "Harbor_Export",
      "template_path": "out/Harbor_Export.uasset",
      "recipes": [
        {"cargo": "Rims_Sport", "production_time": 120}
      ]
    }
  ],
  "sinks": [
    {
      "delivery_point": "Factory_Raven",
      "template_path": "out/Factory_Raven.uasset",
      "recipes": [
        {"cargo": "Rims_Sport", "production_time": 600, "hidden": false}
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

Set `hidden: false` in `recipe_entries.json` for sinks where you want the cargo demand to appear as a visible delivery task. Default for sinks is `hidden: true` (invisible demand).

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
| `CarCarrier` | Vehicle transporters |

### Useful Mesh Paths (with collision ✓)

Props from Polygon asset packs (standalone world objects):
- `/Game/Models/PolygonHeist/Meshes/Props/SM_Prop_Money_Stack_01` — Money stack
- `/Game/PolygonTown/Meshes/Props/SM_Prop_ToolCabinet_01` — Tool cabinet
- `/Game/Models/PolygonCity/Meshes/Props/SM_Prop_PowerBox_01` — Metal power box
- `/Game/Models/PolygonConstruction/Meshes/Props/SM_Prop_CardboardBox_05` — Cardboard box
- `/Game/Models/PolygonMilitary/Meshes/Props/SM_Prop_CardboardBox_03` — Military box
- `/Game/Models/PolygonMilitary/Meshes/Props/SM_Prop_Pallet_03` — Pallet
- `/Game/Models/PolygonStreetRacer/Meshes/Props/SM_Prop_Container_Large_01` — Large container

Full catalog: `sm_prop_meshes.txt` (2,894 meshes across 9 asset packs).

## Verifying a Built PAK

```bash
# List PAK contents
cargo run --release --bin mod_explore --quiet -- MyMod_P.pak --list

# Re-parse a built blueprint (should succeed without errors)
cd csharp/CargoExtractor
dotnet run --configuration Release --verbosity quiet -- /path/to/built/Blueprint.uasset

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
| `csharp/CargoExtractor/Program.cs` | C# tool: `--add-cargos`, `--patch-blueprint`, `--add-recipes` |
| `cargo_entries.json` | Cargo definitions (types, weights, meshes) |
| `recipe_entries.json` | Delivery point source/sink recipes |
| `out/SmallBox.uasset` | Blueprint template (cloned for each new cargo) |
| `out/Cargos.uasset` | Base game Cargos DataTable template |
| `sm_prop_meshes.txt` | Full catalog of 2,894 collision-safe `SM_Prop_*` meshes |
