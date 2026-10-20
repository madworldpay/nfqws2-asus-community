-- Local wrapper: never inject a timestamp fake if timestamps were not negotiated.
function guarded_ts_fake(ctx, desync)
    if not desync.dis.tcp or not find_tcp_option(desync.dis.tcp.options, TCP_KIND_TS) then
        return
    end
    return fake(ctx, desync)
end
