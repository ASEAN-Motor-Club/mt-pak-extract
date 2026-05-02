# Vehicle Modding

> Converting vehicles to AWD, tuning blueprint physics, and understanding drivetrain mechanics.

## AWD Conversion

### How It Actually Works

Contrary to initial assumptions, **AWD is NOT controlled by LSD entries in the Vehicles DataTable**. The `LSD0`/`LSD1` entries in DataTable rows are for the **garage UI / part swapping system** only.

The actual drivetrain is determined by **wheel-to-differential connections in the vehicle blueprint** (`.uasset`).

### The Simple Technique (for 4-wheel cars)

For regular 4-wheel vehicles, all wheels can connect to the **same single differential**:

| Wheel | RWD (stock) | AWD (modded) |
|-------|------------|--------------|
| Wheel0 (front left) | *no diff* | `DifferentialComponentName: Differential` |
| Wheel1 (front right) | *no diff* | `DifferentialComponentName: Differential` |
| Wheel2 (rear left) | `Differential` | `Differential` |
| Wheel3 (rear right) | `Differential` | `Differential` |

**No new differential component is needed.** The existing single `Differential_GEN_VARIABLE` just needs its name referenced on the front wheels.

### Multi-Axle Vehicles (Trucks, 6x4, etc.)

Trucks already have multiple differential components in their blueprints (e.g., `Differential1`, `Differential2`). The Squish AWD mod works by **rewiring** which wheels connect to which existing differential:

```
# FL1 AWD mod: just rewired existing diffs
Wheel0, Wheel1 → Differential1  (front axle)
Wheel2, Wheel3 → Differential2  (rear axle)
```

## Blueprint CDO Patching

Blueprint **Class Default Objects (CDOs)** can be patched to change vehicle properties like horn sounds, physics, and component values. This works by modifying the `Default__<BlueprintName>_C` export in the `.uasset` file.

### CDO Patching Toolchain

Use `--patch-cdo-arrays` to patch CDO properties:

```bash
# Requires the parent blueprint (MTVehicleBaseBP) alongside the target
dotnet run -- --patch-cdo-arrays config.json VehicleBlueprint.uasset output_dir/
```

Config format for horn replacement:
```json
{
  "output_filename": "Jemusi",
  "arrays": [],
  "cdo_patches": [
    {
      "path": "HornSound",
      "op": "set_or_create_import_ref",
      "class_package": "/Script/Engine",
      "class_name": "SoundWave",
      "package_path": "/Game/Sounds/Vehicle/Horn/TruckAirHorn_01",
      "asset_name": "TruckAirHorn_01"
    },
    {
      "path": "HornFadeInSeconds",
      "op": "set_or_add_float",
      "value": 0.2
    },
    {
      "path": "HornFadeOutSeconds",
      "op": "set_or_add_float",
      "value": 0.5
    }
  ]
}
```

### Parent Blueprint Requirement

When patching CDOs, UAssetAPI needs the **parent blueprint** in the same directory to resolve the unversioned property schema. Always copy `MTVehicleBaseBP.uasset` + `.uexp` alongside the target blueprint before patching.

```bash
# Extract parent blueprint once
./mt-pak-extract "MotorTown/Content/Cars/MTVehicleBaseBP"

# For each vehicle, copy parent alongside target
cp MTVehicleBaseBP.uasset MTVehicleBaseBP.uexp .
dotnet run -- --patch-cdo-arrays config.json Jemusi.uasset output_dir/
```

### Schema Gaps (MTVehicleColorSlot)

Some vehicle blueprints have CDO properties that reference structs with incomplete schemas in `Mappings.usmap`. The `MTVehicleColorSlot` schema only lists 5 properties but the actual struct has 6+.

**Fix:** Patch `MainSerializer.cs` to gracefully skip unknown schema properties instead of throwing `FormatException`:

```csharp
// In MainSerializer.cs (~line 428)
if (relevantSchema == null)
{
    Console.WriteLine($"  WARNING: Skipping unknown property at schema index {header.UnversionedPropertyIndex}");
    header.UnversionedPropertyIndex += 1;
    return null;
}
```

Alternatively, patch the schema in `Program.cs` to add dummy properties for the missing indices.

### Supported CDO Operations

| Operation | Type | Example |
|-----------|------|---------|
| `set_or_create_import_ref` | ObjectProperty | Create/link an import reference (e.g. HornSound → SoundWave) |
| `set_or_add_float` | FloatProperty | Add or set a float value |
| `set_name` | NameProperty | Set an FName value |
| `set_enum` | EnumProperty | Set an enum value |
| `set_import_ref` | ObjectProperty | Set existing property to an import |

### Vehicles That CANNOT Be Patched (CDO Schema Mismatch)

Some vehicle types have different parent classes that don't include `HornSound` in their unversioned property schema. Attempting to patch these fails with schema errors:

- **Bikes** (Gunthoo, Scooty, Zero) — Parent is `MHBikeBaseBP_C`, not `MTVehicleBaseBP_C`
- **Karts** (Kart_01, SCM_Kart_One) — Different inheritance chain
- **Trailers** — No horn sound property at all

For these vehicles, horn sound changes must be done via **DataTable vehicle rows** (if the game references a horn sound there) or are not possible via blueprint patching.

## Blueprint Patching Toolchain

### `--patch-named-exports` (C# UAssetTool)

A custom command added to UAssetTool for patching specific named exports within a blueprint:

```bash
cd csharp/UAssetTool
dotnet run -- --patch-named-exports config.json template.uasset output_dir/
```

Config format:
```json
{
  "output_filename": "Zydro_Police",
  "exports": [
    {
      "export_name": "Wheel0",
      "patches": [
        {
          "path": "DifferentialComponentName",
          "op": "set_or_create_name",
          "value": "Differential"
        }
      ]
    }
  ]
}
```

Supported ops on named exports:
- `set_or_create_name` — Set or create a `NamePropertyData`
- `set` — Set numeric/bool/string properties
- `set_enum` — Set enum values
- Any other `ApplyPatches` op from the generic patch system

### `--patch-export-props` vs `--patch-named-exports`

| Command | Target | Use Case |
|---------|--------|----------|
| `--patch-export-props` | First NormalExport (usually Export[0]) | Simple single-export patches |
| `--patch-named-exports` | Any export by exact name | Blueprint component patching |

## Python Vehicle Mod Builder

The `scripts/create_vehicle_mod.py` builder supports both DataTable and blueprint patching:

```json
{
  "vehicle_id": "Zydro_Police",
  "datatable_file": "Vehicles",
  "patches": [
    {
      "path": "Parts",
      "op": "add_map_entry",
      "key": "EMTVehiclePartSlot::LSD1",
      "value": "LSD_Clutch_1.5_50"
    }
  ],
  "blueprint_file": "Zydro_Police",
  "blueprint_folder": "Zydro",
  "blueprint_patches": [
    {
      "export_name": "Wheel0",
      "patches": [
        {
          "path": "DifferentialComponentName",
          "op": "set_or_create_name",
          "value": "Differential"
        }
      ]
    }
  ]
}
```

### `blueprint_folder` Field

Critical: the `blueprint_folder` field controls where the blueprint is staged in the PAK:

```python
# Staged path:
MotorTown/Content/Cars/Models/{blueprint_folder}/{blueprint_file}.uasset
```

For `Zydro_Police`, the folder is **`Zydro`** (the base model), NOT `Zydro_Police`. Without this, the mod blueprint won't override the game file.

## Checking Vehicle Blueprint Structure

To determine if a vehicle can be converted to AWD:

```bash
# Extract and dump the blueprint
cd csharp/UAssetTool
dotnet run -- --dump /path/to/VehicleName.uasset
```

Look for:
1. **Wheel exports** — Check if front wheels (`Wheel0`, `Wheel1`) already have `DifferentialComponentName`
2. **Differential exports** — Count how many `Differential*_GEN_VARIABLE` exports exist
3. **CDO export** — Check `Default__VehicleName_C` for any drivetrain-related properties

### Differential Component Count by Vehicle Type

| Vehicle Type | Typical Diff Components | AWD Possible? |
|-------------|------------------------|---------------|
| Regular RWD car | `Differential` (1) | ✅ Yes — wire all wheels to same diff |
| 6-wheel truck | `Differential1` + `Differential2` (2) | ✅ Yes — rewire existing diffs |
| AWD car | `DifferentialF` + `DifferentialR` + `DiffernetialC` (3) | Already AWD |

## Limitations

- **Cannot add new component exports** — The toolchain can only modify properties of existing exports. It cannot add new `MTDifferentialComponent` exports to a blueprint.
- **RWD cars work because they already have one differential** — Just need to wire the front wheels to it.
- **Trucks work because they already have multiple differentials** — Just need to rewire which wheels connect to which.
