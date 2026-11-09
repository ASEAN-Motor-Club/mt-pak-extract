--[[ C1A7Check v1 -- runtime acceptance collector for the C1Full no-collision build.

WHAT THIS IS
  A data collector, not a judge. It walks every StaticMeshActor whose mesh lives under
  /Game/Mods/C1Full/ and dumps what the ENGINE actually resolved: actor location, mesh asset,
  visibility, mobility, collision profile, and -- for every material slot -- the material object
  the renderer will bind plus its BaseColor texture. It also runs collision traces over the paint
  and foliage actors, because "does this block a car" is a physics question, not a file question.

  The comparison against expectations happens off-machine, where it can be re-run without you
  launching the game again. That is the point of the design: one launch, one file, many questions.

OUTPUT
  D:/c1_a7check.json          the data (single JSON object, overwritten each run)
  D:/c1_a7check_alive.txt     proof the script loaded, timestamped

RUN
  Auto: when the C1Full map is loaded and >=700 of our actors exist, it collects once (~10 s).
  Manual: F10 re-collects at any time (useful after teleporting to another part of the map).

DESIGN NOTES (learned on this build, see C1DecalProbe/SuspHeightProbe)
  * Direct field access on UObjects returns TrivialObject wrappers -> always GetPropertyValue.
  * Big struct arrays (StaticMaterials, BodyInstance) are a Lua-GC hazard -> never dump them whole;
    call GetMaterial(i) per slot instead and read individual scalars only.
  * Every call is pcall'd with a named failure so one missing API does not kill the run; the JSON
    records which approach worked, which is how the next iteration gets cheaper.
--]]

local OUT   = "D:/c1_a7check.json"
local ALIVE = "D:/c1_a7check_alive.txt"
local VER   = "v1"
local MAX_SLOTS_FULL   = 8    -- per actor, full material detail
local MAX_ACTORS_DETAIL = 260 -- beyond this, actors are summarised only
local TRACE_GRID        = 12  -- traces per paint/foliage actor (12x12 = 144 per actor is too many; see below)

local function esc(s)
  return (tostring(s):gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\r', ''):gsub('\n', ' '))
end

local function try(fn, default)
  local ok, v = pcall(fn)
  if ok and v ~= nil then return v end
  return default
end

local function logn(msg)
  if _G.A7LOG then _G.A7LOG(msg) else print("[C1A7Check] " .. tostring(msg)) end
end

local function full(o)
  if o == nil then return "nil" end
  local s = try(function() return o:GetFullName() end, nil)
  if s then return s end
  return tostring(o)
end

local function prop(o, name)
  if o == nil then return "nil" end
  local ok, v = pcall(function() return o:GetPropertyValue(name) end)
  if not ok then return "ERR:" .. tostring(v):sub(1, 30) end
  if v == nil then return "nil" end
  local t = type(v)
  if t == "number" then return string.format("%.4f", v) end
  if t == "boolean" then return v and "true" or "false" end
  if t == "string" then return esc(v) end
  local s = try(function() return v:GetFullName() end, nil)
  if s then return esc(s) end
  return esc(tostring(v))
end

local function vec(o)
  if o == nil then return nil end
  local x = try(function() return o.X end, nil)
  local y = try(function() return o.Y end, nil)
  local z = try(function() return o.Z end, nil)
  if x == nil or y == nil or z == nil then return nil end
  return tonumber(x), tonumber(y), tonumber(z)
end

local function v3(o)
  local x, y, z = vec(o)
  if x == nil then return "null" end
  return string.format("[%.2f,%.2f,%.2f]", x, y, z)
end

-- which of our three layers is this actor?
local function layerOf(meshPath)
  if meshPath == nil then return "?" end
  local p = string.lower(tostring(meshPath))
  if string.find(p, "/meshes_nocollision/", 1, true) then return "nc" end
  if string.find(p, "/meshes/", 1, true) then return "structural" end
  return "?"
end

local function meshPathOf(comp)
  local m = try(function() return comp:GetPropertyValue("StaticMesh") end, nil)
  if m == nil then return nil end
  local s = try(function() return m:GetFullName() end, nil)
  return s
end

-- one material slot: the object the renderer binds and its BaseColor texture
local function slotInfo(mesh, i)
  local ok, mat = pcall(function() return mesh:GetMaterial(i) end)
  if not ok or mat == nil then return nil, "GetMaterial failed: " .. tostring(mat):sub(1, 40) end
  local rec = {}
  rec.idx = i
  rec.mat = esc(full(mat))
  -- GetTextureParameterValue's signature differs between UE versions and MI classes: try the
  -- one-arg form first (UMaterialInstanceDynamic), then the two-arg form, then give up clearly.
  local okA, texA = pcall(function() return mat:GetTextureParameterValue("BaseColor") end)
  local okB, texB = false, nil
  if not okA or texA == nil then
    okB, texB = pcall(function() return mat:GetTextureParameterValue("BaseColor", false) end)
  end
  local tex = (okA and texA) or (okB and texB) or nil
  if tex ~= nil then
    rec.basecolor = esc(full(tex))
  else
    rec.basecolor = (okA or okB) and "NULL" or "NO_FN"
  end
  return rec
end

-- Trace helper. The signature of UKismetSystemLibrary:LineTraceSingle differs between UE4SS
-- builds; each variant is attempted once and the winner is remembered for the whole run.
local traceAPI = { kind = "untried", ctx = nil }

local function worldCtx()
  if traceAPI.ctx then return traceAPI.ctx end
  local pc = try(function() return UEHelpers.GetPlayerController() end, nil)
  if pc == nil then
    local pcs = try(function() return FindAllOf("PlayerController") end, nil)
    if pcs then
      for _, p in ipairs(pcs) do
        if try(function() return p:IsLocalPlayerController() end, false) == true then pc = p; break end
      end
    end
  end
  traceAPI.ctx = pc
  if pc ~= nil and not traceAPI.ctxLogged then
    traceAPI.ctxLogged = true
    logn("player controller resolved: " .. tostring(try(function() return pc:GetFullName() end, "?")))
  end
  return pc
end

-- returns hit(bool), actorName, hitZ, normalZ, errorString
local function traceDown(x, y, z, ignore)
  local ctx = worldCtx()
  if ctx == nil then return nil, nil, nil, nil, "no player controller" end
  local KSL = try(function() return StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end, nil)
    or try(function() return FindFirstOf("KismetSystemLibrary") end, nil)
  if KSL == nil then return nil, nil, nil, nil, "KismetSystemLibrary not reachable" end

  local startV = { X = x, Y = y, Z = z }
  local endV   = { X = x, Y = y, Z = z - 600.0 }
  local hit    = {}

  local attempts = {
    function() return KSL:LineTraceSingle(ctx, startV, endV, 0, true, ignore, 0, hit, true, {X=0,Y=0,Z=0}, {X=0,Y=0,Z=0}, 1.0) end,
    function() return KSL:LineTraceSingle(ctx, startV, endV, 0, true, ignore, 0, hit) end,
  }
  for i, fn in ipairs(attempts) do
    local ok, r = pcall(fn)
    if ok then
      traceAPI.kind = "LineTraceSingle v" .. i
      local bHit = try(function() return hit.bBlockingHit end, nil)
      if bHit == nil then bHit = try(function() return hit.bBlockingHit end, false) end
      local actor = try(function() return hit.HitActor end, nil)
      local loc = try(function() return hit.Location end, nil)
      local _, _, hz = vec(loc)
      local nrm = try(function() return hit.Normal end, nil)
      local _, _, nz = vec(nrm)
      return (bHit == true), full(actor), hz, nz, nil
    end
  end
  traceAPI.kind = "all variants failed"
  return nil, nil, nil, nil, "LineTraceSingle: no working signature"
end

local function writeAlive()
  local f = io.open(ALIVE, "w")
  if f then
    f:write("loaded " .. VER .. " " .. os.date("!%Y-%m-%dT%H:%M:%SZ") .. "\n")
    f:close()
  end
end

local function collect()
  local acts = try(function() return FindAllOf("StaticMeshActor") end, nil)
  if acts == nil then return false, "FindAllOf(StaticMeshActor) unavailable" end

  local ours, allCount = {}, #acts
  for _, a in ipairs(acts) do
    local ok, comp = pcall(function() return a:GetPropertyValue("StaticMeshComponent") end)
    if not ok or comp == nil then pcall(function() comp = a.StaticMesh end) end
    if comp ~= nil then
      local mp = meshPathOf(comp)
      if mp and string.find(string.lower(mp), "/mods/c1full/", 1, true) then
        ours[#ours + 1] = { actor = a, comp = comp, mesh = mp }
      end
    end
  end
  if #ours < 700 then return false, string.format("only %d C1Full actors (%d actors total)", #ours, allCount) end

  local f = io.open(OUT, "w")
  if not f then return false, "cannot open " .. OUT end
  f:write('{"ver":"' .. VER .. '","time":"' .. os.date("!%Y-%m-%dT%H:%M:%SZ") .. '",')
  f:write('"all_actors":' .. allCount .. ',"our_actors":' .. #ours .. ',')
  f:write('"trace_api":"' .. esc(traceAPI.kind) .. '",')

  -- counts by layer, so a missing layer is visible immediately
  local counts = { structural = 0, nc = 0, other = 0 }
  for _, e in ipairs(ours) do
    local l = layerOf(e.mesh)
    if l == "structural" then counts.structural = counts.structural + 1
    elseif l == "nc" then counts.nc = counts.nc + 1
    else counts.other = counts.other + 1 end
  end
  f:write('"counts":{"structural":' .. counts.structural .. ',"nc":' .. counts.nc ..
          ',"other":' .. counts.other .. '},')

  f:write('"actors":[')
  local detail = 0
  for i, e in ipairs(ours) do
    local a, comp, mp = e.actor, e.comp, e.mesh
    local loc = try(function() return a:K2_GetActorLocation() end, nil)
    local layer = layerOf(mp)
    local rec = {}
    rec.name = esc(try(function() return a:GetName() end, "?"))
    rec.layer = layer
    rec.mesh = esc(mp)
    rec.loc = v3(loc)
    rec.visible = prop(comp, "bVisible")
    rec.mobility = prop(comp, "Mobility")
    rec.profile = prop(comp, "CollisionProfileName")

    local mesh = try(function() return comp:GetPropertyValue("StaticMesh") end, nil)
    local nslots = 0
    if mesh then nslots = try(function() return mesh:GetNumSections(0) end, 0) or 0 end
    local nmats = 0
    if mesh then
      nmats = try(function() return #mesh:GetPropertyValue("StaticMaterials") end, 0) or 0
      if nmats == 0 then nmats = nslots end
    end
    rec.slots = nmats

    -- material detail: every NC actor, plus a capped number of structural ones
    local wantDetail = (layer == "nc") or (detail < MAX_ACTORS_DETAIL)
    if wantDetail and mesh and nmats > 0 then
      detail = detail + 1
      local parts = {}
      local cap = math.min(nmats, MAX_SLOTS_FULL)
      local failed = nil
      for s = 0, cap - 1 do
        local si, err = slotInfo(mesh, s)
        if si then
          parts[#parts + 1] = string.format('{"i":%d,"mat":"%s","bc":"%s"}', si.idx, si.mat, si.basecolor)
        else
          failed = err
          break
        end
      end
      rec.mats = "[" .. table.concat(parts, ",") .. "]"
      if failed then rec.mats_err = esc(failed) end
      if nmats > cap then rec.mats_trunc = nmats - cap end
    else
      rec.mats = "null"
    end

    -- traces: only over the no-collision layer and the paint mesh, where the question is
    -- "does anything here stop a car". A 3x3 grid inside the actor bounds, 40 cm above its top.
    if layer == "nc" and traceAPI.kind ~= "all variants failed" then
      local box = try(function() return comp:GetPropertyValue("Bounds") end, nil)
      local boxOrigin = box and try(function() return box.Origin end, nil) or nil
      local boxExtent = box and try(function() return box.BoxExtent end, nil) or nil
      local ox, oy, oz = vec(boxOrigin)
      local ex, ey, ez = vec(boxExtent)
      if ox and ex and ez then
        local hits = {}
        local nullhits, otherhits, ncself = 0, 0, 0
        local traceErr = nil
        for gx = -1, 1 do
          for gy = -1, 1 do
            local h, actorName, hz, nz, err = traceDown(
              ox + gx * ex * 0.6, oy + gy * ey * 0.6, oz + ez + 40.0)
            if err then traceErr = err; break end
            local lname = string.lower(tostring(actorName or ""))
            if h ~= true or actorName == "nil" then nullhits = nullhits + 1
            elseif string.find(lname, "_nc_", 1, true) then ncself = ncself + 1
            else otherhits = otherhits + 1 end
            hits[#hits + 1] = string.format('{"hit":%s,"actor":"%s","z":%s}',
              tostring(h == true), esc(actorName or "nil"),
              hz and string.format("%.2f", hz) or "null")
          end
          if traceErr then break end
        end
        rec.traces = "[" .. table.concat(hits, ",") .. "]"
        rec.trace_summary = string.format('{"none":%d,"nc":%d,"other":%d}', nullhits, ncself, otherhits)
        if traceErr then rec.trace_err = esc(traceErr) end
      else
        rec.traces = "null"
      end
    end

    f:write('{"name":"' .. rec.name .. '","layer":"' .. rec.layer .. '","mesh":"' .. rec.mesh ..
            '","loc":' .. rec.loc .. ',"visible":"' .. rec.visible .. '","mobility":"' .. rec.mobility ..
            '","profile":"' .. rec.profile .. '","slots":' .. rec.slots ..
            ',"mats":' .. rec.mats)
    if rec.mats_err then f:write(',"mats_err":"' .. rec.mats_err .. '"') end
    if rec.mats_trunc then f:write(',"mats_trunc":' .. rec.mats_trunc) end
    if rec.traces and rec.traces ~= "null" then f:write(',"traces":' .. rec.traces) end
    if rec.trace_summary then f:write(',"trace_summary":' .. rec.trace_summary) end
    f:write('}')
    if i < #ours then f:write(',') end
  end
  f:write(']}')
  f:close()
  return true, string.format("wrote %s actors=%d structural=%d nc=%d trace=%s",
    OUT, #ours, counts.structural, counts.nc, traceAPI.kind)
end

do
  writeAlive()
  print("[C1A7Check] " .. VER .. " loaded")
end

-- =====================================================================================
-- Level travel + API discovery
--
-- There is no "start a Time Attack" function in the C++ SDK: EMotorTownGameType has
-- TimeAttack, UMTGameResource.TimeAttackMaps is a TArray<FMTMap> of soft level pointers,
-- and the actual start lives in blueprint (UStartOfflineTimeAttackWidget has LevelsSpinBox /
-- VehiclesSpinBox, i.e. it picks from that array). So the generic engine route is the reliable
-- one for LOADING a level, and the TA entry point has to be discovered at runtime with
-- UStruct:ForEachFunction, then called through UFunction:__call.
--
-- F9  -> OpenLevel(/Game/Mods/C1Full/Maps/C1Full)
-- F7  -> dump every function of the interesting objects to D:/c1_fns.json
-- =====================================================================================

local FNS = "D:/c1_fns.json"
local LEVEL = "/Game/Mods/C1Full/Maps/C1Full"

local function kismetLib()
  return try(function() return StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end, nil)
    or try(function() return FindFirstOf("KismetSystemLibrary") end, nil)
end

local function loadC1(lvl)
  local pc = worldCtx()
  if pc == nil then logn("[C1A7Check] loadC1: no player controller"); return false end
  lvl = lvl or LEVEL

  -- ON THIS BUILD an unknown member does not return nil, it returns a TrivialObject, and calling
  -- one raises "attempt to call a TrivialObject value". So each attempt is named in the log and a
  -- TrivialObject means "that function does not exist here", not "it failed at runtime".
  --
  -- Order is by how much reflection each one needs:
  --   1. UGameplayStatics:OpenLevel  -- the documented travel API (this is the one that owns it;
  --                                     KismetSystemLibrary does NOT have OpenLevel)
  --   2. KismetSystemLibrary:ExecuteConsoleCommand -- 'open <package>' through the console verb
  --   3. APlayerController:ClientTravel -- signature is (URL, TravelType, bSeamless, FGuid)
  local GPS = try(function() return StaticFindObject("/Script/Engine.Default__GameplayStatics") end, nil)
  if GPS ~= nil then
    for i, fn in ipairs({
      function() return GPS:OpenLevel(pc, FName(lvl), true, "") end,
      function() return GPS:OpenLevel(pc, FName(lvl), true) end,
      function() return GPS:OpenLevel(pc, lvl, true, "") end,
    }) do
      local ok, err = pcall(fn)
      if ok then logn("[C1A7Check] GameplayStatics:OpenLevel v" .. i .. " -> " .. lvl); return true end
      logn("[C1A7Check] GameplayStatics:OpenLevel v" .. i .. " failed: " .. tostring(err):sub(-90))
    end
  else
    logn("[C1A7Check] no GameplayStatics CDO")
  end

  local KSL = kismetLib()
  if KSL ~= nil then
    for i, fn in ipairs({
      function() return KSL:ExecuteConsoleCommand(pc, "open " .. lvl, nil) end,
      function() return KSL:ExecuteConsoleCommand(pc, "open " .. lvl) end,
    }) do
      local ok, err = pcall(fn)
      if ok then logn("[C1A7Check] ExecuteConsoleCommand v" .. i .. " -> open " .. lvl); return true end
      logn("[C1A7Check] ExecuteConsoleCommand v" .. i .. " failed: " .. tostring(err):sub(-90))
    end
  end

  for i, fn in ipairs({
    function() return pc:ClientTravel(lvl, 0, false) end,
    function() return pc:ClientTravel(lvl, 0, false, FGuid and FGuid(0,0,0,0) or nil) end,
  }) do
    local ok, err = pcall(fn)
    if ok then logn("[C1A7Check] ClientTravel v" .. i .. " -> " .. lvl); return true end
    logn("[C1A7Check] ClientTravel v" .. i .. " failed: " .. tostring(err):sub(-90))
  end

  return false
end

local KEYWORDS = { "timeattack", "time_attack", "travel", "openlevel", "open_level",
                   "loadlevel", "start", "session", "level", "map", "join", "host" }

local function interesting(name)
  local l = string.lower(tostring(name or ""))
  for _, k in ipairs(KEYWORDS) do
    if string.find(l, k, 1, true) then return true end
  end
  return false
end

local function dumpFunctions()
  local targets = {}
  local function add(tag, o)
    if o ~= nil then targets[#targets + 1] = { tag = tag, o = o } end
  end
  add("GameInstance", try(function() return FindFirstOf("MotorTownGameInstance") end, nil)
                   or try(function() return FindFirstOf("GameInstance") end, nil))
  local pc = worldCtx(); add("PlayerController", pc)
  add("GameState", try(function() return FindFirstOf("MotorTownGameState") end, nil)
                or try(function() return FindFirstOf("GameStateBase") end, nil))
  add("GameSession", try(function() return FindFirstOf("MTGameSession") end, nil)
                   or try(function() return FindFirstOf("GameSession") end, nil))
  add("GameResource", try(function()
        local gi = FindFirstOf("MotorTownGameInstance")
        if gi then return gi:GetPropertyValue("GameResource") end
      end, nil))
  -- widgets: the Time Attack UI is where the start logic lives
  local ws = try(function() return FindAllOf("UserWidget") end, nil) or {}
  local nw = 0
  for _, w in ipairs(ws) do
    local cn = try(function() return w:GetClass():GetName() end, "")
    if interesting(cn) and nw < 40 then
      nw = nw + 1
      add("Widget:" .. tostring(cn), w)
    end
  end

  local f = io.open(FNS, "w")
  if not f then return false, "cannot write " .. FNS end
  f:write('{"ver":"' .. VER .. '","time":"' .. os.date("!%Y-%m-%dT%H:%M:%SZ") .. '","objects":[')
  local emitted = 0
  for _, t in ipairs(targets) do
    local ok, cls = pcall(function() return t.o:GetClass() end)
    if ok and cls then
      if emitted > 0 then f:write(',') end
      emitted = emitted + 1
      f:write('{"tag":"' .. esc(t.tag) .. '","object":"' .. esc(full(t.o)) ..
              '","class":"' .. esc(try(function() return cls:GetName() end, "?")) .. '","fns":[')
      local first, total, matched = true, 0, 0
      local ok2 = pcall(function()
        cls:ForEachFunction(function(fn)
          total = total + 1
          local name = try(function() return fn:GetName() end, "?")
          if interesting(name) or total <= 40 then
            matched = matched + 1
            local flags = try(function() return fn:GetFunctionFlags() end, 0)
            if not first then f:write(',') end
            first = false
            f:write('{"n":"' .. esc(name) .. '","f":' .. tostring(flags) .. '}')
          end
          return false
        end)
      end)
      f:write('],"total":' .. total .. ',"matched":' .. matched .. ',"ok":' .. tostring(ok2) .. '}')
    end
  end
  f:write(']}')
  f:close()
  return true, string.format("wrote %s objects=%d", FNS, emitted)
end

pcall(function() RegisterKeyBind(Key.F9, {}, function() pcall(loadC1) end) end)
pcall(function() RegisterKeyBind(Key.F7, {}, function()
  local ok, res, why = pcall(dumpFunctions)
  print("[C1A7Check] fns: " .. tostring(ok and why or res))
end) end)

-- ---------------------------------------------------------------------------------------------
-- Autoload: if D:/c1_autoload.txt exists, walk into that level without touching the menu.
-- The file holds the package path (empty file -> the C1 default). Deleting it returns the mod to
-- purely manual behaviour, which is the point: the agent can drive a run, and so can you, with no
-- edit either way.
--
-- Why the bespoke waiting instead of one delay: OpenLevel before the game instance and a local
-- player controller exist is a crash, and the main menu takes a variable amount of time to appear.
-- So the gate is "a local PC exists AND some seconds have passed", retried, and it fires once.
-- ---------------------------------------------------------------------------------------------
local AUTOLOAD = "D:/c1_autoload.txt"
local AUTOLOG  = "D:/c1_autoload.log"

local function autolog(msg)
  _G.A7LOG = autolog
  pcall(function()
    local f = io.open(AUTOLOG, "a")
    if f then f:write(os.date("!%H:%M:%S ") .. tostring(msg) .. "\n"); f:close() end
  end)
  print("[C1A7Check] autoload: " .. tostring(msg))
end

local function autoloadTarget()
  local f = io.open(AUTOLOAD, "r")
  if not f then return nil end
  local line = f:read("*l")
  f:close()
  if line == nil or line == "" or line == "default" then return LEVEL end
  return line
end

local target = autoloadTarget()
if target then
  autolog("marker found, target=" .. target .. " (waiting for a player controller)")
  local fired = false
  local startedAt = os.clock()
  LoopAsync(4000, function()
    if fired then return true end
    local pc = worldCtx()
    local elapsed = os.clock() - startedAt
    if pc == nil or elapsed < 25 then return false end
    -- already there? then there is nothing to do
    local already = false
    local acts = try(function() return FindAllOf("StaticMeshActor") end, nil) or {}
    local ours = 0
    for _, a in ipairs(acts) do
      local mp = try(function() return a:GetStaticMeshComponent():GetPropertyValue("StaticMesh"):GetFullName() end, nil)
      if mp and string.find(string.lower(mp), "/mods/c1full/", 1, true) then ours = ours + 1; if ours > 5 then break end end
    end
    already = ours > 5
    if already then
      fired = true
      autolog("already in the C1 level, no travel needed")
      return true
    end
    local attempts = 0
    local ok = false
    while attempts < 3 and not ok do
      attempts = attempts + 1
      autolog(string.format("travel attempt %d to %s at %.0fs", attempts, target, elapsed))
      ok = loadC1(target)
    end
    if ok then
      fired = true
      autolog("travel issued, waiting for the level to load")
      return true
    end
    autolog("all travel methods failed; will retry on the next tick")
    return false
  end)
else
  autolog("no marker, manual mode (F9 loads, F10 collects)")
end

local done = false
LoopAsync(3000, function()
  if done then return true end
  local ok, res, why = pcall(collect)
  if ok and res then
    done = true
    print("[C1A7Check] " .. tostring(why))
    return true
  end
  return false
end)

pcall(function()
  RegisterKeyBind(Key.F10, {}, function()
    local ok, res, why = pcall(collect)
    if ok and res then print("[C1A7Check] manual: " .. tostring(why))
    else print("[C1A7Check] manual failed: " .. tostring(why)) end
  end)
end)
