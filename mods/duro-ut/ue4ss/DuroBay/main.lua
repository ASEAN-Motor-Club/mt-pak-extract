-- main.lua -- DuroBay (v2)
-- Spawns the native AMTDealerVehicleSpawnPoint at Gosan and points it at the
-- Duro UT class. No .uasset editing, no framework pak.
--
-- Install: MotorTown\Binaries\Win64\ue4ss\Mods\DuroBay\Scripts\main.lua
--          plus an empty Mods\DuroBay\enabled.txt
-- Output:  UE4SS.log, lines tagged [DuroBay]

local COORDS   = { X = -388065.0, Y = 103586.0, Z = -21880.0 }
local ROTATION = { Pitch = 0.0, Yaw = 0.0, Roll = 0.0 }
local DEALER_CLASS = "/Script/MotorTown.MTDealerVehicleSpawnPoint"
-- the BlueprintGeneratedClass itself, not the package
local VEHICLE_CLASSES = {
    "/Game/Cars/Models/DUT1/DUT1.DUT1_C",
    "/Game/Cars/Models/DUT1/DUT1",
}

local spawned = nil
local function log(s) print("[DuroBay] " .. tostring(s) .. "\n") end

local function findVehicleClass()
    for _, path in ipairs(VEHICLE_CLASSES) do
        local ok, obj = pcall(function() return StaticFindObject(path) end)
        if ok and obj then
            log("vehicle class resolved: " .. path)
            return obj
        end
        log("not found: " .. path)
    end
    local ok, cls = pcall(function() return FindObject("/Game/Cars/Models/DUT1/DUT1.DUT1_C") end)
    if ok and cls then
        log("vehicle class resolved via FindObject")
        return cls
    end
    return nil
end

local function trySpawn()
    if spawned and spawned:IsValid() then
        log("bay already present: " .. tostring(spawned:GetFullName()))
        return
    end

    local pc = FindFirstOf("PlayerController")
    if not pc then log("no PlayerController yet"); return end
    local world = pc:GetWorld()
    if not world then log("no world yet"); return end

    local dealerCls = StaticFindObject(DEALER_CLASS)
    if not dealerCls then log("dealer class not found"); return end

    local vehicleClass = findVehicleClass()
    if not vehicleClass then
        log("Duro UT class unavailable — is zzz_AMC_DuroUT installed and enabled?")
        return
    end

    local actor = world:SpawnActor(dealerCls, COORDS, ROTATION)
    if not actor or not actor:IsValid() then
        log("SpawnActor returned nothing")
        return
    end
    spawned = actor
    log("spawned: " .. tostring(actor:GetFullName()))

    local okSet, errSet = pcall(function() actor:SetVehicleClass(vehicleClass) end)
    log("SetVehicleClass ok=" .. tostring(okSet) .. " err=" .. tostring(errSet))

    local okRead, vc = pcall(function() return actor.VehicleClass end)
    log("VehicleClass now = " .. tostring(okRead and tostring(vc) or "unreadable"))

    local okSpawn, errSpawn = pcall(function() actor:SpawnVehicle() end)
    log("SpawnVehicle ok=" .. tostring(okSpawn) .. " err=" .. tostring(errSpawn))

    log("done")
end

RegisterHook("/Script/Engine.PlayerController:ClientRestart", function()
    ExecuteWithDelay(6000, function()
        ExecuteInGameThread(function()
            local ok, err = pcall(trySpawn)
            if not ok then log("ERROR: " .. tostring(err)) end
        end)
    end)
end)
