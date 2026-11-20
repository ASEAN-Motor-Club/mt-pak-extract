# Duro UT — client-side Motor Town vehicle mod (0.7.20)

A buyable, bedless **Duro UT** for the 0.7.20 client: a clone of the vanilla Duro with
swappable Dump and Tanker bodies, sold for 1 credit at Gosan. The vanilla Duro is never
touched and keeps its bed.

Status: the vehicle, its sales row and its buy-anywhere dealer bay all work in game.
Part compatibility and the cargo-bed menu are the open items (see **Open work**).

## What ships

| Piece | Path | Notes |
|---|---|---|
| Vehicle pak | `zzz_AMC_DuroUT_v1.0.15_0.7.20_P.pak` (built, not committed) | class + meshes + tables |
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
6. **The bed menu depends on `CargoBedAttachments`, and `Duro_CargoBedAttachment_01` is
   the game's "Toolbox" attachment.** That single `CargoBedAttachment` row carries the
   display text `Toolbox`; with `Duro_UT_AMC1` in its `VehicleKeys` it shows up as a third
   entry in the bed list, which is the shipped behaviour. Three attempts to remove that
   entry all killed the whole bed menu: omitting the table (v1.0.11), shipping it
   unpatched (v1.0.12), and renaming the row (v1.0.13 — `set_display_name` +
   `set_localization_guid` write a synthetic string-table guid, and the row stops
   resolving). Treat the row's data as load-bearing for the group and do not touch it.

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

- **Cargo-bed menu is class-side, not row-side (v1.0.11 test).** Adding
  `EMTVehiclePartSlot::CargoBed0` to the vehicle row does nothing for a Duro: the DUT1
  class only enumerates `Bonnet, Bullbar, CargoBedAttachment0, Fender, FrontBumper,
  RearBumper, Roof, SideSkirt` (see the class dump's `EMTVehiclePartSlot::` names).
  Swappable-bed vehicles are `CargoBed0` vehicles; the Duro's bed lives on
  `CargoBedAttachment0`. So beds must be `PartType::CargoBedAttachment` rows in
  `CargoBedAttachments` and the row needs `CargoBedAttachment0`, which v1.0.11 does.
  If the category still does not appear, the remaining suspect is the BP's part-slot
  component set, not any DataTable.
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
- **"Toolbox" entry in the bed list** — left as-is on purpose. The row doubles as the
  vehicle's `CargoBedAttachment` and removing or renaming it takes the whole bed menu
  with it.
- **Material slots** — the grille, SCM badge, mirrors and window sills are *not* a
  slot-assignment problem: the vanilla Duro paints them with `M_Palette` too. Their
  colour comes from the shared PolygonCity atlas, so they need correct UVs, not a
  different material. See "Mesh import rules" — fixed in v1.0.14.

## Mesh import rules

- **Flip V when leaving glTF.** glTF texture space starts at the image's top-left and
  grows v downwards; UE's starts bottom-left and grows upwards. Copying glTF
  `TEXCOORD_n` straight into an FBX mirrors every texture. The Duro body showed it
  plainly: its `Palette` geometry covers glTF v 0.5..1.0, which is the paint-ramp area
  of the shared PolygonCity atlas. Unflipped it samples v 0..0.5 instead — signage
  tiles and empty padding — which is exactly the red badge and blown-out grille.
  `scripts/uv_atlas_probe.py` samples the atlas at each polygon's UVs and prints the
  colour stats plus an overlay; run it before cooking. Unflipped: near-white 60%+ on
  the paint zones. Flipped: 0% near-white, colours from the ramps.
- **FBX layers are per polygon-vertex, not per control point.** Declaring
  `MappingInformationType: "ByPolygonVertex"` while writing one entry per deduplicated
  control point makes the importer misindex normals, colours and UVs. Emit one entry
  per polygon corner (`glb_to_fbx.py` does this as of v1.0.14).
- **Expanding `Vertices` per corner means rewriting `PolygonVertexIndex`.** Once the
  vertex array is unwelded, the corner list is `0,1,2 / 3,4,5 ...` and each polygon's
  last index is encoded as `-(k+1)`. Leaving the old deduplicated point indices in place
  connects unrelated vertices: the shell renders as a crumpled translucent wreck while
  the vertex count and bounds still look right. Check triangle edge statistics instead —
  the known-good body has median 5.24, p99 90.7, max 351.4 cm; the broken export was
  p99 218, max 602.
- **Only the body comes from the glb route.** Beds, tailgate stub and the rest of the
  truck are procedural OBJ (`make_bodies.py`), and every one of those materials is
  untextured `M_Body`, so their `vt 0 0` is harmless.

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
| v1.0.11 | dropped the `CargoBedAttachments` table from the pak | bed menu disappeared — the table's contents govern the group |
| v1.0.12 | vanilla (unpatched) `CargoBedAttachments` | bed menu disappeared |
| v1.0.13 | table restored, `Duro_CargoBedAttachment_01` renamed | menu gone again; reverted |
| v1.0.14 | body re-imported from a per-corner FBX with UE-space (V-flipped) UVs | **broken, do not ship** — expanding `Vertices` per corner without rewriting `PolygonVertexIndex` crumpled the shell |
| v1.0.15 | same UV fix, polygon indices rewritten for the per-corner vertex array | textures sample the paint ramps; geometry matches v1.0.10 |
