-- Conservative UDP DNS response rebuilding.  Never splice compressed wire data:
-- all retained owner/CNAME names are decoded and emitted without compression.
local function name_at(data, position)
    local parts, seen, length, next_position = {}, {}, 1, nil
    for _ = 1, 128 do
        if position < 13 or position > #data or seen[position] then return nil end
        seen[position] = true
        local size = data:byte(position)
        if size == 0 then
            parts[#parts+1] = "\0"
            return table.concat(parts), next_position or position + 1
        elseif size >= 192 then
            local low = data:byte(position+1)
            if not low then return nil end
            local target = (size - 192) * 256 + low + 1
            -- RFC1035 pointers refer to a prior name occurrence.
            if target >= position then return nil end
            next_position = next_position or position + 2
            position = target
        elseif size > 63 or size == 0 or position + size > #data then return nil
        else
            length = length + size + 1
            if length > 255 then return nil end
            parts[#parts+1] = data:sub(position, position + size)
            position = position + size + 1
        end
    end
    return nil
end

local function filter(data, now, health)
    if type(data) ~= "string" or #data < 12 or #data > 4096 then return nil end
    local flags = u16(data,3)
    -- QR, standard opcode, no truncation/rcode or authenticated DNSSEC data.
    if bitand(flags,0x8000) == 0 or bitand(flags,0x7a7f) ~= 0 or
       u16(data,5) ~= 1 or u16(data,9) ~= 0 or u16(data,11) > 1 then return nil end
    local count, additional_count = u16(data,7), u16(data,11)
    if count < 1 or count > 128 then return nil end
    local question, pos = name_at(data,13)
    if not question or pos + 3 > #data then return nil end
    local family, qclass = u16(data,pos), u16(data,pos+2)
    if (family ~= 1 and family ~= 28) or qclass ~= 1 then return nil end
    local question_wire = question .. data:sub(pos,pos+3)
    pos = pos + 4
    local records = {}
    for _ = 1, count do
        local name, after = name_at(data,pos)
        if not name or after + 9 > #data then return nil end
        local typ, class, length = u16(data,after), u16(data,after+2), u16(data,after+8)
        local first, last = after+10, after+9+length
        if class ~= 1 or last > #data then return nil end
        local value = data:sub(first,last)
        if typ == 1 then if length ~= 4 then return nil end
        elseif typ == 28 then if length ~= 16 then return nil end
        elseif typ == 5 then
            local cname, finish = name_at(data,first)
            if not cname or finish ~= last+1 then return nil end
            value = cname
        else return nil end
        records[#records+1] = {name=name, typ=typ, ttl=data:sub(after+4,after+7), value=value}
        pos = last+1
    end
    local additional = ""
    if additional_count == 1 then
        local name, after = name_at(data,pos)
        if name ~= "\0" or after+9 > #data or u16(data,after) ~= 41 then return nil end
        local size, ttl, length = u16(data,after+2), u32(data,after+4), u16(data,after+8)
        if size < 512 or ttl ~= 0 or after+9+length > #data then return nil end
        local first, finish = after+10, after+10+length
        local cursor = first
        while cursor < finish do
            if cursor+3 >= finish then return nil end
            local option_length = u16(data,cursor+2)
            cursor = cursor+4+option_length
            if cursor > finish then return nil end
        end
        additional = "\0" .. data:sub(after,finish-1)
        pos = finish
    end
    if pos ~= #data+1 then return nil end

    -- Only addresses reachable from the question through its CNAME chain count
    -- as a usable alternative.  Unrelated records cannot justify a rewrite.
    local reachable, cursor = {}, question:lower()
    for depth = 1, 17 do
        if reachable[cursor] then return nil end
        reachable[cursor] = true
        local target
        for _,rr in ipairs(records) do
            if rr.typ == 5 and rr.name:lower() == cursor then
                local value = rr.value:lower()
                if target and target ~= value then return nil end
                target = value
            end
        end
        if not target then break end
        if depth == 17 then return nil end
        cursor = target
    end
    local usable, remove = false, false
    for _,rr in ipairs(records) do
        if rr.typ == family and reachable[rr.name:lower()] then
            rr.remove = health.banned(rr.value,now)
            if rr.remove then remove = true
            elseif health.public_ip(rr.value) then usable = true end
        end
    end
    if not remove or not usable then return nil end
    local answers, kept = {}, 0
    for _,rr in ipairs(records) do
        if not rr.remove then
            kept = kept+1
            answers[#answers+1] = rr.name .. bu16(rr.typ) .. bu16(1) .. rr.ttl .. bu16(#rr.value) .. rr.value
        end
    end
    local result = data:sub(1,4) .. bu16(1) .. bu16(kept) .. bu16(0) .. bu16(additional_count) ..
                   question_wire .. table.concat(answers) .. additional
    if #result > 4096 then return nil end
    return result
end

local function dns_reply(ctx, desync)
    local health = nfqws_ip_health
    if not health then return VERDICT_PASS end
    local on, now = health.active()
    local dis = desync.dis
    -- Locally generated resolver replies may be marked outgoing by NFQWS2.
    -- Source port, QR and the externally scoped queue establish reply direction.
    if not on or not dis or not dis.udp or dis.udp.uh_sport ~= 53 or dis.frag_off ~= nil then return VERDICT_PASS end
    local data = filter(dis.payload, now, health)
    if not data then return VERDICT_PASS end
    local reply = deepcopy(dis)
    reply.payload = data
    if health.send(reply,desync.fwmark,desync.ifout) then return VERDICT_DROP end
    return VERDICT_PASS
end

function ip_health_dns(ctx, desync)
    local ok, verdict = pcall(dns_reply, ctx, desync)
    return ok and verdict or VERDICT_PASS
end
