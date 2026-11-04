"""Author AMTAIVehicleSpawnSystem into C1Roads (exact UPROPERTY names).

Scalars only: EMTVehicleType is not exposed to Python, so VehicleTypes cannot be built here
and VehicleClass stays null. SettingKey (Small/Special/Truck/Bus) is the semantic selector the
spawner reads; the server probe will tell us whether that is sufficient.
"""

import json
import os

import unreal

ROWS = json.loads(r"""[
 {
  "SettingKey": "Small",
  "SpawnType": 0,
  "VehicleTypes": [
   2,
   3
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
   9
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
   5,
   6
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
   4
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
   2
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
   2
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
   2,
   3,
   4,
   5,
   6
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
   6
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
   2,
   3
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
   4,
   5,
   6
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
   2
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
   4,
   5,
   6
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
   2
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
   2,
   5
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
   5
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
    types = row.get("VehicleTypes") or []
    if types:
        txt = "(VehicleTypes=(" + ",".join(str(int(t)) for t in types) + "))"
        try:
            s.import_text(txt)
        except Exception as e:
            print("[TRAFFIC] types_import_fail " + row["SettingKey"] + " " + str(e))
    return s


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

for a in EAS.get_all_level_actors():
    if a.get_class().get_name() == "MTAIVehicleSpawnSystem":
        st = a.get_editor_property("SpawnSettings")
        print("[TRAFFIC] readback=" + str(len(st)))
        for i in range(len(st)):
            s = st[i]
            print("[TRAFFIC] row " + str(i) + " key=" + str(s.get_editor_property("SettingKey"))
                  + " max=" + str(s.get_editor_property("MaxCount"))
                  + " traffic=" + str(s.get_editor_property("bIsTrafficVehicle"))
                  + " dens=" + str(s.get_editor_property("bUseNPCVehicleDensity"))
                  + " cd=" + str(s.get_editor_property("SpawnOverMinCountCoolDownTimeSeconds"))
                  + " types=" + str(s.export_text().split("VehicleTypes=")[1].split(",")[0] if "VehicleTypes=(" in s.export_text() else "EMPTY"))
print("[TRAFFIC] done")
