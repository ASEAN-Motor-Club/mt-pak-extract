# Resolving base-game classes (MTSunSky) from a bare UE project

Question: how do we get `/Game/Blueprints/MTSunSky` and `/Script/MotorTown.*` usable
from `D:\UEProjects\C1`, which is a bare UE 5.5 project with neither the module nor
the assets?

## The mechanism everything rests on

Cooking does not store pointers, it stores **package paths as strings**. A reference
is `"/Game/Blueprints/MTSunSky"` + class name `MTSunSky_C`. At load time the engine
looks that path up in the mounted paks. Therefore a project can hold a *fake* asset at
exactly the same path, reference it, and the game will resolve the reference to the
**real** asset — provided the fake is never packaged.

Buckminsterfullerene's modding guide states this directly: references are persistent
strings, "modders can make the asset in the same name, location, and type as in the
game and reference it in the blueprint… It will work, as long as they do not pack the
dummied asset into the mod, otherwise it will replace the original and cause issues."

https://buckminsterfullerene.github.io/dev-guide/Basis/Blueprints.html

## Options, cheapest first

### 1. Dummy the blueprint asset (no compilation)
Create a Blueprint in our project at the exact game path:

- `/Game/Blueprints/MTSunSky`, parent = `Actor`, generating class `MTSunSky_C`
- `/Game/Objects/GarageActorBP`, parent = `Actor`, generating class `GarageActorBP_C`

Then `ChildActorComponent.ChildActorClass` can be picked in the editor like any other
class, the level is cooked with a normal reference, and the dummy is **excluded from
the pak** at staging time (we already stage explicitly, so this is one filter).

Limits: this covers *blueprint* classes and their exposed properties. It does not
give us `/Script/MotorTown` C++ classes, and the dummy's real parent/behaviour never
ships, so anything relying on inherited defaults behaves as the real asset does at
runtime — which is what we want.

### 2. Dummy the C++ classes ("stub module") — needs a compiler
Recreate the headers from our UHT dump as a module named exactly `MotorTown`
(`/Script/MotorTown`), with matching `UCLASS` names, property names and types. The
editor can then spawn `AMTSunSky`/`AMTGarageActor` directly and expose their
properties in BP graphs. This is the documented "dummying headers" practice from the
same guide, and the "stub module" pattern from modding.wiki's
Dummying Missing Plugin Dependencies.

Cost: Visual Studio + UBT build, and a compile error surface (inherited virtuals,
bitfield widths, `SoftObject`/`SoftClass` naming) documented at length in UE4SS's UHT
guide: https://docs.ue4ss.com/guides/generating-uht-compatible-headers

### 3. Generate a whole project from the UHT dump — needs a compiler
`Archengius/UE4GameProjectGenerator` builds a complete project from a UE4SS
`UHTHeaderDump` plus the game's `.uproject` and `.upluginmanifest` (both extractable
from the game pak). We already have the header dump (`uht/MotorTown`, 11 MB, 1,444
public + 1,233 private headers), so only the two manifests and a compiled commandlet
are missing.
https://github.com/Archengius/UE4GameProjectGenerator

### 4. Suzie — runtime class generation in the editor, no header rewrite
`trumank/Suzie` is an editor plugin that reads a `.jmap` dump (from `jmap_dumper`, run
against the live game) and generates all native classes at editor startup *and during
cooking*, so game classes appear in the Blueprint editor without regenerating headers.
Tested on 5.3–5.6; needs a C++ project of the same engine version, and the plugin
compiled. This is the closest analogue to NS's authoring experience.
https://github.com/trumank/Suzie

### 5. UE4SS / Dumper-7 runtime SDKs — wrong tool for this job
`Dumper-7` and UE4SS's `SdkGenerator` produce headers for **native C++ mods** that are
compiled against the game's own module and injected as a DLL. They do not make the
*editor* able to author content referencing game classes. Useful only if we ever go
native.

## Recommendation for C1

Do **1** now (dummy `MTSunSky` and `GarageActorBP` at their real paths, exclude both
from staging). It removes the post-cook `--set-class-ref` step entirely: the
`ChildActorClass` becomes an ordinary editor-authored reference and the level cooks
clean.

Escalate to **3** (project generator over our existing UHT dump) only if we need to
call `AMTSunSky`/`AMTRoad`/`AMotorTownRaceSection` members directly or place race
sections from the editor — which phase 3/4 will want, since `AMotorTownRaceSection`
has no blueprint counterpart in the game's content tree.
