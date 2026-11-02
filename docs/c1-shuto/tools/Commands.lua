local vehicleManager = require("VehicleManager")
local teleportManager = require("TeleportManager")
-- local satNav = require("SatNav")
local integrityChecker = require("IntegrityChecker")

local Commands = {}

Commands["/despawn"] = function(PC, args)
  local mode = args[1] and string.lower(args[1]) or nil
  local count = 0

  if mode == "all" then
    count = vehicleManager.DespawnAllPlayerVehicles(PC)
    if count > 0 then
      LogOutput("INFO", "Despawned all %d vehicle(s)", count)
    else
      LogOutput("INFO", "No vehicles to despawn")
    end
  elseif mode == "others" then
    count = vehicleManager.DespawnOtherPlayerVehicles(PC)
    if count > 0 then
      LogOutput("INFO", "Despawned %d other vehicle(s)", count)
    else
      LogOutput("INFO", "No other vehicles to despawn")
    end
  else
    count = vehicleManager.DespawnPlayerVehicle(PC)
    if count > 0 then
      LogOutput("INFO", "Despawned %d vehicle(s)", count)
    else
      LogOutput("INFO", "No vehicle to despawn")
    end
  end
end

Commands["/d"] = Commands["/despawn"]

Commands["/teleport"] = function(PC, args)
  teleportManager.HandleTeleport(PC, args)
end

Commands["/tp"] = Commands["/teleport"]

Commands["/satnav"] = function(PC, args)
  satNav.Toggle()
end

Commands["/nav"] = Commands["/satnav"]

Commands["/check"] = function(PC, args)
  integrityChecker.RunCheck()
end

Commands["/dumpparts"] = function(PC, args)
  vehicleManager.DumpNetParts()
end

Commands["/snapshot"] = function(PC, args)
  vehicleManager.SnapshotParts()
end

Commands["/restore"] = function(PC, args)
  vehicleManager.RestoreParts()
end

local function writeCoordLine(line)
  local f = io.open("coords_log.txt", "a")
  if f then
    f:write(line .. "\n")
    f:close()
  end
end

local function f3(v)
  return string.format("%.1f %.1f %.1f", v.X, v.Y, v.Z)
end

local function compMesh(c)
  local sm = nil
  pcall(function() sm = c.StaticMesh end)
  if sm == nil then pcall(function() sm = c:GetStaticMesh() end) end
  return sm
end

local function meshName(sm)
  if sm == nil then return nil end
  local n = nil
  pcall(function() n = sm:GetName() end)
  return n
end

Commands["/coords"] = function(PC, args)
  local out = {}

  local function try(label, fn)
    local ok, res = pcall(fn)
    out[#out + 1] = label .. "=" .. (ok and tostring(res) or ("ERR:" .. tostring(res)))
  end

  try("PC", function()
    if not PC or PC:IsValid() == false then return "invalid" end
    return PC:GetFullName()
  end)
  try("PC_loc", function() return f3(PC:K2_GetActorLocation()) end)
  try("pawn", function()
    local p = PC.Pawn
    if not p or p:IsValid() == false then return "nil" end
    return p:GetFullName()
  end)
  try("pawn_loc", function() return f3(PC.Pawn:K2_GetActorLocation()) end)
  try("view", function()
    local v = PC:GetViewTarget()
    if not v or v:IsValid() == false then return "nil" end
    return v:GetFullName() .. " @ " .. f3(v:K2_GetActorLocation())
  end)
  try("cam", function()
    local cm = PC.PlayerCameraManager
    if not cm or cm:IsValid() == false then return "nil" end
    return cm:GetFullName() .. " @ " .. f3(cm:K2_GetActorLocation())
  end)

  local line = table.concat(out, " | ")
  LogOutput("INFO", "%s", line)
  writeCoordLine(os.date("%H:%M:%S ") .. line)
end

Commands["/jump"] = function(PC, args)
  local up = tonumber(args[1]) or 200
  ExecuteInGameThread(function()
    if not PC:IsValid() then return end
    local pawn = PC:K2_GetPawn()
    if not pawn:IsValid() then
      LogOutput("INFO", "J jump: no pawn")
      return
    end
    local loc = pawn:K2_GetActorLocation()
    local dest = { X = loc.X, Y = loc.Y, Z = loc.Z + up * 100 }
    local vehicleClass = StaticFindObject("/Script/MotorTown.MTVehicle")
    if vehicleClass:IsValid() and pawn:IsA(vehicleClass) then
      local rot = pawn:K2_GetActorRotation()
      PC:ServerResetVehicleAt(pawn, dest, rot, false, false)
    else
      PC:ServerTeleportCharacter(dest, false, false)
    end
    LogOutput("INFO", "J jump %+d m: from (%.1f, %.1f, %.1f) to (%.1f, %.1f, %.1f)",
      up, loc.X, loc.Y, loc.Z, dest.X, dest.Y, dest.Z)
  end)
end

Commands["/probe"] = function(PC, args)
  local out = {}
  local comps = FindAllOf("StaticMeshComponent")
  local n = 0
  for _, c in ipairs(comps) do
    local ok, line = pcall(function()
      local sm = compMesh(c)
      local name = meshName(sm)
      if not name then return nil end
      if args[1] and not string.find(name, args[1], 1, true) then return nil end
      local loc = c:K2_GetComponentLocation()
      local actor = c:GetOwner()
      local an = (actor and actor:IsValid()) and actor:GetName() or "?"
      local aloc = (actor and actor:IsValid()) and actor:K2_GetActorLocation() or loc
      return string.format("%s owner=%s comp=%.0f %.0f %.0f actor=%.0f %.0f %.0f",
        name, an, loc.X, loc.Y, loc.Z, aloc.X, aloc.Y, aloc.Z)
    end)
    if ok and line then
      n = n + 1
      out[#out + 1] = line
      if n >= 12 then break end
    end
  end
  local summary = string.format("probe comps_total=%d matched=%d", #comps, n)
  LogOutput("INFO", "%s", summary)
  writeCoordLine(os.date("%H:%M:%S ") .. summary)
  for _, l in ipairs(out) do
    LogOutput("INFO", "P %s", l)
    writeCoordLine("P " .. l)
  end
end

Commands["/probe2"] = function(PC, args)
  local filt = args[1]
  local function emit(s)
    LogOutput("INFO", "Q %s", s)
    writeCoordLine("Q " .. s)
  end

  local pawn = PC.Pawn
  if pawn and pawn:IsValid() then
    local pl = pawn:K2_GetActorLocation()
    emit(string.format("pawn %s @ %.0f %.0f %.0f", pawn:GetName(), pl.X, pl.Y, pl.Z))
    pcall(function()
      local mv = pawn:GetCharacterMovement()
      if mv and mv:IsValid() then
        emit(string.format("pawn falling=%s velZ=%.1f mode=%s",
          tostring(mv:IsFalling()), pawn:GetVelocity().Z, tostring(mv.MovementMode)))
      end
    end)
  end

  local comps = FindAllOf("StaticMeshComponent")
  local shown = 0
  for _, c in ipairs(comps) do
    local line = nil
    pcall(function()
      local sm = compMesh(c)
      local name = meshName(sm)
      if not name then return end
      if filt and not string.find(name, filt, 1, true) then return end
      local cl = c:K2_GetComponentLocation()
      local b = c.Bounds
      local ab = sm:GetBounds()
      line = string.format(
        "mesh=%s compLoc=%.0f %.0f %.0f compOrigin=%.0f %.0f %.0f extent=%.0f %.0f %.0f assetOrigin=%.0f %.0f %.0f assetExtent=%.0f %.0f %.0f",
        name, cl.X, cl.Y, cl.Z,
        b.Origin.X, b.Origin.Y, b.Origin.Z,
        b.BoxExtent.X, b.BoxExtent.Y, b.BoxExtent.Z,
        ab.Origin.X, ab.Origin.Y, ab.Origin.Z,
        ab.BoxExtent.X, ab.BoxExtent.Y, ab.BoxExtent.Z)
    end)
    if line then
      emit(line)
      shown = shown + 1
      if shown >= 8 then break end
    end
  end
  emit(string.format("probe2 done comps_total=%d shown=%d", #comps, shown))

  local roads = FindAllOf("MotorTownRoad")
  emit(string.format("roads actors=%d", #roads))
  for i, r in ipairs(roads) do
    if i > 3 then break end
    pcall(function()
      local l = r:K2_GetActorLocation()
      emit(string.format("road[%d] %s @ %.0f %.0f %.0f", i, r:GetName(), l.X, l.Y, l.Z))
    end)
  end
end


Commands["/probe3"] = function(PC, args)
  local function emit(t)
    LogOutput("INFO", "R %s", t)
    writeCoordLine("R " .. t)
  end
  local comps = FindAllOf("StaticMeshComponent")
  emit("probe3 comps=" .. tostring(#comps))
  local n = 0
  for i, c in ipairs(comps) do
    local fn = "?"
    pcall(function() fn = c:GetFullName() end)
    if string.find(fn, "PersistentLevel", 1, true) and not string.find(fn, "Default__", 1, true) then
      n = n + 1
      local prop = "nil"
      pcall(function() prop = tostring(c.StaticMesh) end)
      local fnc  = "nil"
      local err  = ""
      pcall(function() fnc = tostring(c:GetStaticMesh()) end)
      local okG, errG = pcall(function() return c:GetStaticMesh() end)
      if not okG then err = tostring(errG) end
      emit(string.format("%s | prop=%s | call=%s | callerr=%s", fn, prop, fnc, err))
      if n >= 5 then break end
    end
  end
  emit("probe3 done emitted=" .. n)
end

Commands["/pos"] = Commands["/coords"]

local function HandleCommand(PC, message)
  if string.sub(message, 1, 1) == "/" then
    local parts = SplitString(message, " ")
    if #parts > 0 then
      ---@diagnostic disable-next-line: need-check-nil
      local commandName = parts[1]
      local handler = Commands[commandName]
      if handler then
        local args = {}
        for i = 2, #parts do
          ---@diagnostic disable-next-line: need-check-nil
          table.insert(args, parts[i])
        end
        handler(PC, args)
        return true
      end
    end
  end
  return false
end

-- Hook the client-side chat widget text commit instead of the Server RPC
-- ServerSendChat is a Server RPC stub on the client and may not be hookable by UE4SS
RegisterHook("/Script/MotorTown.ChatWidget:OnTextCommitted", function(Context, Text, CommitMethod)
  local message = Text:get():ToString()
  if message == "" then return end

  local PC = GetMyPlayerController()
  if not PC:IsValid() then return end

  HandleCommand(PC, message)
end)

return Commands
