-- C1Probe v3: components/child-actor of the garage, and what is near it.
local MOD = "[C1Probe] "
local done = false
local GX, GY, GZ = 136645.1, -654630.6, 85843.7

local function body(w)
    local ok, ws = pcall(FindAllOf, "World")
    w("level=" .. tostring(ws and ws[1] and ws[1]:GetFullName()))

    -- child actor components belonging to the garage
    local okc, comps = pcall(FindAllOf, "ChildActorComponent")
    w("childcomp_total=" .. tostring(okc and comps and #comps or -1))
    if okc and comps then
        for _, c in ipairs(comps) do
            local nm = "?"
            pcall(function() nm = c:GetFullName() end)
            if string.find(nm, "BP_C1_Prop", 1, true) then
                w("GARAGE_CHILDCOMP " .. nm)
                local cls, act = "?", "?"
                pcall(function() cls = tostring(c:GetChildActorClass()) end)
                pcall(function() act = tostring(c:GetChildActor()) end)
                w("    childClass=" .. cls)
                w("    childActor=" .. act)
            end
        end
    end

    -- static mesh components owned by the garage
    local oks, smcs = pcall(FindAllOf, "StaticMeshComponent")
    if oks and smcs then
        for _, m in ipairs(smcs) do
            local nm, own = "?", "?"
            pcall(function() nm = m:GetFullName() end)
            if string.find(nm, "BP_C1_Prop", 1, true) then
                pcall(function() own = tostring(m:GetOwner():GetFullName()) end)
                w("GARAGE_SMC " .. nm .. " owner=" .. own)
            end
        end
    end

    -- anything within 3000cm of the expected spot
    local okA, actors = pcall(FindAllOf, "Actor")
    if okA and actors then
        local near = 0
        for _, a in ipairs(actors) do
            local nm = "?"
            pcall(function() nm = a:GetFullName() end)
            local okd, d = pcall(function()
                local l = a:K2_GetActorLocation()
                return math.sqrt((l.X-GX)^2 + (l.Y-GY)^2 + (l.Z-GZ)^2)
            end)
            if okd and d and d < 3000 then
                w(string.format("NEAR %.0fcm %s", d, nm))
                near = near + 1
                if near > 20 then w("...near truncated"); break end
            end
        end
        w("near_count=" .. near)
    end
end

local function dump()
    if done then return true end
    local ok, ws = pcall(FindAllOf, "World")
    if not ok or not ws or #ws == 0 then return false end
    done = true
    ExecuteInGameThread(function()
        local f = io.open("D:/c1probe3.txt", "w")
        local function w(s) print(MOD .. s .. "\n"); if f then f:write(s .. "\n"); f:flush() end end
        w("=== C1Probe v3 ===")
        local okb, err = pcall(body, w)
        if not okb then w("BODY_ERROR " .. tostring(err)) end
        w("=== end ===")
        if f then f:close() end
    end)
    return true
end

LoopAsync(2000, dump)
