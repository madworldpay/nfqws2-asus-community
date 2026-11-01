-- Separate, pass-through observer for the pinned NFQWS2 1.0.6 engine.
-- Load zapret-lib.lua, dns.lua, then this file.  The controller owns the
-- short-lived manifest; only events.log belongs to the engine's writable UID.
local manifest_path = IPHEALTH_MANIFEST or "/tmp/nfqws2-asus/ip-health/active.txt"
local event_path = WRITABLE and (WRITABLE .. "/events.log")
local flows, flow_count = {}, 0
local bans, enabled, expires = {}, false, 0
local last_read, last_time = -1, nil

local function clear_flows()
    flows, flow_count = {}, 0
end

local function forget(key)
    if flows[key] then flows[key] = nil; flow_count = flow_count - 1 end
end

local function clock()
    local sec, nsec = clock_gettime()
    if type(sec) ~= "number" or type(nsec) ~= "number" or
       sec < 1704067200 or sec > 4102444800 or nsec < 0 or nsec >= 1000000000 then
        return nil
    end
    return sec + nsec / 1000000000
end

-- Conservative globally routable unicast only.  In particular, translated,
-- mapped and transition IPv6 addresses cannot smuggle a local IPv4 endpoint.
local function public_ip(raw)
    if type(raw) ~= "string" then return false end
    local a,b,c,d = raw:byte(1,4)
    if #raw == 4 then
        return not (a == 0 or a == 10 or a == 127 or a >= 224 or
            (a == 100 and b >= 64 and b <= 127) or (a == 169 and b == 254) or
            (a == 172 and b >= 16 and b <= 31) or
            (a == 192 and (b == 168 or (b == 0 and (c == 0 or c == 2)) or (b == 88 and c == 99))) or
            (a == 198 and (b == 18 or b == 19 or (b == 51 and c == 100))) or
            (a == 203 and b == 0 and c == 113))
    end
    if #raw ~= 16 or a < 0x20 or a > 0x3f then return false end
    if a == 0x20 and b == 0x01 and (c < 2 or (c == 0x0d and d == 0xb8)) then return false end
    if a == 0x20 and b == 0x02 then return false end
    if a == 0x3f and b == 0xff and c < 0x10 then return false end
    return true
end

local function hostname(value)
    if type(value) ~= "string" or #value > 253 or #value < 3 or
       not value:find("%.") or not value:find("[A-Za-z]") or
       value:find("[^A-Za-z0-9.%-]") or value:sub(1,1) == "." or value:sub(-1) == "." or value:find("..",1,true) then
        return nil
    end
    for label in value:gmatch("[^.]+") do
        if #label > 63 or not label:match("^[A-Za-z0-9]") or not label:match("[A-Za-z0-9]$") then return nil end
    end
    return value:lower()
end

local function invalidate()
    bans, enabled, expires = {}, false, 0
    clear_flows()
end

local function parse_manifest(data, now)
    if type(data) ~= "string" or #data > 65536 or data:sub(-1) ~= "\n" then return nil end
    local expiration, flag, body = data:match("^IPHEALTH1\nexpires (%d+)\nenabled ([01])\n(.*)$")
    expiration = tonumber(expiration)
    if not expiration or expiration <= now or expiration > math.floor(now) + 15 then return nil end
    local result, count = {}, 0
    for line in body:gmatch("([^\n]*)\n") do
        local text, until_text = line:match("^ban ([0-9a-f:.]+) (%d+)$")
        local until_at = tonumber(until_text)
        if not text or not until_at or until_at > math.floor(now) + 604815 then return nil end
        local ok, raw = pcall(pton, text)
        if not ok or not raw or not public_ip(raw) or ntop(raw) ~= text or result[raw] then return nil end
        count = count + 1
        if count > 512 then return nil end
        if until_at > now then result[raw] = until_at end
    end
    -- An empty enabled manifest is normal.  Disabled manifests retain no bans.
    return flag == "1", result, expiration
end

local function active()
    local now = clock()
    if not now then invalidate(); last_read = -1; last_time = nil; return false end
    if last_time and now < last_time then invalidate(); last_read = -1 end
    last_time = now
    if last_read < 0 or now - last_read >= 1 then
        last_read = now
        local f = io.open(manifest_path, "rb")
        local data
        if f then data = f:read(65537); f:close() end
        local flag, result, expiration = parse_manifest(data, now)
        if flag == nil then invalidate()
        else
            enabled, bans, expires = flag, result, expiration
            if not enabled then clear_flows() end
        end
    end
    if now >= expires then invalidate() end
    return enabled, now
end

local function banned(raw, now)
    local until_at = bans[raw]
    return enabled and until_at ~= nil and until_at > now
end

local function emit(kind, now, ip, port, host)
    if not event_path then return end
    local line = kind .. "|" .. math.floor(now) .. "|" .. ntop(ip) .. "|" .. port .. "|" .. (host or "") .. "\n"
    local f = io.open(event_path, "ab")
    if not f then return end
    local size = f:seek("end")
    if size and size + #line <= 262144 then f:write(line) end
    f:close()
end

-- The pinned C rawsend_dissect always adds its configured desync mark and
-- recalculates L3/L4 checksums.  Preserve the packet's other routing mark bits.
-- Do not bind a reverse client refusal to the packet's original WAN ifout.
local function send(dis, fwmark, ifout)
    local ok, sent = pcall(rawsend_dissect, dis, { fwmark = fwmark, ifout = ifout })
    return ok and sent == true
end

local function reset(dis, fwmark, payload_length)
    local flags = dis.tcp.th_flags
    if bitand(flags, TH_RST) ~= 0 then return false end
    local reply = deepcopy(dis)
    dis_reverse(reply)
    reply.payload, reply.frag_off = "", nil
    reply.tcp.options, reply.tcp.th_win, reply.tcp.th_urp, reply.tcp.th_x2 = {}, 0, 0, 0
    if bitand(flags, TH_ACK) ~= 0 then
        reply.tcp.th_flags, reply.tcp.th_seq, reply.tcp.th_ack = TH_RST, dis.tcp.th_ack, 0
    else
        local length = payload_length or #(dis.payload or "")
        if bitand(flags, TH_SYN) ~= 0 then length = length + 1 end
        if bitand(flags, TH_FIN) ~= 0 then length = length + 1 end
        reply.tcp.th_flags, reply.tcp.th_seq = bitor(TH_RST, TH_ACK), 0
        reply.tcp.th_ack = u32add(dis.tcp.th_seq, length)
    end
    if reply.ip then
        reply.ip.ip_off, reply.ip.options, reply.ip.ip_hl, reply.ip.ip_ttl = 0, nil, 5, 64
    elseif reply.ip6 then
        reply.ip6.exthdr, reply.ip6.ip6_nxt, reply.ip6.ip6_hlim = nil, IPPROTO_TCP, 64
    end
    return send(reply, fwmark)
end

local function tuple(desync)
    local dis, outgoing = desync.dis, desync.outgoing
    local server = outgoing and dis_ipdst(dis) or dis_ipsrc(dis)
    local client = outgoing and dis_ipsrc(dis) or dis_ipdst(dis)
    local port = outgoing and dis.tcp.th_sport or dis.tcp.th_dport
    if not public_ip(server) or type(client) ~= "string" or type(port) ~= "number" or port < 1 or port > 65535 then return nil end
    return client .. server .. bu16(port), server, port
end

local function complete_hello(data)
    if type(data) ~= "string" or #data > 65535 or not is_tls_record(data, 1, TLS_RECORD_TYPE_HANDSHAKE, false) then return false end
    local ok, parsed = pcall(tls_dissect, data)
    local hello = ok and parsed and parsed.handshake and parsed.handshake[TLS_HANDSHAKE_TYPE_CLIENT]
    return hello and hello.dis ~= nil and is_tls_handshake(hello.data, 1, TLS_HANDSHAKE_TYPE_CLIENT, false)
end

local function tcp_observe(ctx, desync)
    local on, now = active()
    if not on then return VERDICT_PASS end
    local dis = desync.dis
    if not dis or not dis.tcp or dis.frag_off ~= nil then return VERDICT_PASS end
    local remote_port = desync.outgoing and dis.tcp.th_dport or dis.tcp.th_sport
    if remote_port ~= 443 then return VERDICT_PASS end
    local key, ip, port = tuple(desync)
    if not key then return VERDICT_PASS end
    if not desync.outgoing then
        if #(dis.payload or "") > 0 or bitand(dis.tcp.th_flags, bitor(TH_RST,TH_FIN)) ~= 0 then
            if flows[key] then emit("reply", now, ip, 0); forget(key) end
        end
        return VERDICT_PASS
    end
    if banned(ip, now) and reset(dis, desync.fwmark) then forget(key); return VERDICT_DROP end
    if bitand(dis.tcp.th_flags, bitor(TH_RST,TH_FIN)) ~= 0 then forget(key); return VERDICT_PASS end
    local observed = desync.track and desync.track.lua_state and desync.track.lua_state.ip_health_observed
    if bitand(dis.tcp.th_flags, TH_SYN) ~= 0 and not observed then forget(key) end
    if flows[key] or flow_count >= 512 or observed then return VERDICT_PASS end
    local host = desync.track and not desync.track.hostname_is_ip and hostname(desync.track.hostname)
    if host and complete_hello(desync.reasm_data or dis.payload) then
        -- Retain only headers for a later client RST, never the ClientHello.
        local saved = deepcopy(dis)
        saved.payload = ""
        flows[key] = { started = now, ip = ip, port = port, host = host, dis = saved, payload_length = #(dis.payload or ""),
                       fwmark = desync.fwmark, reported = false }
        flow_count = flow_count + 1
        if desync.track.lua_state then desync.track.lua_state.ip_health_observed = true end
    end
    return VERDICT_PASS
end

local function udp_refuse(ctx, desync)
    local on, now = active()
    local dis = desync.dis
    if not on or not desync.outgoing or not dis or not dis.udp or dis.udp.uh_dport ~= 443 or dis.frag_off ~= nil then return VERDICT_PASS end
    local ip = dis_ipdst(dis)
    if not public_ip(ip) or not banned(ip, now) then return VERDICT_PASS end
    local raw = raw_packet(ctx)
    if type(raw) ~= "string" then return VERDICT_PASS end
    local reply = { payload = "", icmp = {icmp_type = dis.ip and 3 or 1, icmp_code = dis.ip and 3 or 4, icmp_data = 0} }
    if dis.ip then
        local header_length = (raw:byte(1) % 16) * 4
        if header_length < 20 or #raw < header_length + 8 then return VERDICT_PASS end
        reply.ip = {ip_v=4, ip_hl=5, ip_tos=0, ip_id=0, ip_off=0, ip_ttl=64, ip_p=IPPROTO_ICMP,
                    ip_src=dis.ip.ip_dst, ip_dst=dis.ip.ip_src}
        reply.payload = raw:sub(1, header_length + 8)
    elseif dis.ip6 then
        if #raw < 48 then return VERDICT_PASS end
        reply.ip6 = {ip6_flow=0x60000000, ip6_nxt=IPPROTO_ICMPV6, ip6_hlim=64, ip6_src=dis.ip6.ip6_dst, ip6_dst=dis.ip6.ip6_src}
        reply.payload = raw:sub(1, 1232) -- fit the IPv6 minimum MTU including outer IP/ICMP
    else return VERDICT_PASS end
    if send(reply, desync.fwmark) then return VERDICT_DROP end
    return VERDICT_PASS
end

-- dns.lua is deliberately loaded before this shared runtime is initialized.
nfqws_ip_health = { active = active, banned = banned, public_ip = public_ip, send = send }

function ip_health_tcp(ctx, desync)
    local ok, verdict = pcall(tcp_observe, ctx, desync)
    return ok and verdict or VERDICT_PASS
end

function ip_health_udp(ctx, desync)
    local ok, verdict = pcall(udp_refuse, ctx, desync)
    return ok and verdict or VERDICT_PASS
end

timer_set("ip_health_silence", function()
    local on, now = active()
    if not on then return end
    for key, flow in pairs(flows) do
        if now - flow.started >= 15 then forget(key)
        elseif banned(flow.ip, now) then
            if reset(flow.dis, flow.fwmark, flow.payload_length) then forget(key) end
        elseif now - flow.started >= 3 and not flow.reported then
            flow.reported = true
            emit("silent", now, flow.ip, flow.port, flow.host)
        end
    end
end, 500, false)
