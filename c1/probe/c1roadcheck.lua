-- C1RoadCheck: verify the installed road pak at runtime.
-- Reports, from the live game:
--   * how many MotorTownRoad actors exist and their properties (type, lanes, width, speed)
--   * spline point counts and first/last world locations, so seams can be re-measured in-game
--   * MotorTownNavigation GraphData node count, before and after calling BuildNavigation()
-- Output: D:/c1_roadcheck.json   (single valid JSON object, written once)

local OUT = "D:/c1_roadcheck.json"
local ALIVE = "D:/c1_roadcheck_alive.txt"
local MAX_WAIT_MS = 120000
local started = os.clock()

local function esc(s)
  return (tostring(s):gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\r', ''):gsub('\n', ' '))
end

local function try(fn, default)
  local ok, v = pcall(fn)
  if ok and v ~= nil then return v end
  return default
end

local function num(v, default)
  if type(v) == "number" then return string.format("%.3f", v) end
  return default or "null"
end

local function pointOf(spline, idx)
  -- UE adds a "World" coordinate space enum; 0 is World in shipping builds.
  local loc = try(function() return spline:GetLocationAtSplinePoint(idx, 0) end, nil)
  if loc == nil then return nil end
  local x = try(function() return loc.X end, nil)
  if x == nil then x = try(function() return loc.x end, nil) end
  local y = try(function() return loc.Y end, nil)
  if y == nil then y = try(function() return loc.y end, nil) end
  local z = try(function() return loc.Z end, nil)
  if z == nil then z = try(function() return loc.z end, nil) end
  if x == nil or y == nil then return nil end
  return { tonumber(x), tonumber(y), tonumber(z) or 0 }
end

local function splineOf(actor)
  return try(function() return actor.Spline end, nil)
    or try(function() return actor.RootComponent end, nil)
end

local function roadEntry(a, i)
  local name = try(function() return a:GetFullName() end, "road" .. i)
  local s = {}
  s.name = esc(name)
  s.type = tostring(try(function() return a.RoadType end, "?"))
  s.forward = num(try(function() return a.NumForwardLanes end, nil))
  s.backward = num(try(function() return a.NumBackwardLanes end, nil))
  s.width = num(try(function() return a.LaneWidth end, nil))
  s.speed = num(try(function() return a.SpeedLimitKPH end, nil))
  s.course_key = esc(try(function() return a.CourseKey end, ""))

  local spl = splineOf(a)
  if spl then
    local n = try(function() return spl:GetNumberOfSplinePoints() end, nil)
    s.points = num(n)
    if type(n) == "number" and n > 0 then
      local p0 = pointOf(spl, 0)
      local pn = pointOf(spl, n - 1)
      s.start = p0 and string.format("[%.2f,%.2f,%.2f]", p0[1], p0[2], p0[3]) or "null"
      s.finish = pn and string.format("[%.2f,%.2f,%.2f]", pn[1], pn[2], pn[3]) or "null"
    end
  else
    s.points = "no_spline"
  end
  return s
end

local function navEntry(nav)
  local e = {}
  e.name = esc(try(function() return nav:GetFullName() end, "nav"))
  e.nodes_before = num(try(function() return nav.GraphData.Nodes:GetArrayNum() end, nil))
  e.bounds_min = try(function()
    return string.format("[%.1f,%.1f,%.1f]", nav.GraphData.Bounds.Min.X,
                         nav.GraphData.Bounds.Min.Y, nav.GraphData.Bounds.Min.Z)
  end, "null")
  e.buildnav_ok = try(function() nav:BuildNavigation() return true end, false)
  e.nodes_after = num(try(function() return nav.GraphData.Nodes:GetArrayNum() end, nil))
  return e
end

local function write()
  local roads = FindAllOf("MotorTownRoad")
  local navs = FindAllOf("MotorTownNavigation")
  if not roads or #roads == 0 then return false end

  local f = io.open(OUT, "w")
  if not f then return true end
  f:write('{"time":"' .. os.date("!%Y-%m-%dT%H:%M:%SZ") .. '",')
  f:write('"actor_count":' .. #roads .. ',')
  f:write('"nav_count":' .. ((navs and #navs) or 0) .. ',')

  f:write('"roads":[')
  for i, a in ipairs(roads) do
    if i > 1 then f:write(',') end
    local e = roadEntry(a, i)
    f:write(string.format(
      '{"name":"%s","type":"%s","forward":%s,"backward":%s,"width":%s,"speed":%s,"course_key":"%s","points":%s,"start":%s,"finish":%s}',
      e.name, e.type, e.forward, e.backward, e.width, e.speed, e.course_key,
      e.points, e.start or "null", e.finish or "null"))
  end
  f:write('],')

  f:write('"nav":[')
  if navs then
    for i, n in ipairs(navs) do
      if i > 1 then f:write(',') end
      local e = navEntry(n)
      f:write(string.format('{"name":"%s","nodes_before":%s,"nodes_after":%s,"buildnav_ok":%s,"bounds_min":%s}',
        e.name, e.nodes_before, e.nodes_after, tostring(e.buildnav_ok), e.bounds_min))
    end
  end
  f:write(']}')
  f:close()
  print("[C1RoadCheck] wrote " .. OUT .. " roads=" .. #roads)
  return true
end

-- heartbeat: proves the mod loaded, even if the map never does
do
  local f = io.open(ALIVE, "w")
  if f then
    f:write("loaded " .. os.date("!%Y-%m-%dT%H:%M:%SZ") .. "\n")
    f:close()
  end
  print("[C1RoadCheck] main.lua executed")
end

-- wait for the map to finish loading, then write once
LoopAsync(2000, function()
  local done = false
  local ok, res = pcall(write)
  if ok and res then done = true end
  if done or (os.clock() - started) * 1000 > MAX_WAIT_MS then
    return true -- stops the loop
  end
  return false
end)
