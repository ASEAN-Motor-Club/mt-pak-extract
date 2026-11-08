# C1 Shuto — release v2 (Motor Town 0.7.19)

Rebuilt map plus a matching dedicated-server pak. The 2026-11-03 paks are
untouched and remain valid rollback targets.

## Artifacts

Client: `zzz_AMC_C1_v2_P.pak` — 207,588,621 B / 10,039 records
sha256 `96a2baba031ff0839225ef741dc3b43c4d3e73b85f76a3c4a08f65427514b988`

Server: `zzz_AMC_C1_Server_v2_P.pak` — 62,319,274 B / 8,056 records
sha256 `ce98ed0f73bf9bb12621955d2f867ea79dc461af833ec838a6ed04afd3af1cf4`

Both mount `../../../MotorTown/Content/Mods/C1/`. Published to
`/var/lib/mod-releases/mods/` and served at
`https://www.aseanmotorclub.com/releases/mods/<name>.pak`.

## Client install

Replace `zzz_AMC_C1_P.pak` with `zzz_AMC_C1_v2_P.pak` (keeping both works — `v2`
sorts later and wins). Keep `zzzz_AMC_C1Mats_P.pak`. Remove any
`zzzz_AMC_C1Test*.pak`.

## Server install

`enableExternalMods.zzz_AMC_C1_Server_v2_P = true;` and drop
`zzz_AMC_C1_Server_P` from that block. `install-mt-mods` caches by filename, so the
new name is required to get a fresh download. Takes effect on the next server
restart.

## What changed vs 2026-11-03

- Roads authored natively in the C1 package: no Nordschleife `MotorTownRoad`
  export, no `MTHouse`, no `MTAreaVolume` (verified 0 occurrences). 27
  lane-segmented splines in a new `Maps/C1_Roads` sublevel that `C1.umap` streams.
- `C1_Course` (closed `Track_Course`, 1,379 points, `CourseKey=C1Shuto`) and 40
  `MotorTownRaceSection` gates; navigation baked.
- Garage restored, lowered 100 units to Z 85,843.7.
- Sun raised 105,943 -> 300,000 (geometry tops out at 121,200; the dome centre was
  153 m below the highest ridge).
- `WorldSettings.DefaultGameMode`, `SunSky.ChildActorClass`,
  `Child.ChildActorClass` restored — without them the map loads black.

## Verification

- Client pak: 10,039 records, compresses 532 MB -> 207.6 MB.
- Server pak built by the documented pipeline: WindowsServer cook with
  `CLIENT_COOK_UNCHANGED=True`, records derived from the new client pak,
  `staged=8056 missing=0`, `CLIENT_PAK_UNCHANGED=True`.
- Server record set is a strict subset of the client set, 0 extras, 0 `.ubulk`.
- All six `Maps/*` files byte-identical between client and server paks.
- Client packages are versioned (`PackageFlags 0x80000200`, unversioned-props
  clear), which is why reusing client map bytes server-side is safe here.
- Pre-existing release paks re checksummed after publish: all `OK`.

## Not in this release

Course registration in `Courses/GameResource` (the map enters and renders but is
not a registered race course), tow, and AI traffic.
