"""Author AMTAIVehicleSpawnSystem into C1Roads (exact UPROPERTY names).

EMTVehicleType is not exposed to Python, so VehicleTypes are written through
`import_text` using enum ENTRY NAMES ('Small', 'Pickup', 'Truck', ...), never raw
integers: numeric ordinals are not stable and an earlier integer table (offset by
two) made the 250-count "Small" row spawn Bus/Truck instead of Small/Pickup.

Row set and every count below mirror the vanilla Jeju MTAIVehicleSpawnSystem1
(16 rows, verified 2026-11-14) so the C1 map spawns traffic exactly like the
island. `verify()` re-reads the authored actor and fails loudly on any drift.
"""

import json
import os

import unreal

ROWS = json.loads(r"""[
 {
  "SettingKey": "Small",
  "SpawnType": 0,
  "VehicleTypes": [
   "Small",
   "Pickup"
  ],
  "VehicleKey": "",
  "bSpawnAIController": true,
  "bIsTrafficVehicle": true,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": true,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": true,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 250,
  "MinCount": -1,
  "bUseNPCVehicleDensity": true,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "Special",
  "SpawnType": 0,
  "VehicleTypes": [
   "Motorhome"
  ],
  "VehicleKey": "",
  "bSpawnAIController": true,
  "bIsTrafficVehicle": true,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": true,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": true,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 5,
  "MinCount": -1,
  "bUseNPCVehicleDensity": true,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "Truck",
  "SpawnType": 0,
  "VehicleTypes": [
   "Truck",
   "SemiTractor"
  ],
  "VehicleKey": "",
  "bSpawnAIController": true,
  "bIsTrafficVehicle": true,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": true,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": true,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 50,
  "MinCount": -1,
  "bUseNPCVehicleDensity": true,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "Bus",
  "SpawnType": 0,
  "VehicleTypes": [
   "Bus"
  ],
  "VehicleKey": "",
  "bSpawnAIController": true,
  "bIsTrafficVehicle": true,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": true,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": true,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 50,
  "MinCount": -1,
  "bUseNPCVehicleDensity": true,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 1,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "Police",
  "SpawnType": 0,
  "VehicleTypes": [
   "Small"
  ],
  "VehicleKey": "",
  "bSpawnAIController": true,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": true,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": true,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": true,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "Tow_LD",
  "SpawnType": 1,
  "VehicleTypes": [
   "Small"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": true,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": true
 },
 {
  "SettingKey": "Tow",
  "SpawnType": 1,
  "VehicleTypes": [
   "Small",
   "Pickup",
   "Bus",
   "Truck",
   "SemiTractor"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": true,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": true
 },
 {
  "SettingKey": "TowHeavy",
  "SpawnType": 1,
  "VehicleTypes": [
   "SemiTractor"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": true,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": true
 },
 {
  "SettingKey": "Rescue",
  "SpawnType": 2,
  "VehicleTypes": [
   "Small",
   "Pickup"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": true,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 120.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": 2000.0,
  "MaxDistanceFromRoad": 1000000.0,
  "MinDistanceFromLastSpawnLocation": 100000.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "HeavyRescue",
  "SpawnType": 2,
  "VehicleTypes": [
   "Bus",
   "Truck",
   "SemiTractor"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": true,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": false,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 300.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": 500.0,
  "MaxDistanceFromRoad": 5000.0,
  "MinDistanceFromLastSpawnLocation": 100000.0,
  "bIncludeTrailer": true
 },
 {
  "SettingKey": "VehicleDelivery",
  "SpawnType": 3,
  "VehicleTypes": [
   "Small"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": true,
  "bAllowCloseToOtherVehicle": true,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 30.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "VehicleDeliveryHeavy",
  "SpawnType": 3,
  "VehicleTypes": [
   "Bus",
   "Truck",
   "SemiTractor"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": true,
  "bAllowCloseToOtherVehicle": true,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 30.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "Getaway",
  "SpawnType": 4,
  "VehicleTypes": [
   "Small"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": true,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": false,
  "bAllowCloseToOtherVehicle": true,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 0.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "Delivery_Terra",
  "SpawnType": 3,
  "VehicleTypes": [],
  "VehicleKey": "Terra",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": false,
  "bAllowCloseToPlayer": true,
  "bAllowCloseToOtherVehicle": true,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 10.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "VehicleDeliveryAmbulance",
  "SpawnType": 3,
  "VehicleTypes": [
   "Small",
   "Truck"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": true,
  "bAllowCloseToPlayer": true,
  "bAllowCloseToOtherVehicle": true,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 },
 {
  "SettingKey": "VehicleDeliveryFireEngine",
  "SpawnType": 3,
  "VehicleTypes": [
   "Truck"
  ],
  "VehicleKey": "",
  "bSpawnAIController": false,
  "bIsTrafficVehicle": false,
  "bSpawnRoadSide": false,
  "bDespawnIfPlayersAreFar": true,
  "bAllowCloseToPlayer": true,
  "bAllowCloseToOtherVehicle": true,
  "bDespawnIfNotMoveForLong": false,
  "MaxLifetimeSeconds": 0.0,
  "MaxCount": 0,
  "MinCount": -1,
  "bUseNPCVehicleDensity": false,
  "bUseNPCPoliceDensity": false,
  "SpawnOverMinCountCoolDownTimeSeconds": 60.0,
  "CountMultiplierScheduleType": 0,
  "MinDistanceFromRoad": -1.0,
  "MaxDistanceFromRoad": -1.0,
  "MinDistanceFromLastSpawnLocation": 0.0,
  "bIncludeTrailer": false
 }
]""")

LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LEVEL = os.environ.get("C1_LEVEL", "/Game/Mods/C1/Maps/C1Roads")

BOOL_FIELDS = ["bSpawnAIController", "bIsTrafficVehicle", "bSpawnRoadSide",
               "bDespawnIfPlayersAreFar", "bAllowCloseToPlayer", "bAllowCloseToOtherVehicle",
               "bDespawnIfNotMoveForLong", "bUseNPCVehicleDensity", "bUseNPCPoliceDensity",
               "bIncludeTrailer"]
FLOAT_FIELDS = ["MaxLifetimeSeconds", "SpawnOverMinCountCoolDownTimeSeconds", "MinDistanceFromRoad",
                "MaxDistanceFromRoad", "MinDistanceFromLastSpawnLocation"]
INT_FIELDS = ["MaxCount", "MinCount"]

# Valid EMTVehicleType entry names (subset the spawner can spawn). Any other name is a
# hard error -- silently writing a bogus type is what produced zero-traffic maps before.
VEHICLE_TYPES = {"Small", "Pickup", "Bus", "Truck", "SemiTractor", "Motorhome",
                 "SportsCar", "Van", "Tanker", "Trailer"}


def build(row):
    s = unreal.MTAIVehicleSpawnSetting()
    s.set_editor_property("SettingKey", row["SettingKey"])
    st = row.get("SpawnType", 0)
    names = {0: "NONE", 1: "TOW_REQUEST", 2: "TOW_REQUEST_RESCUE",
             3: "TOW_REQUEST_DELIVERY", 4: "GETAWAY"}
    s.set_editor_property("SpawnType", getattr(unreal.MTAIVehicleSpawnType, names.get(st, "NONE")))
    sched = row.get("CountMultiplierScheduleType", 0)
    sched_names = {0: "NONE", 1: "TRAFFIC_DENSITY", 2: "COMMUTER_TRAFFIC_DENSITY",
                   3: "COMMERCIAL_TRAFFIC_DENSITY", 4: "INDUSTRIAL_TRAFFIC_DENSITY"}
    try:
        s.set_editor_property("CountMultiplierScheduleType",
                              getattr(unreal.MTTimeOfDayScheduleType, sched_names.get(sched, "NONE")))
    except Exception as e:
        print("[TRAFFIC] sched_fail " + str(e))
    for f in BOOL_FIELDS:
        s.set_editor_property(f, bool(row.get(f, False)))
    for f in FLOAT_FIELDS:
        s.set_editor_property(f, float(row.get(f, 0.0)))
    for f in INT_FIELDS:
        s.set_editor_property(f, int(row.get(f, 0)))
    # EMTVehicleType is not exposed to Python, but import_text parses enum arrays natively.
    # Names only -- see module docstring for why integers are unsafe here.
    types = row.get("VehicleTypes") or []
    if types:
        bad = [t for t in types if t not in VEHICLE_TYPES]
        if bad:
            raise RuntimeError("[TRAFFIC] unknown VehicleTypes " + str(bad)
                               + " in row " + row["SettingKey"])
        s.import_text("(VehicleTypes=(" + ",".join(types) + "))")
    return s


def types_of(s):
    """Read back VehicleTypes from an authored setting as a list of names."""
    t = s.export_text()
    if "VehicleTypes=(" not in t:
        return []
    seg = t.split("VehicleTypes=(", 1)[1].split(")", 1)[0]
    return [x.strip().split("::")[-1] for x in seg.split(",") if x.strip()]


LES.load_level(LEVEL)
for a in EAS.get_all_level_actors():
    if a.get_class().get_name() == "MTAIVehicleSpawnSystem":
        EAS.destroy_actor(a)
        print("[TRAFFIC] removed existing")

cls = getattr(unreal, "MTAIVehicleSpawnSystem", None)
if cls is None:
    print("[TRAFFIC] FATAL class missing")
else:
    actor = EAS.spawn_actor_from_class(cls, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
    actor.set_actor_label("C1_AIVehicleSpawnSystem")
    settings = [build(r) for r in ROWS]
    actor.set_editor_property("SpawnSettings", settings)
    print("[TRAFFIC] authored=" + str(len(settings)))
    LES.save_current_level()
    print("[TRAFFIC] saved")

fail = []
for a in EAS.get_all_level_actors():
    if a.get_class().get_name() == "MTAIVehicleSpawnSystem":
        st = a.get_editor_property("SpawnSettings")
        print("[TRAFFIC] readback=" + str(len(st)))
        if len(st) != len(ROWS):
            fail.append("row_count %d != %d" % (len(st), len(ROWS)))
        for i in range(len(st)):
            s = st[i]
            want = ROWS[i]["VehicleTypes"] if i < len(ROWS) else []
            got = types_of(s)
            ok = (got == want)
            print("[TRAFFIC] row " + str(i)
                  + " key=" + str(s.get_editor_property("SettingKey"))
                  + " max=" + str(s.get_editor_property("MaxCount"))
                  + " traffic=" + str(s.get_editor_property("bIsTrafficVehicle"))
                  + " dens=" + str(s.get_editor_property("bUseNPCVehicleDensity"))
                  + " cd=" + str(s.get_editor_property("SpawnOverMinCountCoolDownTimeSeconds"))
                  + " types=" + (",".join(got) if got else "EMPTY")
                  + ("  OK" if ok else "  MISMATCH want=" + ",".join(want)))
            if not ok:
                fail.append("row %d %s types %s != %s" % (i, s.get_editor_property("SettingKey"),
                                                          got, want))
if fail:
    raise RuntimeError("[TRAFFIC] SPAWNER VERIFY FAILED: " + " | ".join(fail))
print("[TRAFFIC] verified=" + str(len(ROWS)) + " rows")
print("[TRAFFIC] done")
