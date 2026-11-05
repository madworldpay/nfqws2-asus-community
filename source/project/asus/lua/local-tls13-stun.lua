-- ClientHello offers TLS 1.3; this is not the negotiated server version.
-- Only a complete, bounded ClientHello may populate the per-flow boolean cache.
-- No packet bytes or strategy settings are changed by this predicate.
local MAX_HELLO, MAX_RECORDS = 65535, 64
local function u16(raw, at)
    local a, b = raw:byte(at, at + 1)
    if b then return a * 256 + b end
end
local function u24(raw, at)
    local a, b, c = raw:byte(at, at + 2)
    if c then return a * 65536 + b * 256 + c end
end
local function bounded_input(raw)
    if #raw < 4 or #raw > MAX_HELLO + MAX_RECORDS * 5 then return false end
    if raw:byte(1) == 1 then return #raw <= MAX_HELLO end
    local at, records = 1, 0
    while at <= #raw do
        records = records + 1
        local length = u16(raw, at + 3)
        if records > MAX_RECORDS or raw:byte(at) ~= 22 or
            raw:byte(at + 1) ~= 3 or (raw:byte(at + 2) or 255) > 3 or
            not length or length == 0 or length > 16384 or at + 4 + length > #raw then
            return false
        end
        at = at + 5 + length
    end
    return true
end
local function offers_tls13(hello)
    if type(hello) ~= "string" or #hello < 44 or #hello > MAX_HELLO or hello:byte(1) ~= 1 or
        u24(hello, 2) ~= #hello - 4 then return nil end
    local last, session = #hello, hello:byte(39)
    if session > 32 then return nil end
    local at = 40 + session
    local length = u16(hello, at)
    if not length or length < 2 or length % 2 ~= 0 or at + 2 + length > last then return nil end
    at = at + 2 + length
    length = hello:byte(at)
    if not length or length < 1 or at + 1 + length > last then return nil end
    at = at + 1 + length
    length = u16(hello, at)
    if not length or at + 1 + length ~= last then return nil end
    at = at + 2
    local offered, seen = false, {}
    while at <= last do
        local kind = u16(hello, at)
        length = u16(hello, at + 2)
        if not length or at + 3 + length > last or seen[kind] then return nil end
        seen[kind] = true
        if kind == 43 then
            local count = hello:byte(at + 4)
            if not count or count < 2 or count % 2 ~= 0 or count ~= length - 1 then return nil end
            for pos = at + 5, at + 3 + length, 2 do
                if u16(hello, pos) == 0x0304 then offered = true end
            end
        end
        at = at + 4 + length
    end
    return offered
end
function nfqws_local_offers_tls13(desync)
    if type(desync) ~= "table" then return false end
    local track, state = desync.track
    if track ~= nil then
        if type(track) ~= "table" then return false end
        state = track.lua_state
        if state ~= nil and type(state) ~= "table" then return false end
    end
    if state and state.nfqws_local_tls13 ~= nil then return state.nfqws_local_tls13 == true end
    local raw = desync.reasm_data
    if raw == nil and type(desync.dis) == "table" then raw = desync.dis.payload end
    if type(raw) ~= "string" or not bounded_input(raw) or type(tls_dissect) ~= "function" then return false end
    local ok, parsed = pcall(tls_dissect, raw)
    if not ok or type(parsed) ~= "table" or type(parsed.handshake) ~= "table" then return false end
    local hello = parsed.handshake[1]
    if type(hello) ~= "table" or hello.type ~= 1 then return false end
    local offered = offers_tls13(hello.data)
    if offered == nil then return false end
    if state then state.nfqws_local_tls13 = offered end
    return offered
end
