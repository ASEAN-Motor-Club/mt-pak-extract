# Get AI traffic spawning on the C1Full (Shuto) dedicated server

Plan owner: Yumemi. Written 2026-11-13 10:20 UTC.
Target instance: `motortown-server-shuto` on `amc-peripheral` (`root@host.docker.internal`).

---

## Goal

Make AI traffic appear in the running world of the `motortown-server-shuto` instance, proven by
runtime evidence (traffic-flagged vehicle actors > 0 near a connected player), and leave the
build/pak pipeline in a state where the fix survives the next rebuild.

## Current context / assumptions

Read this before touching anything. Every item below is *measured*, not assumed.

- **Instance**: `motortown-server-shuto`, state dir `/var/lib/motortown-server-shuto`, pak dir
  `/var/lib/motortown-server-shuto/MotorTown/Content/Paks/`. Running
  `zzz_AMC_Shuto_Server_v4_P.pak` (389,480,573 B) since 2026-11-13 10:04 UTC.
- **Map**: parent `/Game/Mods/C1Full/Maps/C1Full`, sublevel `C1Full_Roads`
  (`LevelStreamingAlwaysLoaded`, `bShouldBeLoaded: True`).
- **Config**: `NPCVehicleDensity = 1.0` in the running `DedicatedServerConfig.json`. Live admin
  toggles of `GameMode_NPCVehicleDensity` (1.0 → 0.9 → 1.0) produced no traffic. Density is not
  the lever.
- **Vanilla comparison (settled)**: Jeju's `MTAIVehicleSpawnSystem` has 16 rows and **every row
  has `VehicleClass = Index=0` (null)**, `SpawnType: None` on the traffic rows, `MaxCount`
  250/5/50/50/1, `MinCount -1`, `bUseNPCVehicleDensity: True` on the four traffic rows. Our map's
  rows are the same values. **Null class refs are normal and are NOT the bug.** An earlier patch
  that added `Stinger_C`/`Campy_C`/`Liliput_C` refs (v2/v4 paks) is a no-op and must not be
  "fixed" again.
- **Nav graph present**: `MotorTownNavigation_0` in `C1Full_Roads`, `GraphData` 36,571,359 B,
  40,062 nodes / 78,787 edges, 0 isolated nodes, field-for-field identical schema to vanilla
  (which has 17,619 nodes). Map bytes in the server pak are byte-identical to the client pak.
- **The one categorical difference from vanilla**: road lane counts. Ours: 154 roads at
  `NumForwardLanes=2 / NumBackwardLanes=0`, one 3/0, one 4/0 — the whole network is one-way.
  Vanilla: 456 of 490 roads leave the lanes at class defaults (two-way), 31 explicit 2/2, only 2
  at 2/0.
- **Diagnostic already installed (not yet exercised)**: UE4SS Lua mod `AITrafficProbe` at
  `/var/lib/motortown-server-shuto/MotorTown/Binaries/Win64/ue4ss/Mods/AITrafficProbe/`
  (`enabled.txt` + `scripts/main.lua`, owner `steam:oauth2-proxy`), and `AITrafficProbe : 1`
  appended to `Mods/mods.txt` (backup `Mods/mods.txt.bak_preaitprobe`). It logs every 15 s, 120
  ticks, to `UE4SS.log`.

### Hard rules (do not violate)

- **Never restart the Motor Town server yourself.** `systemctl restart motortown-server-shuto`
  is user-only. Ask, wait, then read logs.
- **No inline secrets / inline env-assignments / plain-HTTP hosts / kill commands** in terminal
  calls. Use `/opt/data/scripts/hostprobe.sh`, `/opt/data/scripts/hostrun.sh`,
  `/opt/data/cache/scratch/repak_aes.sh`, `/opt/data/cache/scratch/repak_aes_oodle.sh`.
- **Never dump `Jeju_World.umap` inside the container** — 8 GB cap, it OOMs (exit 134). The
  working recipe is on the host:
  `ssh root@host.docker.internal "cd /opt/data/workspace/mt-pak-wt-c1commit && /run/current-system/sw/bin/nix develop --command bash -c 'cd /opt/data/cache/scratch/uatt_home && export HOME=\$PWD DOTNET_ROLL_FORWARD=Major DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 && dotnet …/UAssetTool.dll --dump /opt/data/cache/scratch/uatt_home/Jeju_World.umap > /opt/data/cache/scratch/jeju_dump_host.txt 2>&1'"`.
- **New server pak ⇒ new filename.** `install-mt-mods` is cache-first; reusing a name means the
  new bytes are never fetched. Current chain: `_v3_P` (stale) → `_v4_P` (running) → next is
  `_v5_P`.
- **UAssetTool must run with `Mappings.usmap` in the CWD** (`/opt/data/cache/scratch/uatt_home`)
  and needs `DOTNET_ROLL_FORWARD=Major`, `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`.
- Server state dir files must be owned by `steam:oauth2-proxy`, or the service cannot overwrite
  them.

## Architecture / proposed approach

Run a evidence-first loop: the probe answers *which* link is broken (spawner not bound → rows
missing → sim not spawning → sim spawning but failing), then apply exactly one minimal change per
iteration — config first (cheap, deploy-only), map second (rebuild + new pak), engine third — and
re-probe. Each iteration ends with a published, uniquely-named server pak and a user restart
request. Stop when the probe reports traffic-flagged `MTVehicle` actors > 0 while a player is
connected; then fold the winning change into the pipeline so it survives the next full rebuild.

---

## Step-by-step tasks

### Task 1 — Collect the first probe log (no restart needed if already restarted)

The probe is installed but the server has not been restarted since. Confirm state first:

```bash
ssh root@host.docker.internal "systemctl show motortown-server-shuto -p ActiveEnterTimestamp --no-pager; ls -l /var/lib/motortown-server-shuto/MotorTown/Binaries/Win64/ue4ss/Mods/AITrafficProbe/scripts/main.lua"
```

Expected: `ActiveEnterTimestamp` **later** than 2026-11-13 10:19 UTC (the install time). If it is
earlier, the probe has never loaded — stop and ask the user for a restart, then re-run.

Read the probe output:

```bash
ssh root@host.docker.internal "grep -a '\[AITrafficProbe\]' /var/lib/motortown-server-shuto/MotorTown/Binaries/Win64/ue4ss/UE4SS.log | tail -60"
```

Expected first block (abridged):

```
[AITrafficProbe] t=0 loaded, first probe in 15s
[AITrafficProbe] t=1 GameState: MotorTownGameState /Game/Maps/C1Full.C1Full:PersistentLevel....
[AITrafficProbe] t=1 GameState.AIVehicleSpawnSystem: MTAIVehicleSpawnSystem_1 … valid=true
[AITrafficProbe] t=1 SpawnSettings rows: 16
[AITrafficProbe] t=1   row 0 key=Small type=EMTAIVehicleSpawnType::None class=nil vtypes=2 max=250 min=-1 density=true traffic=true
[AITrafficProbe] t=1 MTVehicle actors: N (bIsTrafficVehicle=0 bSpawnAIController=0)
[AITrafficProbe] t=1 MotorTownRoad actors: 156
[AITrafficProbe] t=1   nav MotorTownNavigation_0 … graphNodes=40062
```

If no `[AITrafficProbe]` lines exist at all, the mod did not load: check
`grep -ai 'AITrafficProbe' …/UE4SS.log` and `cat …/Mods/mods.txt`; if `Mods/` was reset by a
deploy, re-install from `/opt/data/cache/scratch/AITrafficProbe/` (see Task 8).

### Task 2 — Classify the failure from the probe (decision matrix)

Read the t=1 block and pick exactly one row:

- `GameState: NOT FOUND` → the probe ran before the world existed; wait for a later tick. If it
  never appears, the mod loaded too early — bump the first delay to 60 s and reinstall.
- `GameState.AIVehicleSpawnSystem: nil` → **spawner never bound.** Go to Task 5.
- `SpawnSettings rows: 0` (or unreadable) → **the actor is a different instance than the cooked
  one / the sublevel isn't loaded.** Check the `nav … graphNodes=` line in the same block: if it
  also reports `-1`/NOT FOUND, `C1Full_Roads` is not in the world → Task 6.
- `SpawnSettings rows: 16`, `class=nil`, `density=true`, `traffic=true`, but
  `MTVehicle actors: N (bIsTrafficVehicle=0 …)` → **the sim sees correct settings and is not
  spawning.** Go to Task 3.
- `bIsTrafficVehicle` > 0 but the user sees nothing → traffic exists server-side; the problem is
  the client pak or replication. Stop and report.

Record the classification in the plan's own log file:
`/opt/data/cache/scratch/traffic_iteration_log.md` (append date, change, probe verdict).

### Task 3 — Candidate fix A: give the instance the traffic cvars production has

`/opt/data/workspace/amc-deploy/flake.nix` — the shuto block is around lines 1089–1160
(`mapName = "/Game/Mods/C1Full/Maps/C1Full"`, `stateDirectory = "motortown-server-shuto"`). It has
`enableExternalMods` but **no `engineIni`**. Production (≈ lines 404–411) and the C1 instance
(≈ lines 1275–1283) both set:

```nix
            engineIni = ''
              mh.trafficSpawnVehicleMaxDistance=40000.0
              mh.trafficSpawnVehicleMinDistance=25000.0
              mh.trafficAgentMaxTickDeltaSeconds=5.0
              mh.trafficTickPerFrame=20.0
            '';
```

Edit:

1. `cd /opt/data/workspace/amc-deploy && git checkout master && git pull --ff-only`
2. Insert the block above into the **shuto** instance block, next to `enableExternalMods`.
   Verify placement:

```bash
cd /opt/data/workspace/amc-deploy && sed -n '1089,1165p' flake.nix | grep -nE "engineIni|mh\.traffic|stateDirectory|enableExternalMods"
```

Expected: four `mh.traffic*` lines inside the block whose `stateDirectory = "motortown-server-shuto"`.

3. Validate the flake parses (no build):

```bash
cd /opt/data/workspace/amc-deploy && /run/current-system/sw/bin/nix flake check --no-build 2>&1 | tail -5
```

Expected: no `error:` lines (evaluation warnings are fine).

4. Commit and push to `master` via the normal PR flow (AMC repos: PR only, never direct commit to
   master; ask the user for merge authority before merging).
5. Deploy (**needs the user's go**, it restarts the unit):

```bash
cd /opt/data/workspace/amc-deploy && /run/current-system/sw/bin/nix develop --command deploy root@amc-peripheral
```

6. Verify the cvar file actually reached the state dir:

```bash
ssh root@host.docker.internal "grep -n 'traffic' /var/lib/motortown-server-shuto/MotorTown/Saved/Config/WindowsServer/Engine.ini"
```

Expected: four `mh.traffic*` lines. Then re-run Task 1 on the next restart.

### Task 4 — Candidate fix B: two-way roads (only if Task 3 shows settings-but-no-spawn persists)

Hypothesis: the sim builds lane sets from `NumForwardLanes`/`NumBackwardLanes`; a network that is
100 % one-way (`bwd = 0`) yields no lane to place a vehicle in.

Do **not** rebuild the map through the editor for a test. Patch the cooked sublevel directly,
exactly like the class-ref step:

1. Extract the map from the current client pak into a scratch pair (keep `.umap` and `.uexp`
   beside each other, matching basenames):

```bash
cd /opt/data/cache/scratch && rm -rf roadfix && mkdir roadfix && cd roadfix && \
R=/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak && \
for e in umap uexp; do $R get /opt/data/releases/c1/pakset_release_v2/zzz_AMC_Shuto_P.pak \
  "MotorTown/Content/Mods/C1Full/Maps/C1Full_Roads.$e" > "C1Full_Roads.$e"; done && ls -l
```

Expected: `C1Full_Roads.umap` 49,394 B, `C1Full_Roads.uexp` 57,027,114 B.

2. Patch `NumBackwardLanes` to 2 on every `MotorTownRoad_*` export. Add a small operation to
   `csharp/UAssetTool/Program.cs` modelled on the existing `--set-array-class-ref` handler
   (`Program.cs:3397` area): new switch `--set-int-prop <in.umap> <out.umap> <classFilter> <propName> <value> <skipIfClassMissing>`,
   iterating `asset.Exports`, matching `Export.ClassIndex` resolved to class name `MotorTownRoad`,
   then `SetIntProperty(propName, value)` (creating the property if absent via
   `set_or_create`), printing `SETINTPROP_OK <count> exports`.
3. Build and run:

```bash
cd /opt/data/workspace/mt-pak-wt-c1commit/csharp/UAssetTool && dotnet build -c Release 2>&1 | tail -2
cd /opt/data/cache/scratch/uatt_home && HOME=$PWD DOTNET_ROLL_FORWARD=Major DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 \
  /opt/data/dotnet10/dotnet /opt/data/workspace/mt-pak-wt-c1commit/csharp/UAssetTool/bin/Release/net8.0/UAssetTool.dll \
  --set-int-prop /opt/data/cache/scratch/roadfix/C1Full_Roads.umap \
                 /opt/data/cache/scratch/roadfix/C1Full_Roads_patched.umap \
                 MotorTownRoad NumBackwardLanes 2
```

Expected: `SETINTPROP_OK 156 exports`.

4. Verify by dump:

```bash
cd /opt/data/cache/scratch/uatt_home && cp /opt/data/cache/scratch/roadfix/C1Full_Roads_patched.u* . && \
bash /opt/data/cache/scratch/dump.sh /opt/data/cache/scratch/uatt_home/C1Full_Roads_patched.umap > /tmp/roadfix_dump.txt 2>&1; \
grep -c "NumBackwardLanes (Int): 2" /tmp/roadfix_dump.txt
```

Expected: `156`.

5. Rebuild both paks as `_v5` into a new canonical dir (see Task 7), publish, ask for a restart,
   re-run Task 1.

### Task 5 — Candidate fix C: spawner binding (persistent level)

Evidence for this: vanilla keeps its spawner in the persistent level (`Jeju_World`), ours lives in
the streamed sublevel `C1Full_Roads`. If the probe reports
`GameState.AIVehicleSpawnSystem: nil`, the GameState never bound ours.

1. Confirm the persistent level has none:

```bash
grep -c "Class=MTAIVehicleSpawnSystem" /tmp/parent_dump.txt
```

Expected: `0` (regenerate with the host dump recipe if the file is missing).

2. Cheapest test in the editor: open `D:\C1FullMirror`, duplicate `MTAIVehicleSpawnSystem_1` from
   `C1Full_Roads` into the `C1Full` persistent level at the Shibaura origin
   (`110237, -470902, 87510.6`), save both levels, then run the cook + stage + pack path
   (`c1/pipeline/05_cook.ps1` → `stage_c1full_v2.ps1` → repak). This is a real editor change —
   only do it after Tasks 3 and 4 have been ruled out, because it invalidates the "map bytes ==
   client pak" guarantee until the client pak is rebuilt too.

3. Re-probe. Expected on success: `GameState.AIVehicleSpawnSystem: … valid=true` **and** rows 16.

### Task 6 — Candidate fix D: sublevel not in the dedicated world

If the probe shows `MotorTownNavigation` NOT FOUND too, the sublevel is not mounted. Check the
persistent level's streaming list again (it already says AlwaysLoaded / `bShouldBeLoaded: True`),
then check the server log for the sublevel name:

```bash
ssh root@host.docker.internal "grep -ai 'C1Full_Roads' /var/lib/motortown-server-shuto/MotorTown/Saved/ServerLog/*.log | tail -5"
```

If nothing appears, the pak may not be mounting. Verify with a canary:
`ssh root@host.docker.internal "ls -l /var/lib/motortown-server-shuto/MotorTown/Content/Paks/"` and
confirm the serviced instance's pak mtime matches the deployed copy.

### Task 7 — Rebuild + publish a new server pak (used by Tasks 3–6)

Trees are live at `/opt/data/cache/scratch/relmerge/{tree,srvtree}`.

```bash
cd /opt/data/cache/scratch/relmerge && R=/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak && \
mkdir -p /opt/data/releases/c1/pakset_release_v3 && \
$R pack tree   /opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_P.pak        --version V11 --mount-point "../../../" --compression Zlib --path-hash-seed 0 && \
$R pack srvtree /opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_Server_v5_P.pak --version V11 --mount-point "../../../" --compression Zlib --path-hash-seed 0
```

Expected: `Packed 11341 files` and `Packed 9524 files`.

Gates (all must pass before publishing):

```bash
cd /opt/data/cache/scratch/relmerge && R=/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak && \
C=/opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_P.pak && \
S=/opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_Server_v5_P.pak && \
echo "client=$($R list $C | wc -l) server=$($R list $S | wc -l) shader=$($R list $C | grep -c ShaderArchive)" && \
for e in umap uexp; do a=$($R get $C "MotorTown/Content/Mods/C1Full/Maps/C1Full_Roads.$e" | sha256sum) ; b=$($R get $S "MotorTown/Content/Mods/C1Full/Maps/C1Full_Roads.$e" | sha256sum); [ "$a" = "$b" ] && echo "map $e identical"; done
```

Expected: `client=11341 server=9524 shader=0`, then two `map umap/uexp identical` lines.

Publish:

```bash
sha256sum /opt/data/releases/c1/pakset_release_v3/*.pak > /opt/data/releases/c1/pakset_release_v3/sha256.txt
ssh root@host.docker.internal "cp /opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_P.pak /var/lib/mod-releases/archive/zzz_AMC_Shuto_P_prev_$(date -u +%Y%m%dT%H%M%SZ).pak; cp /opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_P.pak /var/lib/mod-releases/mods/zzz_AMC_Shuto_P.pak; cp /opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_Server_v5_P.pak /var/lib/mod-releases/mods/zzz_AMC_Shuto_Server_v5_P.pak"
```

Verify both URLs return `206` and the right length:

```bash
for f in zzz_AMC_Shuto_P.pak zzz_AMC_Shuto_Server_v5_P.pak; do echo "$f $(curl -sS -o /dev/null -w '%{http_code} %{size_download}' -r 0-1023 https://www.aseanmotorclub.com/releases/mods/$f) $(curl -sSI https://www.aseanmotorclub.com/releases/mods/$f | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}')"; done
```

Expected: `206 1024 <bytes matching sha256.txt>`.

Then bump `enableExternalMods` to `zzz_AMC_Shuto_Server_v5_P = true` in the shuto block, deploy,
and ask the user to restart.

### Task 8 — Reinstalling the probe after a deploy wipes it

```bash
ssh root@host.docker.internal "D=/var/lib/motortown-server-shuto/MotorTown/Binaries/Win64/ue4ss/Mods/AITrafficProbe; rm -rf \$D; mkdir -p \$D/scripts; cp /opt/data/cache/scratch/AITrafficProbe/enabled.txt \$D/; cp /opt/data/cache/scratch/AITrafficProbe/scripts/main.lua \$D/scripts/; chown -R steam:oauth2-proxy \$D; grep -q AITrafficProbe /var/lib/motortown-server-shuto/MotorTown/Binaries/Win64/ue4ss/Mods/mods.txt || echo 'AITrafficProbe : 1' >> /var/lib/motortown-server-shuto/MotorTown/Binaries/Win64/ue4ss/Mods/mods.txt; chown steam:oauth2-proxy /var/lib/motortown-server-shuto/MotorTown/Binaries/Win64/ue4ss/Mods/mods.txt; ls -l \$D/scripts/main.lua"
```

Expected: `main.lua` 4,611 B, `steam oauth2-proxy`.

### Task 9 — Close the loop when traffic appears

1. Capture proof: probe line with `bIsTrafficVehicle` > 0 plus a screenshot request to the user.
2. Fold the winning change into the pipeline so the next full rebuild keeps it:
   - if config: the `engineIni` block stays in `amc-deploy/flake.nix` (already permanent);
   - if lanes: change the road authoring in `c1/pipeline/02_author_roads.sh` (or the
     `constants.json` lane formula) so rebuilt roads are two-way, and re-record
     `constants.json:bake` per `MAP_PORTING_GUIDE.md` §2.5;
   - if spawner placement: add the persistent-level step to `c1/pipeline/04_author_spawner.sh`.
3. Commit to `feat/c1-nav-guards` (no separate PR — standing instruction), with the probe log
   excerpt pasted into the commit message body.
4. Append the outcome to `/opt/data/workspace/mt-pak-wt-c1commit/c1/docs/C1_PORT_LESSONS.md`
   under a new heading "AI traffic did not spawn" with the *evidence chain*, not the guess.

---

## Tests / validation

There is no unit-test surface here; validation is byte-level and runtime evidence.

- **After every pak build** — Task 7 gates: `client=11341 server=9524 shader=0`, both map records
  identical across paks, unpack/diff round-trip `0 differences`:

```bash
cd /opt/data/cache/scratch/relmerge && R=/opt/data/workspace/mt-pak-wt-c1commit/target/release/repak && \
rm -rf rt_c rt_s && $R unpack /opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_P.pak -o rt_c >/dev/null && \
$R unpack /opt/data/releases/c1/pakset_release_v3/zzz_AMC_Shuto_Server_v5_P.pak -o rt_s >/dev/null && \
echo "client_diffs=$(diff -rq tree rt_c | wc -l) server_diffs=$(diff -rq srvtree rt_s | wc -l)"
```

Expected: `client_diffs=0 server_diffs=0`.

- **After every restart** — Task 1 probe read, expecting the t=1 block in full.
- **Success criterion** — all three true in the same probe block:
  `GameState.AIVehicleSpawnSystem` non-nil, `SpawnSettings rows: 16`, and
  `MTVehicle actors: N (bIsTrafficVehicle=M …)` with `M > 0` while a player is connected.
- **Regression gate** — no new `[AITrafficProbe] probe error:` lines in `UE4SS.log`.

## Risks, tradeoffs, and open questions

- **Restart cadence is the bottleneck.** Every iteration costs one user restart. Batch changes per
  iteration (config cvar + probe) rather than one at a time where they are independent.
- **Task 1 might show the probe never loaded.** The `Mods/` tree could be redeployed from the
  flake; the probe is not declarative. Check before concluding anything.
- **The traffic cvars may not exist in the server binary.** `grep -ac trafficSpawnVehicleMaxDistance`
  on `MotorTownServer-Win64-Shipping.exe` returned 0, while `NPCVehicleDensity` appears 5×. If the
  cvars are client-side only, Task 3 is a no-op and Task 4 becomes primary — do not spend a second
  deploy on Task 3 if the Engine.ini verification shows the values written but the probe is
  unchanged.
- **Patching `NumBackwardLanes` may produce wrong-way traffic.** Vanilla's lanes assume right-hand
  driving; the port deliberately reversed spline frames for left-hand driving
  (`MAP_PORTING_GUIDE.md` §2.4). Two-way lanes on a reversed frame could put cars head-on. Treat
  Task 4 as a *diagnosis*, not a shippable fix; if it works, re-author properly.
- **Traffic may be gated on something not visible in static data** (e.g. a game-mode flag we have
  not identified). If Tasks 3–6 all fail, the next step is a native probe through MTDediMod C++
  (`MTDediMod/patches-ue4ss`) hooking the spawn tick — expensive, needs a build and a restart, and
  should be the last resort.
- **Open question for the user**: when traffic last worked, was that offline in single-player or on
  a dedicated server? Offline success + server failure would push diagnosis to the server path
  immediately and skip most of this plan.
