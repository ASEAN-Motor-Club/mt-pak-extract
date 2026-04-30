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

### Config INI Files

UE5 config `.ini` files can also be shipped inside PAK mods. The game reads config from the PAK virtual filesystem at:

```
MotorTown/Config/
├── DefaultEngine.ini        ← base engine config
├── UserEngine.ini           ← user overrides (higher priority)
├── DefaultGame.ini
└── ...
```

**PAK path for config overrides:** `MotorTown/Config/UserEngine.ini`

To ship a config-only mod, create the INI file in the staging directory at `MotorTown/Config/` and pack it with `mod_pack`:

```bash
mkdir -p /tmp/staging/MotorTown/Config
cat > /tmp/staging/MotorTown/Config/UserEngine.ini << 'EOF'
[Audio]
UnfocusedVolumeMultiplier=1.0
EOF

cargo run --release --quiet --bin mod_pack -- /tmp/staging MyConfigMod_P.pak
```

> [!NOTE]
> The `MotorTown/Config/` path is relative to the mount point (`../../../`), resolving from `Content/Paks/` up to the game root then into `MotorTown/Config/`. **Do NOT** use `MotorTown/Saved/Config/Windows/` — that path is for runtime user config on disk, not PAK-based config overrides.

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
| `Cargos` | `DataAsset/` | ~100 | Cargo type definitions (**CompositeDataTable** — see below) |
| `Cargos_01` | `DataAsset/` | ~100 | Child of `Cargos` — actual cargo rows |
| `Cargos_Deprecated` | `DataAsset/` | 1 | Child of `Cargos` — deprecated cargo rows |
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

### CompositeDataTable Pattern

`Cargos.uasset` is a **CompositeDataTable** — a special UE5 DataTable subclass that merges rows from child DataTables via its `ParentTables` array property. The base game has:

```
Cargos (CompositeDataTable)
├── ParentTables[0] → Cargos_01 (DataTable, ~100 rows)
└── ParentTables[1] → Cargos_Deprecated (DataTable, 1 row)
```

At runtime, the engine loads `Cargos` and recursively loads + merges all child tables in `ParentTables`. **Directly adding rows to the parent `Cargos.uasset` does NOT work** — the engine re-merges from children and discards any rows not in a child table.

#### Adding Rows to a CompositeDataTable

To add new rows, you must:
1. **Create a new child DataTable** (e.g., `Cargos_ScheduleI`) with your rows
2. **Override the parent** (`Cargos.uasset`) to append your child to `ParentTables`

> [!CAUTION]
> The child DataTable **MUST be clone-renamed** from an existing DataTable using `--clone-asset`. Simply renaming the output file via `output_filename` does NOT change the internal package path (`NameMap[0]`). The engine resolves assets by internal path, not filename — if the internal path says `/Game/DataAsset/Cargos_Deprecated` but the file is at `Cargos_ScheduleI.uasset`, the engine cannot find it.

**Correct 3-step flow:**

```python
# Step 1: Clone-rename to fix internal package path
clone_config = {
    "assets": [{
        "new_name": "Cargos_ScheduleI",
        "old_name": "Cargos_Deprecated",
        "new_path": "/Game/DataAsset/Cargos_ScheduleI",
        "rename_exports": True,
        "rename_imports": True,
        "patch_namemap_0": True,  # Critical: updates internal path
    }]
}
run_generic("--clone-asset", clone_config, "Cargos_Deprecated.uasset", clone_dir)

# Step 2: Add rows to the clone
rows_config = {"output_filename": "Cargos_ScheduleI", "rows": [...]}
run_generic("--add-rows", rows_config, cloned_child, output_dir)

# Step 3: Patch parent to register child in ParentTables
parent_config = {
    "patches": [{
        "path": "ParentTables",
        "op": "append_import_to_array",
        "class_package": "/Script/Engine",
        "class_name": "DataTable",
        "package_path": "/Game/DataAsset/Cargos_ScheduleI",
        "asset_name": "Cargos_ScheduleI",
    }]
}
run_generic("--patch-export-props", parent_config, "Cargos.uasset", cargos_dir)
```

**Both** the parent `Cargos.uasset` and child `Cargos_ScheduleI.uasset` must be staged in the PAK at `DataAsset/`.

#### UE4SS Runtime Diagnostics

Use UE4SS Lua scripts to verify DataTable loading at runtime:

```lua
-- Check if objects are loaded
local obj = StaticFindObject("/Game/DataAsset/Cargos_ScheduleI.Cargos_ScheduleI")
if obj ~= nil and obj:IsValid() then
    print("FOUND: " .. obj:GetClass():GetFName():ToString())
end

-- Force-load an asset (must run in game thread)
ExecuteInGameThread(function()
    local asset = LoadAsset("/Game/DataAsset/Cargos_ScheduleI")
end)
```

Deploy UE4SS Lua scripts via SCP to `Mods/<ModName>/Scripts/main.lua` on the Windows machine.

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

PartType: Intake
├── Intake.Slope → torque curve slope (higher = more torque bias)
├── Intake.BaseRPMRatio → RPM ratio where effect begins (lower = earlier response)
├── Intake.IntakeSpeedEfficencyMultiplier → overall HP multiplier
├── VehicleTypes: [Small]
├── VehicleKeys: [...]
└── ... (common fields same as above)

PartType: Turbocharger
├── Turbocharger.bIsValid → must be true for turbo to activate
├── Turbocharger.TorqueMultiplier → peak torque multiplier
├── Turbocharger.BaseTorqueMultiplier → base torque at all RPMs
├── Turbocharger.IntakePressureMultiplier → boost pressure
├── Turbocharger.TurbineWeight → rotational inertia (spool time)
├── Turbocharger.TurbineAspectRatio → turbine A/R ratio
├── Turbocharger.HeatingMultiplier → engine heat generation
├── Turbocharger.FuelConsumptionMultiplier → fuel usage
└── ... (common fields same as above)
```

### Intake vs Turbocharger — Supercharger Simulation

Intake parts can simulate superchargers: low `BaseRPMRatio` (instant response), positive `Slope` (torque), high `EfficiencyMult` (HP). Unlike turbochargers, intakes have **no spool lag** (no TurbineWeight). See the `intake-mod` skill for full details.

**Vanilla values (v0.7.18+1):**

| Type | Row | Key Values |
|------|-----|------------|
| Intake | Row 201 | Slope=0.1, BaseRPMRatio=0.7, EfficiencyMult=1.5 |
| Intake | Row 202 | Slope=-0.1, BaseRPMRatio=0.8, EfficiencyMult=0.7 |
| Turbocharger | Stock | TorqueMult=1.1, BaseTorqueMult=0.98, TurbineWeight=30 |
| Turbocharger | Stage1 | TorqueMult=1.2, BaseTorqueMult=0.95, TurbineWeight=100 |

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

Values: `Small`, `Medium`, `Large`, `HeavyMachine`, `MotorCycle`, `Pickup`, `Bus`, `Truck`, `SemiTractor`, `SemiTrailer`, `Motorhome`.

> [!NOTE]
> `Pickup` was discovered in v0.7.18+1 — it covers pickup trucks that can equip both Small and truck-class parts. `Bus`, `Truck`, `SemiTractor`, `SemiTrailer`, `Motorhome` are for heavy-duty vehicle tires.

### TruckClasses — Truck Sub-Class Filter

For truck/bus tires, `TruckClasses` filters within the truck vehicle types:

```json
"truck_classes": ["HeavyDuty", "MediumDuty"]
```

Values: `HeavyDuty`, `MediumDuty`. Set alongside `vehicle_types: ["Bus", "Truck", ...]`.

### bIsDualRearWheel — DRW Truck Tires

Boolean on the `Tire` sub-struct. When `true`, the engine renders two wheels on the rear axle:

```json
"bIsDualRearWheel": true
```

Use `BasicHeavyDutyRearTire` as the template for DRW truck tires.

### OverrideAllowedVehicleKeys — Whitelist Override

Lets a part appear on vehicles it normally wouldn't fit (bypasses VehicleType restrictions).

## Vehicle License System

Vehicles can equip Bus/Taxi licenses via the `Parts` map. This is entirely data-table driven — no blueprint changes needed.

### How It Works

| Field | Purpose | Example |
|-------|---------|---------|
| `bIsBusable` | Enables bus license slot in garage | `true` |
| `bIsTaxiable` | Enables taxi license slot in garage | `true` |
| `VehicleTypeFlags` | Vehicle type bitmask (0=normal, 16=bus) | `0` |
| `GameplayTags` | Must include `Vehicle.Bus` for bus functionality | `["Vehicle.Bus"]` |
| `Parts` map | Must include `EMTVehiclePartSlot::BusLicense` → `BusLicense0` | See below |

### Available License Parts

| Part RowName | PartType | Cost |
|-------------|----------|------|
| `BusLicense0` | BusLicense | 20,000 |
| `TaxiLicense0` | TaxiLicense | 10,000 |
| `TaxiLicense1` | TaxiLicense | 12,000 |
| `TaxiLicense_Bike` | TaxiLicense | 10,000 |

### Example: Adding Bus/Taxi License to a Vehicle

Use `--patch-rows` to modify an existing vehicle row:

```json
{
  "output_filename": "Vehicles_Ambulance",
  "patches": [
    {
      "row_name": "Brutus_Ambulance",
      "patches": [
        { "path": "bIsBusable", "op": "set", "value": true },
        { "path": "bIsTaxiable", "op": "set", "value": true },
        { "path": "GameplayTags", "op": "add_gameplay_tags", "tags": ["Vehicle.Bus"] },
        { "path": "Parts", "op": "add_map_entry", "key": "EMTVehiclePartSlot::BusLicense", "value": "BusLicense0" }
      ]
    }
  ]
}
```

> [!WARNING]
> Keep `VehicleTypeFlags: 0` unless the vehicle is a dedicated bus variant. Setting `VehicleTypeFlags: 16` on a non-bus vehicle may cause unintended NPC spawning or delivery filtering. The base Bongo van has `bIsBusable: true` with `VehicleTypeFlags: 0` — the boolean + part slot is sufficient.

### Vehicle DataTable Locations

| DataTable | Vehicles | Path |
|-----------|----------|------|
| `Vehicles` | All vehicle types | `DataAsset/Vehicles/Vehicles` |
| `Vehicles_Ambulance` | Ambi, Tavan_Ambulance, Brutus_Ambulance | `DataAsset/Vehicles/Vehicles_Ambulance` |
| `Vehicles_Bus` | Bongo, Bongo_Bus, Roadmaster | `DataAsset/Vehicles/Vehicles_Bus` |
| `Vehicles_Truck` | Brutus, Brutus_Wrecker, Brutus_Tanker, etc. | `DataAsset/Vehicles/Vehicles_Truck` |

## Mod Compatibility

### Blueprint CDO Patching

Beyond DataTable mods, you can modify individual vehicle/actor blueprints by patching their **Class Default Object (CDO)** — the `Default__X_C` export in the `.uasset`.

#### UE5 CDO Initialization Order

When UE5 loads a blueprint class, CDO properties are initialized in this order:
1. **C++ constructor** — sets native defaults (e.g. `AMTVehicle` sets `HornFadeInSeconds = 0.1`)
2. **SuperClass CDO** — parent blueprint defaults are inherited (e.g. `MTVehicleBaseBP` sets `HornSound = Horn`)
3. **Asset data** — serialized CDO overrides from the `.uasset` file **take precedence**

This means a mod PAK that overrides a blueprint's `.uasset` with new CDO properties will win over the parent defaults — exactly how the game's own truck blueprints override `HornSound` to `TruckAirHorn_01`.

#### How CDO Patching Works

```bash
# Patch a vehicle blueprint CDO property
cd csharp/UAssetTool
dotnet run -- --patch-cdo-arrays config.json template.uasset output_dir/
```

The `--patch-cdo-arrays` command:
1. Loads the blueprint asset
2. Finds the `Default__X_C` CDO export (may need to reparse from `RawExport`)
3. Applies `cdo_patches` — property-level modifications using the patch engine
4. Applies `arrays` — array-level additions/replacements
5. Writes the modified asset

#### Schema Resolution for Blueprint CDOs

Blueprint CDOs use **unversioned property serialization**. UAssetAPI needs the full class schema chain to parse them. For blueprint-generated classes (anything ending in `_C`):

- The class's own properties come from its `ClassExport.LoadedProperties`
- The **parent blueprint's properties** must also be resolvable
- UAssetAPI discovers parent blueprints by looking for `.uasset` files in the same directory

> [!IMPORTANT]
> Copy the parent blueprint (e.g. `MTVehicleBaseBP.uasset` + `.uexp`) alongside the target before patching. Without it, CDO reparse fails with `"Failed to find a valid property for schema index N"`.

#### Inherited vs Serialized Properties

CDOs only serialize properties that **differ from the parent default**. If a property value matches the parent, it's not stored — it's inherited at runtime.

This has a critical implication for patching: if you want to change an inherited property (e.g. `HornSound` on a vehicle that uses the default horn), the property **doesn't exist** in the CDO data. Use `set_or_create_import_ref` instead of `set_import_ref` to handle this:

```json
{
  "cdo_patches": [
    {
      "path": "HornSound",
      "op": "set_or_create_import_ref",
      "class_package": "/Script/Engine",
      "class_name": "SoundWave",
      "package_path": "/Game/Sounds/Vehicle/Horn/TruckAirHorn_01",
      "asset_name": "TruckAirHorn_01"
    }
  ]
}
```

#### Example: Vehicle Horn Mod

Change Jemusi's horn from default car horn to truck air horn:

```bash
nix develop --command bash -c '
  # 1. Ensure parent blueprint is accessible for schema resolution
  cp MTVehicleBaseBP.uasset out/MTVehicleBaseBP.uasset
  cp MTVehicleBaseBP.uexp out/MTVehicleBaseBP.uexp

  # 2. Patch CDO
  cd csharp/UAssetTool && dotnet run --configuration Release --verbosity quiet -- \
    --patch-cdo-arrays mods/truck-horn/horn_patch.json ../../out/Jemusi.uasset /tmp/horn_out
  cd ../..

  # 3. Build PAK
  mkdir -p /tmp/horn_staging/MotorTown/Content/Cars/Models/Jemusi
  cp /tmp/horn_out/Jemusi.{uasset,uexp} /tmp/horn_staging/MotorTown/Content/Cars/Models/Jemusi/
  cargo run --release --quiet --bin mod_pack -- /tmp/horn_staging ASEAN_JemusiTruckHorn_P.pak

  # 4. Cleanup
  rm -f out/MTVehicleBaseBP.{uasset,uexp}
'
```

#### Vehicle Sound Assets

| Sound | Asset Path | Used By |
|-------|-----------|--------|
| Car horn | `/Game/Sounds/Vehicle/Horn/Horn` | Most cars (default via MTVehicleBaseBP) |
| Truck air horn | `/Game/Sounds/Vehicle/Horn/TruckAirHorn_01` | All trucks |
| Bike horn | `/Game/Sounds/Vehicle/Horn/Bike_01` | All motorcycles |

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
python3 scripts/mods.py build police-tyres

# Or directly with script:
python3 scripts/create_tirepack.py \
  --config mods/police-tyres/tire_entries.json \
  --output ASEAN_PoliceTyres_P.pak

# Build compatible with MoreTuning
python3 scripts/create_tirepack.py \
  --config mods/police-tyres/tire_entries.json \
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
  --config mods/police-tyres/tire_entries.json \
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

### Manual Mod Merging (When `--compat-mod` Is Not Enough)

The `--compat-mod` flag works when your mod **only** adds rows to a DataTable that the other mod also modifies. But if you need to combine mods that each bring **their own assets** (e.g., tire physics `.uasset` files), `--compat-mod` only extracts the DataTable — the other mod's assets are lost.

**Example:** Combining PD Parts (6 car tire physics assets + VehicleParts0 with intakes) with Gunthoo bike tires (6 bike tire physics assets + VehicleParts0 with bike tires).

**The problem:**
- `create_tirepack.py --compat-mod PDParts.pak` → extracts PD Parts' VehicleParts0 as template, adds bike tire rows ✅
- But the output PAK only contains the **bike tire physics assets** — the 6 PD Parts car tire physics assets are NOT staged ❌
- Result: PD Parts' car tires appear in the list but have no grip values (physics assets missing)

**Solution — Manual merge:**

```python
# 1. Extract both PAKs to a staging directory
#    PD Parts → staging/MotorTown/Content/...
#    Bike tires → staging/MotorTown/Content/... (overwrites VehicleParts0)

# 2. Patch cross-mod changes (e.g., add Gunthoo_Police to SC intake VehicleKeys)
#    Use --patch-rows on the merged VehicleParts0

# 3. Build final PAK from the merged staging directory
#    mod_pack staging/ output.pak
```

**Key rule:** When combining mods that each have `.uasset` assets (not just DataTables), you MUST manually merge the asset directories before repacking.

> [!WARNING]
> **Inherited properties from compat templates:** When `--compat-mod` extracts a VehicleParts0 and your mod clones rows from it, properties like `VehicleKeys` and `LevelRequirementToBuy` are inherited from the template row. If the template row is a police tire with `VehicleKeys: ["Elisa_Police", ...]`, your new tire will ALSO be police-only unless you explicitly clear it. The tire/intake builders now auto-clear these, but for manual merges or new mod types, always check for stale inherited restrictions.

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
cd csharp/UAssetTool
dotnet run --configuration Release --verbosity quiet -- /path/to/mod_out/VehicleParts0.uasset
```

## Game Version Management

When a new Motor Town update drops, the game PAK changes and extracted data (`out/`, `motortown.db`) must be refreshed. The versioning system uses git tags + worktrees + a data archive to manage multiple versions in parallel.

```bash
# Check current version
scripts/mt-version.sh status

# Archive current data after extraction
scripts/mt-version.sh archive v0.7.18

# Switch to a different version for building
scripts/mt-version.sh switch v0.7.17

# Create parallel worktree for old version
scripts/mt-version.sh worktree v0.7.17
```

See `AGENTS.md` "Game Versioning" section for full workflow.

## Toolchain Reference

### Rust Tools

| Binary | Command | Purpose |
|--------|---------|---------|
| `mt-pak-extract` | `cargo run --release --quiet --` | Base game PAK extraction (AES decrypt + Oodle decompress) |
| `mod_explore` | `cargo run --release --quiet --bin mod_explore --` | List, search, and extract from mod PAKs |
| `mod_pack` | `cargo run --release --quiet --bin mod_pack --` | Pack a directory into a mod PAK |

### C# Tool (UAssetTool)

Located in `csharp/UAssetTool/`. Run via:

```bash
cd csharp/UAssetTool
dotnet run --configuration Release --verbosity quiet -- <command> [args]
```

| Command | Purpose |
|---------|---------|
| `--batch` | Parse all extracted `.uasset` files |
| `--dump <file>` | Debug dump of a `.uasset` file |
| `--add-rows <config> <template> <outdir>` | Add rows to any DataTable (clone-based) |
| `--patch-rows <config> <template> <outdir>` | Modify existing DataTable rows by RowName |
| `--clone-asset <config> <template> <outdir>` | Clone and rename any asset with property patches |
| `--patch-cdo-arrays <config> <template> <outdir>` | Patch CDO properties and arrays in blueprint exports |
| `--patch-export-props <config> <template> <outdir>` | Patch properties on the main export (e.g., CompositeDataTable `ParentTables`) |

### Python Build Scripts

| Script | Purpose |
|--------|---------|
| `scripts/modbase.py` | **Shared base module** — `ModBuilder` class with common build infrastructure |
| `scripts/create_tirepack.py` | Tire mod PAK builder (subclasses `ModBuilder`) |
| `scripts/create_intakepack.py` | Intake mod PAK builder (subclasses `ModBuilder`) |
| `scripts/create_cargopack.py` | Cargo mod PAK builder (subclasses `ModBuilder`) |
| `scripts/create_decal_pack.py` | Decal mod PAK builder (subclasses `ModBuilder`) |
| `scripts/aggregate_to_sqlite.py` | Parsed JSON → SQLite database |

### ModBuilder Base Module

All mod-type scripts inherit from `ModBuilder` in `scripts/modbase.py`. The base class provides:

| Method | Purpose |
|--------|---------|
| `run_dotnet(args, label)` | Run C# UAssetTool commands |
| `build_pak(staging_dir)` | Build mod PAK via `mod_pack` binary |
| `verify_pak()` | List PAK contents via `mod_explore` |
| `extract_from_compat_mod(pak, asset_path, dest)` | Extract a single asset from another mod's PAK |
| `resolve_template_with_compat(base, pak_path)` | Resolve DataTable template (base game or compat mod) |
| `stage_asset(src, pak_dir, name)` | Copy `.uasset/.uexp` pair to PAK staging |
| `stage_datatable(src, name, subdir)` | Stage a DataTable asset |

**Build flow** (template method pattern):

```
build() → transform_assets() → register_in_tables() → assemble_pak() → build_pak() → verify_pak()
```

Subclasses implement the three hooks to define their mod-type-specific logic.

### C# Shared Helpers

The C# tool (`Program.cs`) provides shared helpers used across all DataTable commands:

| Helper | Used By | Purpose |
|--------|---------|---------|
| `FindDataTable(asset)` | cargos, tires, decals | Find first DataTableExport in an asset |
| `SetLocalizationGuid(prop)` | cargos, tires | Set `Name` to random GUID for localization |
| `SetDisplayName(prop, json, asset)` | cargos, tires | Set `Name2.Texts` display name array |
| `SetDescriptionFallback(prop, text)` | tires | Set `Desciption` text fallback |
| `AddImportChain(asset, pkg, class, path, name)` | cargos, tires, CDO patches | Add Package + Asset import pair |
| `SetEnumArray(arr, json, asset, enumType)` | cargos, tires | Set enum array from JSON values |

### CDO Patch Engine Operations

The `--patch-cdo-arrays`, `--patch-rows`, and `--patch-export-props` commands use a JSON-driven patch engine. Key operations:

| Operation | Purpose | Creates if missing? |
|-----------|---------|--------------------|
| `set` | Set numeric, bool, or string property | No |
| `set_enum` | Set enum property | No |
| `set_import_ref` | Set ObjectProperty to import reference | No |
| `set_or_create_import_ref` | Set or create ObjectProperty with import reference | **Yes** |
| `set_or_add_float` | Set or create float property | **Yes** |
| `set_or_create_name` | Set or create name/string property | **Yes** |
| `set_or_create_int` | Set or create integer property | **Yes** |
| `null_ref` | Set ObjectProperty/SoftObjectProperty to null | No |
| `set_soft_object` | Set SoftObjectProperty path | No |
| `clear_array` | Empty an array property | No |
| `clear_map` | Empty a map property | No |
| `add_gameplay_tags` | Add tags to existing GameplayTagContainer | No |
| `add_map_entry` | Add entry to existing map (clones key/value from existing entries) | No |
| `append_import_to_array` | Append new import reference to array (e.g., `ParentTables`) | No |

The `set_or_create_*` variants are essential for patching **inherited** CDO properties that aren't serialized in the child blueprint.

### --patch-rows: In-Place DataTable Row Patching

Modifies existing DataTable rows by RowName without adding new rows. Uses the same patch engine as `--patch-cdo-arrays`.

```bash
cd csharp/UAssetTool
dotnet run -- --patch-rows config.json template.uasset output_dir/
```

Config format:
```json
{
  "output_filename": "Vehicles_Ambulance",
  "patches": [
    {
      "row_name": "Brutus_Ambulance",
      "patches": [
        { "path": "bIsBusable", "op": "set", "value": true },
        { "path": "GameplayTags", "op": "add_gameplay_tags", "tags": ["Vehicle.Bus"] },
        { "path": "Parts", "op": "add_map_entry", "key": "EMTVehiclePartSlot::BusLicense", "value": "BusLicense0" }
      ]
    }
  ]
}
```

> [!IMPORTANT]
> Unlike `--add-rows` which clones a row and adds a **new** row, `--patch-rows` finds an existing row by name and applies patches in-place. This is essential when you need to modify a vehicle's properties without duplicating it.

## Creating a New Mod Type

To add a new mod type (e.g., engine mods, wheel mods):

### 1. Define JSON config schema

Create a JSON format for the new mod type. Follow existing patterns:
- Tire: `mods/police-tyres/tire_entries.json` with `tire_physics` + `tire_part` sections
- Cargo: `mods/schedule-i/cargo_entries.json` with entries array + `mods/schedule-i/recipe_entries.json`

### 2. Add C# command(s) to `Program.cs`

Reuse shared helpers to minimize new code:

```csharp
// Add command dispatch in Main()
else if (addEnginePartsMode)
{
    // --add-engine-parts config.json template.uasset output_dir
    var idx = Array.IndexOf(args, "--add-engine-parts");
    // ...
    AddEngineParts(configPath, templatePath, outputDir);
}

// Command handler — uses shared helpers
static void AddEngineParts(string configPath, string templatePath, string outputDir)
{
    var asset = new UAsset(templatePath, EngineVersion.VER_UE5_5, Mappings);
    var dtExport = FindDataTable(asset);  // shared
    if (dtExport == null) return;

    var templateRow = dtExport.Table.Data[^1];
    var newRow = (StructPropertyData)templateRow.Clone();  // deep-clone

    SetLocalizationGuid(/* Name prop */);        // shared
    SetDisplayName(/* Name2 prop */, ...);        // shared
    var (_, importIdx) = AddImportChain(...);     // shared

    dtExport.Table.Data.Add(newRow);
    asset.Write(outputPath);
}
```

### 3. Create Python build script

Subclass `ModBuilder`:

```python
# scripts/create_enginepack.py
from modbase import ModBuilder, add_common_args

class EngineModBuilder(ModBuilder):
    def transform_assets(self):
        # Create engine DataAsset files
        self.run_dotnet(["--patch-engine", ...], "patch engine")

    def register_in_tables(self):
        # Add to Engines DataTable
        template = self.resolve_template_with_compat(
            base_template, "MotorTown/Content/DataAsset/VehicleParts/Engines.uasset")
        self.run_dotnet(["--add-engine-parts", ...], "add engine parts")

    def assemble_pak(self):
        self.stage_asset(engine_asset, "Cars/Parts/Engine", name=engine_name)
        self.stage_datatable(engines_dt, "Engines", "DataAsset/VehicleParts")

    def print_summary(self):
        self.log(f"  Engines: {', '.join(...)}")
```

### 4. Create skill documentation

Add `.agents/skills/{type}-mod/SKILL.md` following the cargo/tire skill structure:
- Quick Start with build command
- Pipeline overview table
- Configuration reference
- Critical rules / gotchas
- Verification commands
- Key files table

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

### Clone-Rename for New Assets

> [!CAUTION]
> When creating a new asset derived from an existing template (e.g., a new child DataTable), you **MUST** use `--clone-asset` with `patch_namemap_0: true` to rename the internal package path. Simply writing the file with a new filename (e.g., via `output_filename` in `--add-rows`) does NOT update `NameMap[0]`, which is the internal package path. The engine resolves assets by this internal path — if it doesn't match the file path, `LoadAsset()` and `StaticFindObject()` fail silently.

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

### Dot-Path Resolution Through Sub-Structs

The C# `ResolvePropertyWithContainer` function resolves dot-separated paths through `StructPropertyData` containers. This means `Intake.Slope` correctly traverses into the `Intake` struct and finds the `Slope` float inside it:

```csharp
// "Intake.Slope" resolves as:
// 1. Find "Intake" in row properties → StructPropertyData
// 2. Traverse into struct.Value (its child properties)
// 3. Find "Slope" in those children → FloatPropertyData
```

This works with `set_or_add_float`, `set_or_create_name`, `set_or_create_int`, etc. If the property doesn't exist, the `set_or_add_*` variants clone the first same-type property in the container as a template and add it.

> [!IMPORTANT]
> Only ONE level of dot-path nesting is needed for VehicleParts sub-structs (e.g., `Intake.Slope`, `Turbocharger.bIsValid`). The sub-structs themselves are direct children of the row.

### Map Property Types — NamePropertyData vs StrPropertyData

When adding entries to DataTable maps (e.g. `Parts` in vehicle rows), **the parsed JSON shows values as plain strings, but UAssetAPI internally stores them as different C# types depending on the map.**

The `Parts` map uses:
- **Keys:** `EnumPropertyData` (e.g. `EMTVehiclePartSlot::BusLicense`)
- **Values:** `NamePropertyData` (NOT `StrPropertyData`)

Constructing `StrPropertyData` values from scratch for a `NamePropertyData` map **corrupts unversioned header serialization** and causes runtime serialization errors.

```csharp
// ✅ Correct — clone existing entry and modify
var firstVal = mapProp.Value.Values.OfType<NamePropertyData>().FirstOrDefault();
var valProp = (NamePropertyData)firstVal.Clone();
valProp.Value = FName.FromString(asset, "BusLicense0");

// ❌ Wrong — StrPropertyData doesn't match NamePropertyData map
var valProp = new StrPropertyData(...) { Value = FString.FromString("BusLicense0") };
```

**Always debug-log the actual C# types before cloning:**
```csharp
foreach (var kvp in mapProp.Value)
    Console.WriteLine($"Key: {kvp.Key.GetType().Name}, Val: {kvp.Value.GetType().Name}");
```

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
6. For intakes: verify `VehicleKeys` includes the target vehicle — intakes with non-empty VehicleKeys are restricted to ONLY those vehicles

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

### Rebuilt PAK still has old values
1. **Always verify the final PAK output directly** — extract and dump the `.uasset` from the built `.pak` file, not from intermediate temp directories
2. Stale temp build directories (`/tmp/nix-shell.*/modpack_*/`) persist across builds inside `nix develop` sessions. These contain configs from **previous** builds and are NOT reliable indicators of current PAK contents
3. To verify PAK values, use this pattern:
   ```bash
   # Extract the specific asset from the built PAK
   cargo run --release --quiet --bin mod_explore -- \
     mods/<name>/builds/<pak_file> --extract \
     MotorTown/Content/<path>/<Asset>.uasset mod_out/
   cargo run --release --quiet --bin mod_explore -- \
     mods/<name>/builds/<pak_file> --extract \
     MotorTown/Content/<path>/<Asset>.uexp mod_out/
   
   # Dump and verify values
   cd csharp/UAssetTool && dotnet run --configuration Release --verbosity quiet -- \
     --dump /path/to/repo/mod_out/<Asset>.uasset
   ```
4. For numeric values (e.g. storage limits, production counts), binary-scan the `.uexp`:
   ```python
   import struct
   with open("mod_out/Asset.uexp", "rb") as f:
       data = f.read()
   for val in [100, 20, 15, 10]:
       encoded = struct.pack('<i', val)
       offsets = [i for i in range(len(data)-3) if data[i:i+4] == encoded]
       print(f"Value {val}: offsets {offsets}")
   ```

### CDO patches don't take effect
1. **Parent blueprint MUST be present** — `MTVehicleBaseBP.uasset` + `.uexp` must be in the same directory as the target blueprint during patching. Without it, CDO reparse fails with schema resolution errors
2. **Schema gaps in `Mappings.usmap`** — Some structs like `MTVehicleColorSlot` have incomplete schemas. The patcher will fail with `FormatException` unless `MainSerializer.cs` is modified to skip unknown properties (return `null` with a warning instead of throwing)
3. Use `--dump` to verify the import was added (look for the asset name in imports)
4. Use `--dump` to verify CDO size changed (compare with original)
5. For inherited properties, ensure you used `set_or_create_import_ref` (not `set_import_ref`)
6. Check CDO loads as `RawExport` — if reparse failed, the property was NOT added
7. **Use `set_or_add_float` for new float properties** — `set_float` is not a valid op. For adding properties like `HornFadeInSeconds`, use `set_or_add_float` which creates the property if it doesn't exist
8. **Some vehicle types can't be CDO-patched** — Bikes, karts, and trailers have different parent classes that don't include `HornSound` in their schema. These will fail even with `MTVehicleBaseBP` present

## Key Files

| File | Purpose |
|------|---------|
| `AGENTS.md` | Build commands, Nix dev shell, full pipeline docs |
| `src/bin/mod_pack.rs` | PAK creator (V11, mount `../../../`) |
| `src/bin/mod_explore.rs` | PAK reader/extractor for mod analysis |
| `csharp/UAssetTool/Program.cs` | Core UAsset manipulation tool |
| `motortown.db` | SQLite database of parsed game data |
| `out/` | Extracted base game assets (templates) |
| `scripts/` | Python build pipeline scripts |
