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

local function SafeCall(fn, default)
  local ok, v = pcall(fn)
  if ok then return v end
  return default
end

Commands["/mat"] = function(PC, args)
  ExecuteInGameThread(function()
    local out = {}
    local function L(m) out[#out+1] = m end
    local function slots(path)
      local m = LoadAsset(path)
      if not m then L(path .. " load=false"); return end
      local n, first = 0, "-"
      for i = 0, 140 do
        local ok, mm = pcall(function() return m:GetMaterial(i) end)
        if ok and mm then
          n = n + 1
          if first == "-" then local o2, nm = pcall(function() return mm:GetFullName() end); first = (o2 and nm) or "?" end
        end
      end
      L(path .. " load=true with_material=" .. n .. " first=" .. first)
    end
    local function parent(path)
      local m = LoadAsset(path)
      if not m then L(path .. " load=false"); return end
      local ok, p2 = pcall(function() return m:GetMaterial() end)
      local nm = "-"
      if ok and p2 then local o2, v = pcall(function() return p2:GetFullName() end); nm = (o2 and v) or "?" end
      L(path .. " load=true parent=" .. nm)
    end
    L("== MATCHK2 ==")
    slots("/Game/Mods/C1/Meshes/c5_18")
    slots("/Game/Cars/Models/Atlas/Cab")
    parent("/Game/Mods/C1/Materials/MI_C1_mat_road_01")
    parent("/Game/Env/Materials/Road/MI_Road_01A_Ver01_NoGroove")
    L("== END ==")
    print(table.concat(out, "\n"))
  end)
end

Commands["/near"] = function(PC, args)
  local radius = tonumber(args[1]) or 50000
  ExecuteInGameThread(function()
    local pawn = PC.Pawn
    if not pawn or pawn:IsValid() == false then LogOutput("INFO", "near: no pawn"); return end
    local pl = pawn:K2_GetActorLocation()
    local px, py, pz = pl.X, pl.Y, pl.Z
    local out = { "== NEAR ==", string.format("player=%.0f %.0f %.0f radius=%.0f", px, py, pz, radius) }
    local rows, counts = {}, {}
    local function info(c)
      local r = { mats = {}, nmat = 0 }
      pcall(function() local l = c:K2_GetComponentLocation(); r.lx, r.ly, r.lz = l.X, l.Y, l.Z end)
      pcall(function()
        local b = c.Bounds
        r.bx, r.by, r.bz = b.Origin.X, b.Origin.Y, b.Origin.Z
        r.ex, r.ey, r.ez = b.BoxExtent.X, b.BoxExtent.Y, b.BoxExtent.Z
      end)
      pcall(function() r.name = c:GetFullName() end)
      pcall(function() r.mesh = meshName(compMesh(c)) end)
      pcall(function() r.nmat = c:GetNumMaterials() end)
      r.mats = {}
      pcall(function()
        for mi = 0, math.min((r.nmat or 0) - 1, 2) do
          local mm = nil
          pcall(function() mm = c:GetMaterial(mi) end)
          if mm ~= nil then
            local okn, nm = pcall(function() return mm:GetFullName() end)
            r.mats[#r.mats + 1] = (okn and nm) or "?"
          end
        end
      end)
      local dl, db = nil, nil
      if r.lx ~= nil then
        local dx, dy, dz = r.lx - px, r.ly - py, r.lz - pz
        dl = math.sqrt(dx * dx + dy * dy + dz * dz)
      end
      if r.bx ~= nil and r.ex ~= nil then
        local dx = math.max(math.abs(px - r.bx) - r.ex, 0)
        local dy = math.max(math.abs(py - r.by) - r.ey, 0)
        local dz = math.max(math.abs(pz - r.bz) - r.ez, 0)
        db = math.sqrt(dx * dx + dy * dy + dz * dz)
      end
      r.dl, r.db = dl, db
      r.d = db or dl or 1e12
      return r
    end
    local function scan(cls)
      local ok, comps = pcall(FindAllOf, cls)
      if not ok or comps == nil then counts[#counts + 1] = cls .. "=ERR"; return end
      counts[#counts + 1] = cls .. "=" .. tostring(#comps)
      for _, c in ipairs(comps) do
        local ok2, r = pcall(info, c)
        if ok2 and r ~= nil then rows[#rows + 1] = r end
      end
    end
    scan("StaticMeshComponent")
    scan("InstancedStaticMeshComponent")
    table.sort(rows, function(a, b) return a.d < b.d end)
    out[#out + 1] = "comps " .. table.concat(counts, " ")
    for i = 1, math.min(#rows, 12) do
      local r = rows[i]
      out[#out + 1] = string.format("%d. d=%.0f mesh=%s nmat=%d mats=%s", i, r.d, tostring(r.mesh), r.nmat or -1, table.concat(r.mats or {}, " ; "))
    end
    out[#out + 1] = "== END near rows=" .. tostring(#rows)
    print(table.concat(out, "\n"))
  end)
end


-- ---------------------------------------------------------------------------
-- Named teleport targets, extracted from the original BeamNG level
-- (levels/c1/main/missiongroup/{playerdroppoints,garage_marker,trap,
-- tunnel_triggers}/items.level.json inside the source mod).
-- Converted bng metres -> UE cm the same way the geometry was ported:
--   x*100, y negated, z*100.
-- Use: /tp shibaura | /tp garage2 | /tp trap7 | /tp tunnel3 | /tplist
-- ---------------------------------------------------------------------------
local TP_NAMED = {
  ["spawn_parking"] = {593234, -466784, 87449},
  ["tatsumi"] = {593234, -466784, 87449},
  ["spawn_road"] = {83167, 406270, 84990},
  ["yotsuya"] = {83167, 406270, 84990},
  ["spawn_default"] = {110237, -470902, 87411},
  ["shibaura"] = {110237, -470902, 87411},
  ["spawn_new"] = {381965, 511319, 85216},
  ["haneda"] = {381965, 511319, 85216},
  ["spawn_mirai"] = {-844349, 1606825, 86672},
  ["mirai"] = {-844349, 1606825, 86672},
  ["shin_yamashita"] = {-844349, 1606825, 86672},
  ["garage1"] = {17790, 224139, 85484},
  ["garage2"] = {-17925, 138682, 85484},
  ["garage3"] = {20387, 222918, 85484},
  ["garage4"] = {-52539, 75478, 85954},
  ["trap1"] = {-23016, 574373, 86276},
  ["trap2"] = {-51821, 704386, 86247},
  ["trap3"] = {-548125, 1050589, 86162},
  ["trap4"] = {-741837, 1131938, 86754},
  ["trap5"] = {-790623, 1155711, 85924},
  ["trap6"] = {-1088922, 1446762, 86205},
  ["trap7"] = {-821627, 1597593, 87220},
  ["trap8"] = {-675980, 1529533, 90835},
  ["trap9"] = {389131, -354009, 85781},
  ["trap10"] = {608879, -506166, 88584},
  ["trap11"] = {540882, -771460, 87764},
  ["trap12"] = {265433, -844802, 84760},
  ["trap13"] = {270989, -387585, 88556},
  ["trap14"] = {206854, -966353, 86531},
  ["trap15"] = {4777, -974645, 86763},
  ["trap16"] = {133121, -610742, 85901},
  ["trap17"] = {250918, -820319, 84618},
  ["trap18"] = {340070, -875442, 86704},
  ["trap19"] = {493980, -796938, 86108},
  ["trap20"] = {587214, -617812, 86399},
  ["trap21"] = {604114, -469894, 87536},
  ["trap22"] = {491145, -419415, 85353},
  ["trap23"] = {110975, -463283, 88240},
  ["trap24"] = {102575, -493253, 86121},
  ["trap25"] = {47104, -300895, 85981},
  ["trap26"] = {12483, -21301, 85802},
  ["trap27"] = {68515, 365726, 84786},
  ["trap28"] = {13507, 462138, 85750},
  ["trap29"] = {-635162, 1286998, 87516},
  ["trap30"] = {-651350, 1145861, 87488},
  ["trap31"] = {-641612, 1162147, 86307},
  ["trap32"] = {-893654, 1628697, 86246},
  ["trap33"] = {-1094199, 1440846, 86267},
  ["trap34"] = {-1009155, 1278681, 86252},
  ["trap35"] = {-770768, 1139358, 86383},
  ["trap36"] = {-577953, 1061875, 86117},
  ["trap37"] = {-263425, 889113, 86023},
  ["trap38"] = {-86599, 753981, 86020},
  ["trap39"] = {-11448, 523233, 86038},
  ["trap40"] = {85095, 394651, 84507},
  ["trap41"] = {31731, 303824, 85931},
  ["trap42"] = {53502, -114467, 85233},
  ["trap43"] = {52937, -232403, 85886},
  ["trap44"] = {87121, -457307, 85879},
  ["trap45"] = {-463607, 1327220, 89185},
  ["tunnel1"] = {158866, -687461, 84775},
  ["tunnel2"] = {177157, -196867, 84775},
  ["tunnel3"] = {234170, 368508, 85169},
  ["tunnel4"] = {455502, 697778, 86072},
  ["tunnel5"] = {439835, 763593, 86079},
  ["tunnel6"] = {422367, 825661, 86010},
  ["tunnel7"] = {335052, 916430, 86079},
  ["tunnel8"] = {266016, 960473, 86079},
  ["tunnel9"] = {-973210, 1605500, 86079},
  ["tunnel10"] = {-1026700, 1541737, 86079},
  ["tunnel11"] = {-1029471, 1507691, 86079},
  ["tunnel12"] = {77714, 378714, 86079},
  ["tunnel13"] = {53998, -981225, 86079},
  ["tunnel14"] = {-12147, -920292, 86079},
  ["tunnel15"] = {-8076, -880860, 86079},
  ["tunnel16"] = {33476, -834522, 86079},
  ["tunnel17"] = {13118, -800374, 86079},
  ["tunnel18"] = {-63880, -690388, 86080},
  ["tunnel19"] = {-69388, -664565, 86080},
}

local function tp_named_list(prefix)
  local out = {}
  for k in pairs(TP_NAMED) do
    if prefix == nil or string.sub(k, 1, #prefix) == prefix then out[#out + 1] = k end
  end
  table.sort(out)
  return out
end

Commands["/tplist"] = function(PC, args)
  local prefix = args[1] and string.lower(args[1]) or nil
  local names = tp_named_list(prefix)
  local out = { "== TP POINTS (" .. #names .. ") ==" }
  local line = ""
  for _, n in ipairs(names) do
    if #line + #n + 2 > 78 then out[#out + 1] = line; line = "" end
    line = line .. n .. "  "
  end
  if #line > 0 then out[#out + 1] = line end
  print(table.concat(out, "\n"))
end

Commands["/tp"] = function(PC, args)
  -- Named target: /tp <name> (see /tplist). Numeric form still works unchanged.
  if args[1] ~= nil and tonumber(args[1]) == nil then
    local key = string.lower(tostring(args[1]))
    local pt = TP_NAMED[key]
    if pt == nil then
      local hits = {}
      for k in pairs(TP_NAMED) do
        if string.find(k, key, 1, true) ~= nil then hits[#hits + 1] = k end
      end
      table.sort(hits)
      if #hits == 1 then pt = TP_NAMED[hits[1]]
      elseif #hits > 1 then
        print("== TP ==\n'" .. key .. "' matches " .. #hits .. ": " .. table.concat(hits, " "))
        return
      else
        print("== TP ==\nunknown target '" .. key .. "'  (run /tplist to see names)")
        return
      end
    end
    return Commands["/tp"](PC, { tostring(pt[1]), tostring(pt[2]), tostring(pt[3]) })
  end
  local x = tonumber(args[1])
  local y = tonumber(args[2])
  local z = tonumber(args[3])
  if x == nil then
    print("== TP ==\nusage: /tp <x> <y> <z>   |   /tp <name>   |   /tplist for names   |   /tpback")
    return
  end
  ExecuteInGameThread(function()
    local out = { "== TP ==" }
    local function emit(s) out[#out + 1] = s end
    local ok, err = pcall(function()
      local pawn = PC.Pawn
      if pawn == nil then emit("no pawn"); return end
      emit(string.format("target=%.1f %.1f %.1f", x, y, z))
      local loc = { X = x, Y = y, Z = z }
      local moved = false
      local e1 = nil
      local ok1, r1 = pcall(function() moved = pawn:K2_SetActorLocation(loc, false, {}, true) end)
      if not ok1 or moved ~= true then
        e1 = r1
        local ok2, r2 = pcall(function() moved = pawn:SetActorLocation(loc, false, {}, true) end)
        if not ok2 then e1 = tostring(e1) .. " / " .. tostring(r2) end
      end
      if moved ~= true then
        pcall(function() local rc = pawn.RootComponent; rc:K2_SetWorldLocation(loc, false, {}, true) end)
      end
      local p = nil
      pcall(function() p = pawn:K2_GetActorLocation() end)
      if p ~= nil then
        emit(string.format("moved=%s now=%.1f %.1f %.1f", tostring(moved), p.X, p.Y, p.Z))
      else
        emit("moved=" .. tostring(moved) .. " (location unreadable)")
      end
      if e1 ~= nil then emit("fallback_note=" .. tostring(e1)) end
    end)
    if not ok then emit("tp error: " .. tostring(err)) end
    print(table.concat(out, "\n"))
  end)
end

-- The BeamNG "dum" dummy slab site, in map space (this is the same frame the /coords probe
-- prints pawn_loc in, NOT PC_loc -- the two disagree and PC_loc is the misleading one).
local SLAB_SPOT = { -25711.6, 130757.3, 85590.6 }

Commands["/tpback"] = function(PC, args)
  return Commands["/tp"](PC, { tostring(SLAB_SPOT[1]), tostring(SLAB_SPOT[2]), tostring(SLAB_SPOT[3]) })
end

Commands["/ray"] = function(PC, args)
  local dist = tonumber(args[1]) or 5000
  ExecuteInGameThread(function()
    local out = { "== RAY ==" }
    local function emit(s) out[#out + 1] = s end
    local ok, err = pcall(function()
      local cam = PC.PlayerCameraManager
      if not cam or cam:IsValid() == false then emit("no camera manager"); return end
      local start = cam:K2_GetActorLocation()
      local rot = cam:GetCameraRotation()
      local fwd = rot:GetForwardVector()
      local stop = {
        X = start.X + fwd.X * dist,
        Y = start.Y + fwd.Y * dist,
        Z = start.Z + fwd.Z * dist,
      }
      emit(string.format("start=%.0f %.0f %.0f stop=%.0f %.0f %.0f dist=%.0f",
        start.X, start.Y, start.Z, stop.X, stop.Y, stop.Z, dist))
      local ksl = StaticFindObject("/Script/Engine.KismetSystemLibrary")
      if not ksl or ksl:IsValid() == false then emit("no KismetSystemLibrary"); return end
      local hit = {}
      local ok2, e2 = pcall(function()
        ksl:LineTraceSingle(PC, start, stop, 0, true, {}, 0, hit, true, {}, 0)
      end)
      emit("trace_ok=" .. tostring(ok2) .. " err=" .. tostring(e2))
      local comp = hit.Component
      if comp == nil then emit("no hit"); return end
      local okc = pcall(function() if comp:IsValid() == false then comp = nil end end)
      if comp == nil then emit("hit component invalid"); return end
      emit("comp=" .. tostring(comp:GetFullName()))
      local sm = compMesh(comp)
      if sm ~= nil then emit("mesh=" .. tostring(meshName(sm)) .. " path=" .. tostring(sm:GetFullName())) end
      local n = 0
      pcall(function() n = comp:GetNumMaterials() end)
      emit("nmat=" .. tostring(n))
      for i = 0, math.min(n - 1, 4) do
        local m = nil
        pcall(function() m = comp:GetMaterial(i) end)
        if m ~= nil then emit("slot[" .. i .. "]=" .. tostring(m:GetFullName())) else emit("slot[" .. i .. "]=nil") end
      end
    end)
    if not ok then emit("ray error: " .. tostring(err)) end
    print(table.concat(out, "\n"))
  end)
end

Commands["/what"] = function(PC, args)
  ExecuteInGameThread(function()
    local out = { "== WHAT ==" }
    local function emit(s) out[#out + 1] = s end

    local hit = {}
    local ok = pcall(function()
      PC:GetHitResultUnderCursorByChannel(0, true, hit)
    end)
    emit("trace_ok=" .. tostring(ok))

    local comp = nil
    pcall(function() comp = hit.Component end)
    local face = -1
    pcall(function() face = hit.FaceIndex end)
    emit("component=" .. tostring(comp ~= nil) .. " face=" .. tostring(face))
    if comp == nil then
      local h2 = {}
      pcall(function()
        local w = PC:GetWorld()
        local cam = PC.PlayerCameraManager
        local start = cam:K2_GetActorLocation()
        local rot = cam:GetCameraRotation()
        local fr, ri, up = nil, nil, nil
        pcall(function() fr = rot:GetForwardVector() end)
        emit("cam=" .. tostring(start ~= nil))
      end)
      print(table.concat(out, "\n"))
      return
    end

    local cname = "?"
    pcall(function() cname = comp:GetFullName() end)
    emit("comp_name=" .. cname)

    local nmat = 0
    pcall(function() nmat = comp:GetNumMaterials() end)
    emit("nmat=" .. tostring(nmat))

    local idx = -1
    pcall(function() idx = comp:GetMaterialFromCollisionFaceIndex(face, nil) end)
    emit("material_from_face=" .. tostring(idx))

    local function show(i, tag)
      local m = nil
      pcall(function() m = comp:GetMaterial(i) end)
      if m ~= nil then
        local s = "?"
        pcall(function() s = m:GetFullName() end)
        emit(tag .. "[" .. tostring(i) .. "]=" .. s)
      else
        emit(tag .. "[" .. tostring(i) .. "]=nil")
      end
    end
    if idx ~= nil and idx >= 0 then show(idx, "hit_material") end
    for i = 0, math.min(nmat - 1, 3) do show(i, "slot") end

    print(table.concat(out, "\n"))
    writeCoordLine(os.date("%H:%M:%S ") .. "what idx=" .. tostring(idx) .. " nmat=" .. tostring(nmat))
  end)
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


Commands["/cell"] = function(PC, args)
  local name = args[1] or "c-1_-3"
  local pkg = "/Game/Mods/C1Full/Meshes/" .. name
  local full = pkg .. "." .. name
  ExecuteInGameThread(function()
    local out = { "== CELL " .. name .. " ==" }
    local function emit(s) out[#out + 1] = s end
    local function describe(tag, m)
      if m == nil then emit(tag .. "=nil") return end
      local lods, nmat = -1, -1
      pcall(function() lods = m:GetNumLODs() end)
      pcall(function() nmat = #m:GetStaticMaterials() end)
      emit(string.format("%s=%s lods=%s mats=%s", tag, tostring(m:GetFullName()), tostring(lods), tostring(nmat)))
      pcall(function()
        local b = m:GetBoundingBox()
        emit(string.format("  %s bounds min=%.0f %.0f %.0f max=%.0f %.0f %.0f", tag,
          b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z))
      end)
      pcall(function()
        local mats = m:GetStaticMaterials()
        for i = 1, math.min(#mats, 3) do
          local mi = mats[i].MaterialInterface
          emit(string.format("  %s slot[%d]=%s", tag, i - 1,
            tostring(mi ~= nil and mi:GetFullName() or "NULL")))
        end
      end)
    end
    local ok, err = pcall(function()
      local m = nil
      pcall(function() m = StaticFindObject(full) end)
      if m == nil then pcall(function() m = LoadObject(full) end) end
      describe("asset", m)
      local comps = FindAllOf("StaticMeshComponent") or {}
      local hits = 0
      for _, comp in ipairs(comps) do
        if comp ~= nil and comp:IsValid() ~= false then
          local cm = compMesh(comp)
          local cp = ""
          if cm ~= nil then pcall(function() cp = cm:GetFullName() end) end
          if cp ~= nil and cp:find(name, 1, true) ~= nil then
            hits = hits + 1
            local vis, hid = "?", "?"
            local owner = nil
            pcall(function() vis = tostring(comp:IsVisible()) end)
            pcall(function() owner = comp:GetOwner() end)
            if owner ~= nil then pcall(function() hid = tostring(owner.bHidden) end) end
            emit(string.format("comp[%d] visible=%s owner_hidden=%s owner=%s", hits, vis, hid,
              owner ~= nil and tostring(owner:GetFullName()) or "nil"))
            local bm = nil
            pcall(function() bm = comp:GetStaticMesh() end)
            describe("  bound", bm)
            -- placement: the actor transform is what turns asset-local cm into world position
            pcall(function()
              local loc = owner:K2_GetActorLocation()
              local sc = owner:K2_GetActorScale3D()
              emit(string.format("  actor_loc=%.0f %.0f %.0f actor_scale=%.3f %.3f %.3f",
                loc.X, loc.Y, loc.Z, sc.X, sc.Y, sc.Z))
              local rl = owner:K2_GetActorRotation()
              emit(string.format("  actor_rot pitch=%.1f yaw=%.1f roll=%.1f", rl.Pitch, rl.Yaw, rl.Roll))
            end)
            pcall(function()
              local cl = comp:K2_GetComponentLocation()
              emit(string.format("  comp_loc=%.0f %.0f %.0f", cl.X, cl.Y, cl.Z))
            end)
            pcall(function()
              local bo = comp.Bounds
              emit(string.format("  comp_world_bounds origin=%.0f %.0f %.0f extent=%.0f %.0f %.0f",
                bo.Origin.X, bo.Origin.Y, bo.Origin.Z, bo.BoxExtent.X, bo.BoxExtent.Y, bo.BoxExtent.Z))
            end)
            local cn = 0
            pcall(function() cn = comp:GetNumMaterials() end)
            emit("  comp_nmat=" .. tostring(cn))
            for i = 0, math.min(cn - 1, 2) do
              local mm = nil
              pcall(function() mm = comp:GetMaterial(i) end)
              emit(string.format("  comp_slot[%d]=%s", i,
                tostring(mm ~= nil and mm:GetFullName() or "NULL")))
            end
          end
        end
      end
      emit("components_using_it=" .. tostring(hits))
    end)
    if not ok then emit("cell error: " .. tostring(err)) end
    print(table.concat(out, "\n"))
  end)
end

Commands["/time"] = function(PC, args)
  local h = tonumber(args[1] or "22")
  if h == nil or h < 0 or h > 24 then
    print("usage: /time <hour 0-24>   (e.g. /time 22 = night)")
    return
  end
  ExecuteInGameThread(function()
    local out = { "== TIME -> " .. tostring(h) .. "h ==" }
    local function add(x) out[#out + 1] = x end

    -- 1) the game's own entry point on the player controller
    local okc, errc = pcall(function() PC:Cheat_TimeOfDay(h) end)
    add("Cheat_TimeOfDay: " .. (okc and "ok" or ("ERR " .. tostring(errc))))

    -- 2) report the sky, and drive it directly if the cheat did not take
    local suns = FindAllOf("MTSunSky") or {}
    add("MTSunSky actors: " .. tostring(#suns))
    for i, s in ipairs(suns) do
      local okb, vb = pcall(function() return s.SolarTime end)
      add(string.format("  [%d] SolarTime before=%s", i, tostring(okb and vb or "?")))
      if okb and (not okc) then
        local oks, errs = pcall(function() s.SolarTime = h end)
        add("  set SolarTime: " .. (oks and "ok" or ("ERR " .. tostring(errs))))
        pcall(function() s:UpdateLighting(0.016) end)
        local oka, va = pcall(function() return s.SolarTime end)
        add(string.format("  SolarTime after=%s", tostring(oka and va or "?")))
      end
    end
    print(table.concat(out, "\n"))
  end)
end

Commands["/night"] = function(PC, args) Commands["/time"](PC, { "22" }) end
Commands["/noon"] = function(PC, args) Commands["/time"](PC, { "12" }) end

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
