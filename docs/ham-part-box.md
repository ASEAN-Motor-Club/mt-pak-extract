# Ham's Part Box — merged parts pak (2026-10-21)

One merged client pak that replaces several competing `VehicleParts0`
table paks: **`zzzzzzz_Hams_Part_Box_0.7.19_P.pak`** (353 rows,
pak index V3, mount `../../../`).

## What is inside

Single merged `VehicleParts0` DataTable carrying:

- **TruckerRadi 7.19** (third-party) — vanilla + its rows: winches
  `Winch_06_MMW`, `Winch_Tow_05–08_MMW`, brake upgrades
  `BrakePower300/400/500`, buffed `Winch_Tow_04`, current
  `TruckerRadiator` stats (Cost 1000, CoolingPower 9999), and the
  GATE-family AMC tire rows (Bike/Sport/Stupid/Rally/Truck-DRW/Drift).
- **GATE AMC Tires** rows (already inline in both source tables).
- **PDParts** superchargers `PD_SC_Standard`, `PD_SC_MkII`,
  `PD_SC_Pursuit` (police vehicles, CL_Police 10).
- **AMC Dual Drag Rear** `AMC_HDDual_DragRearTire` + physics asset
  `AMC_HDDual_DragTire` (row cloned from `AMC_Truck_89-DRW`, empty
  filter + `bIsDualRearWheel`).

## Why the merge was needed

The user's `ZZZZZ_TruckerRadi_7.19_P.pak` and the previous
`zzzzzzz_AMC_DualDragRear_v0.9.0_0.7.19_FullCompat_P.pak` BOTH ship a
`VehicleParts0` DataTable. The game loads only one — the other's added
rows silently vanish. Row-level diff (dump vs dump):

- B (TruckerRadi) = superset of A (v0.9.0) except A's own 4 rows
  (drag tire + 3 PD_SC).
- v0.9.0 carried a STALE TruckerRadi snapshot via the More Tuning
  mega-table chain (old `TruckerRadiator` Cost 20000) — B's rows are
  fresher, so B was chosen as the merge BASE.

Build chain (rebased on B): wrap B's table at the standard mount
(`mod_pack`, V3) → `create_intakepack.py --compat-mod <wrapped B>`
(PD_SC rows) → `create_dualdrag_tirepack.py --compat-mod <that>`
(drag row + physics asset). The wrapped pak is then dropped; the
merged pak is the SOLE `VehicleParts0` provider.

**Install rule:** this one pak replaces the old DualDrag FullCompat
pak, TruckerRadi, PDParts, More Tuning, and GATE table paks. Any other
pak shipping `VehicleParts0` reintroduces the race. Non-table paks
(decals, Schedule I, cargo mods) coexist fine.

## Drag tire tuning

Initial build (v0.10.0) used soft drag-launch springs
(SpringX 140k / SpringY 13k, Damping 140/110) — user feedback: too
soft. Test build **v0.10.1** restores the template's truck-tire
suspension character (SpringX 1.2M / SpringY 400k, Damping 800/400)
while keeping drag grip (StaticMu 4.9 / SlidingMu 3.1), instant
warm-up, wear 0.5, offroad 0.2, MaxWeight 8000. Pending in-game
confirmation; if confirmed, fold the values into
`mods/amc-dual-drag/dual_drag_entries.json` and cut a release.

## Build/verify recipe (container)

- Wrapped dep: stage dep's `VehicleParts0.*` under
  `<stage>/MotorTown/Content/DataAsset/VehicleParts/`, pack with
  `target/release/mod_pack` (V3, mount `../../../`).
- In-container dotnet: prebuilt UAssetTool apphost fails
  `libssl.so not found` — rename the apphost aside so
  `run_dotnet` falls back to `dotnet run` with the wrapped
  8.0.416 SDK (`DOTNET_ROOT=<store>/share/dotnet`,
  `PATH=<store>/bin:...`).
- Ship verification: extract the SHIPPED pak into a fresh dir,
  `--dump` the table: row count 353, key rows from both sides,
  `SubPathString: ''` count == 0 (the row-hider bug), footer V3.
