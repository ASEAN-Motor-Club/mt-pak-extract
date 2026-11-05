# C1 map pipeline

Two stages, in this order. Both are required; neither can be skipped.

## 1. Authoring and cooking (editor)

```bat
UnrealEditor-Cmd.exe "D:\UEProjects\C1\C1.uproject" -run=pythonscript ^
  -script="...\pipeline\edit_map.py" -unattended -nosplash -stdout -log
pipeline\cook.bat
```

Cook **in `D:\UEProjects\C1`**. That project can load `/Game/Objects`,
`/Game/GameMode` and `/Game/Blueprints`; the mirror at `D:\C1Mirror` cannot and
silently strips every game-class reference from the map (no game mode -> black
screen, no sun, no garage).

## 2. Class-reference repair (after cook)

```bash
pipeline/repair_class_refs.sh cook_out.umap repaired.umap
```

Restores `WorldSettings.DefaultGameMode`, `SunSky.ChildActorClass` and
`Child.ChildActorClass`.

**Why this cannot be done in the editor.** Setting `child_actor_class` makes the
editor instantiate the child actor, and cooking bakes those instances as real
exports (`MTSunSky_C_0`, `GarageActorBP_C_0`). The game then dies on load:

```
LowLevelFatalError ... UObjectArchetype.cpp [Line: 175]
SceneComponent /Game/Blueprints/MTSunSky.Default__MTSunSky_C:RootSceneComponent
had RF_NeedLoad when being set up as an archetype ...
```

A mod map cannot contain an instance of a game-package blueprint at all -- not as
a child actor and not as a directly placed actor (both verified). Only a class
reference survives, because the child is then spawned at runtime after its
package has loaded. Destroying the children before saving does not help either:
the cook re-creates them.

## 3. Packing

Pack the map plus every cooked asset it references, including the loose
blueprints at the mod root -- a pak containing only `Maps/` leaves the garage
actor without its class:

```
<root>/Maps/C1.umap, C1.uexp
<root>/Maps/C1_Roads.umap, C1_Roads.uexp
<root>/BP_C1_Prop.uasset, .uexp
<root>/BP_C1_Sky.uasset, .uexp
```

```
mod_pack <root>/ out.pak --version V11 --mount "../../../MotorTown/Content/Mods/C1/"
```

## Verifying a candidate map before shipping

Import tables, compared as sets against the last shipped map, must show nothing
missing. `probe/c1probe.lua` (UE4SS) dumps live actors and their locations if the
map loads but something does not appear.
