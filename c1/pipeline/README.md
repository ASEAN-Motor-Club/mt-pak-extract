# C1 build pipeline

Reproducible stages for the C1 Shuto map. Design rationale, constants and the
full failure history are in [`../docs/C1_PIPELINE.md`](../docs/C1_PIPELINE.md) —
read that before changing anything here.

```
00_env.sh              paths + tool locations; source it, don't run it
01_decal_specs.sh      BeamNG items.level.json -> road specs
02_author_roads.sh     spawn MotorTownRoad actors (editor)
03_bake_nav.sh         bake GraphData (editor) — asserts the 4 counts
04_author_spawner.sh   author AMTAIVehicleSpawnSystem (editor)
05_cook.ps1            cook the sublevel (Windows, mirror project)
06_postcook_patch.sh   class refs + spawner VehicleClass
07_pack.sh             compressed pak (repak, V11, zlib)
08_deploy_staging.sh   install into .mod-cache (restart gated by RESTART=1)
09_verify.sh           pak contents + live server probe
run_all.sh             driver
```

## Quick start

```bash
# editor side: rebuild roads, graph and spawner
./run_all.sh author

# build side: cook → patch → pack
./run_all.sh build

# verify the pak and the live server
./run_all.sh verify /path/to/pak
```

## Rules that must not be relaxed

- **`dead_ends == 0`** is the only graph property that has predicted in-game
  behaviour. Stage 3 fails without it.
- **Counts must match `constants.json:expected`.** Drift after a road-set change is
  expected — re-record the baseline in the same commit as the change. Drift without
  a road-set change means something moved that shouldn't have.
- **Never reboot/restart a shared server implicitly.** Stage 8 only stages unless
  `RESTART=1`.
- **Never bind vehicle classes at runtime.** Stage 6 patches the cooked package.
- **Keep the pak filename stable while iterating** (`zzz_AMC_C1_Server_v3_P.pak`).
  Version it only at publish time.

## Determinism

Roads are sampled **sorted by actor label**, so node indices and edges are
reproducible for a given level + constants. Pak bytes are not: the UE cook embeds
build/timestamp data. Verify content (file list, `.uexp` size, property values,
counts), never pak hashes across rebuilds.
