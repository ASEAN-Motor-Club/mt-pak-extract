# Duro UT — client-side Motor Town vehicle mod (0.7.20)

A buyable, bedless **Duro UT** for the 0.7.20 client: a clone of the vanilla Duro with
swappable Dump and Tanker bodies, sold for 1 credit at Gosan. The vanilla Duro is never
touched and keeps its bed.

Status: the vehicle, its sales row and its buy-anywhere dealer bay all work in game.
Part compatibility and the cargo-bed menu are the open items (see **Open work**).

## What ships

| Piece | Path | Notes |
|---|---|---|
| Vehicle pak | `zzz_AMC_DuroUT_v1.0.10_0.7.20_P.pak` (built, not committed) | class + meshes + tables |
| Dealer bay | `ue4ss/DuroBay/main.lua` | UE4SS Lua, spawns the native dealer point |

Both are needed: the pak gives you the truck, the Lua gives you somewhere to buy it.

## Architecture

**Cloned class, not a patched Duro.** `scripts/clone_dut1.py` does same-length byte
surgery on the vanilla `Duro` blueprint (`Duro` → `DUT1`, 4 chars both ways), so meshes
cook to `/Game/Cars/Models/DUT1/*` and the vanilla `/Game/Cars/Models/Duro/*` paths stay
stock. The cloned BP must live in its own folder, not the donor's.

**Sales row** `Duro_UT_AMC1` in `DataAsset/Vehicles/Vehicles_Truck`, `Cost = 1`,
`VehicleClass = /Game/Cars/Models/DUT1/DUT1.DUT1_C`. That is what puts it in Motorpedia
and the garage list.

**Dealer bay** is spawned at runtime by `ue4ss/DuroBay/main.lua`:
`StaticFindObject("/Game/Cars/Models/DUT1/DUT1.DUT1_C")` →
`world:SpawnActor(MTDealerVehicleSpawnPoint, Location, Rotation)` → `SetVehicleClass(cls)`.
Location `-388065, 103586, -21880` (next to the Brutus tanker at Gosan).

The pak-based dealer route (`ReservedRegistration/Slots/SlotNN` + framework pak) is
**dead for 0.7.20**: 0.7.19-authored dealer components lack the `VehicleClasses` array
that 0.7.20's actor has, and any populated slot crashes the client with
`EXCEPTION_ACCESS_VIOLATION` on world entry. Do not resurrect it.

## The 0.7.20 DataTable rules that cost the most time

1. **`DataAsset/VehicleParts/VehicleParts` is a `CompositeDataTable`.** It rebuilds its
   rows from its parent tables on load, so *anything written into the composite is
   discarded*. Row edits must go into the child tables:
   `AeroParts`, `VehicleParts0`, `Wheels`, `CargoBed`, `CargoBedAttachments`, `Engines`,
   `Transmissions`, `Horns`, `License`, `UtilityParts`, `Headlights`, `Suspensions`,
   `LSD`, `FinalDriveRatio`, `BrakeBalance`, `BrakePads`, `BrakePower`, `AeroParts`.
2. **Paths are not what the names suggest.** The parts tables live under
   `MotorTown/Content/DataAsset/VehicleParts/<Name>`. There is no
   `DataAsset/VehicleParts.uasset` and no `DataAsset/CargoBedAttachments.uasset` —
   shipping to those paths is silently ignored.
3. **Part compatibility is an allowlist of row names, not classes.**
   Each part row carries `VehicleKeys: ["Duro"]`. A vehicle row named `Duro_UT_AMC1`
   matches nothing until `Duro_UT_AMC1` is added to those arrays. Symptom: the
   "Incompatible Parts" dialog lists even the wheels the truck is wearing, and the
   Parts menu is empty.
4. **The cargo-bed menu needs a slot AND a real part in it.** The vehicle row's `Parts`
   map (slot enum → part row name) is the slot list. Duro has 23 slots and **no
   `CargoBed0`** — only Voltex/Kira/Gunthoo do. Adding `CargoBed0` is necessary but not
   sufficient: with the value `None` the game builds no category at all (verified in
   game — the slot exists in the row, the Workshop still shows nothing, and the
   modded-parts dialog lists a nameless "Cargo Bed"). Point the slot at a real bed row
   (`configs/vt_cargobed_default.json` → `Duro_CargoBed_Dump`) and the category appears
   with that bed fitted and the other compatible beds as swaps.
5. **Swappable beds are `PartType::CargoBed` rows in `DataAsset/VehicleParts/CargoBed`**
   (Voltex/Kira/Tank...), not `CargoBedAttachment` rows. Clone `Kira_Flatbed_01` for a
   dump body and `Kira_Tank_01` for a tanker so the row struct matches.

## Build

Prerequisites: the 0.7.20 pak extracted in `mt-pak-extract-wt-0720` (`out/`), the
`UAssetTool` fork built from `csharp/UAssetTool` (its `obj/` in the shared repo is
root-owned — build in a copy), `mod_pack`, and the DUT1 meshes cooked into
`/var/lib/durocook`.

```bash
# 0. author the two rear bodies, then prove no closed island is inside-out
#    (make_bodies.py writes into scripts/obj/)
python3 mods/duro-ut/scripts/make_bodies.py
python3 mods/duro-ut/scripts/check_winding.py mods/duro-ut/scripts/obj/duro_dump_body.obj
python3 mods/duro-ut/scripts/check_winding.py mods/duro-ut/scripts/obj/duro_tanker_body.obj

# 1. clone the class (byte surgery on the vanilla Duro BP)
python3 mods/duro-ut/scripts/clone_dut1.py

# 2. patch the four child tables so the Duro rows accept Duro_UT_AMC1
#    (configs/keys_*.json, --patch-rows, one invocation per table)

# 3. add the two beds to CargoBed (configs/cargobed_rows.json, --add-rows,
#    templates Kira_Flatbed_01 and Kira_Tank_01)

# 4. add the CargoBed0 slot to the vehicle row (configs/vt_cargobed_slot.json,
#    --patch-rows on Vehicles_Truck)

# 5. pack: mod_pack stage/ zzz_AMC_DuroUT_vX_0.7.20_P.pak
```

Every row edit must be re-dumped from the **packed** pak, not the build tree, and the
patch is proven by the dump showing `Duro_UT_AMC1` inside `VehicleKeys`.

## Open work

- **Chassis-only ("no bed") option.** The truck now defaults to the dump body because a
  slot holding `None` produces no category. A bedless default needs an extra
  `CargoBed` row whose `Aero.Mesh` is null-reffed and whose cargo-space size is zero, so
  the slot resolves to something the player can pick. Not built yet — a mesh-less bed row
  is unproven and must not be the default on a fresh buy until it is.
- **Tanker body inside-out (fixed in v1.0.9, needs a look in game).** The cylinder and
  both dished heads in `make_bodies.py` were wound backwards, so the barrel rendered
  from the inside. `scripts/check_winding.py` finds this class of bug: every *closed*
  island of an OBJ is signed-volume tested, and a negative volume means inside-out.
  Verify with `python3 scripts/check_winding.py <obj>` — all islands must read
  `closed … vol=+…`. Do not "fix" an open island by volume; its volume is meaningless.
- **Tanker collision.** The barrel is a single 216-face closed island; auto-generated
  convex collision from it is coarse. Not yet compared against the dumped body's own
  collision.
- **Rear bulkhead.** Trim the wall behind the seats down to the shell.
- **`M_Palette`** atlas binding gives a red SCM badge and an over-bright grille;
  cosmetic, deliberately deferred.

## Pak history (0.7.20)

| Version | Change | Outcome |
|---|---|---|
| v1.0.0–1.0.3 | slot-based bay + framework paks | truck visible, bay never appeared, crashes |
| v1.0.4 | first VehicleKeys patch, wrong table paths | no effect (silently ignored) |
| v1.0.5 | patched the composite | no effect — composite rows are rebuilt |
| v1.0.6 | patched AeroParts / VehicleParts0 / Wheels / CargoBedAttachments | aero parts and hitches accepted |
| v1.0.7 | beds added to CargoBed | no menu — no `CargoBed0` slot |
| v1.0.8 | `CargoBed0 = None` slot added | pending in-game test |
| v1.0.9 | tanker barrel/heads re-wound (source was inside-out) | pending in-game test |
| v1.0.10 | `CargoBed0` set to a real bed row (`Duro_CargoBed_Dump`) | category now exists; `None` produced none |
