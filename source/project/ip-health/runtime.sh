#!/bin/sh
# Optional ASUS sidecar, sourced only while S51 holds its core/update leases.
ASUS_HEALTH_PRIVATE=$RUN_DIR/ip-health-private
ASUS_HEALTH_PUBLIC=/tmp/nfqws2-asus-ip-health
ASUS_HEALTH_LIB=/opt/lib/nfqws2-asus/ip-health

asus_ip_health_php() {
    if [ -f /opt/lib/php8/sockets.so ]; then
        /opt/bin/php-cgi -n -d extension=/opt/lib/php8/sockets.so -d register_argc_argv=1 -q -f "$ASUS_HEALTH_LIB/worker.php" -- "$@"
    else
        /opt/bin/php-cgi -n -d register_argc_argv=1 -q -f "$ASUS_HEALTH_LIB/worker.php" -- "$@"
    fi
}

asus_ip_health_queue_sockets() {
    [ -x /opt/lib/nfqws2-asus/ip-health-sockets/control.sh ] || return 0
    /opt/lib/nfqws2-asus/ip-health-sockets/control.sh queue 7>&- 8>&- 9>&-
}

asus_ip_health_directory() {
    local path=$1 mode=$2 hex=$3
    [ ! -L "$path" ] || return 1
    if [ ! -e "$path" ]; then mkdir -m "$mode" "$path" || return 1; fi
    [ -d "$path" ] && [ "$(stat -t "$path" | awk '{print $5 ":" $4}')" = "0:$hex" ]
}

asus_ip_health_rules() {
    local family=$1 clients addr chain direction original=ORIGINAL reply=REPLY observed
    case "$family" in 4) clients=$ASUS_CLIENTS4; observed=${ASUS_CT4:-normal};; 6) clients=$ASUS_CLIENTS6; observed=${ASUS_CT6:-normal};; *) return 1;; esac
    [ "$observed" != reverse ] || { original=REPLY; reply=ORIGINAL; }
    if [ "$ASUS_CLIENT_MODE" = include ] && [ -z "$clients" ]; then return 0; fi
    for chain in pre post local; do
        printf '%s\n' "-A nfqh_$chain -m mark --mark 0x40000000/0x40000000 -j RETURN"
        if [ "$ASUS_CLIENT_MODE" = exclude ]; then
            for addr in $clients; do
                if [ "$chain" = local ]; then direction="-d $addr"; else direction="-m conntrack --ctorigsrc $addr"; fi
                printf '%s\n' "-A nfqh_$chain $direction -j RETURN"
            done
        fi
    done
    # A queued NF_ACCEPT skips the rest of this table's hook, not just the
    # queue rule. Keep TLS observation in FORWARD/INPUT/OUTPUT: the core owns
    # PREROUTING/POSTROUTING and must still see the same packets afterwards.
    printf '%s\n' '-A nfqh_forward -j nfqh_pre'
    printf '%s\n' '-A nfqh_forward -j nfqh_post'
    # Only transit DNS replies from this generation's WAN are eligible.
    printf '%s\n' "-A nfqh_forward -i $ASUS_WAN -j nfqh_local"
    if [ "$ASUS_CLIENT_MODE" = include ]; then
        for addr in $clients; do
            printf '%s\n' "-A nfqh_pre -i $ASUS_WAN -m conntrack --ctdir $reply --ctorigsrc $addr -j nfqh_in"
            printf '%s\n' "-A nfqh_post -o $ASUS_WAN -m conntrack --ctdir $original --ctorigsrc $addr -j nfqh_out"
            [ -z "$ASUS_HEALTH_LAN" ] || printf '%s\n' "-A nfqh_local -o $ASUS_HEALTH_LAN -p udp --sport 53 -d $addr -j NFQUEUE --queue-num $ASUS_HEALTH_QUEUE --queue-bypass"
        done
    else
        printf '%s\n' "-A nfqh_pre -i $ASUS_WAN -m conntrack --ctdir $reply -j nfqh_in"
        printf '%s\n' "-A nfqh_post -o $ASUS_WAN -m conntrack --ctdir $original -j nfqh_out"
        [ -z "$ASUS_HEALTH_LAN" ] || printf '%s\n' "-A nfqh_local -o $ASUS_HEALTH_LAN -p udp --sport 53 -j NFQUEUE --queue-num $ASUS_HEALTH_QUEUE --queue-bypass"
    fi
    printf '%s\n' "-A nfqh_in -p tcp --sport 443 -j NFQUEUE --queue-num $ASUS_HEALTH_QUEUE --queue-bypass"
    printf '%s\n' "-A nfqh_out -p tcp --dport 443 -j NFQUEUE --queue-num $ASUS_HEALTH_QUEUE --queue-bypass"
    printf '%s\n' "-A nfqh_out -p udp --dport 443 -j NFQUEUE --queue-num $ASUS_HEALTH_QUEUE --queue-bypass"
}

asus_ip_health_firewall_family() {
    local family=$1 cmd=iptables chain line parent policy
    [ "$family" != 6 ] || cmd=ip6tables
    # A queue's ACCEPT would bypass a non-ACCEPT mangle base policy too.
    # Such custom tables are outside this adapter's supported topology.
    for parent in FORWARD INPUT OUTPUT; do
        policy=$("$cmd" -w -t mangle -S "$parent" | head -n 1) || return 1
        [ "$policy" = "-P $parent ACCEPT" ] || return 1
    done
    [ ! -e "$ASUS_HEALTH_PRIVATE/chains$family" ] && [ ! -L "$ASUS_HEALTH_PRIVATE/chains$family" ] || return 1
    (umask 077; set -C; : > "$ASUS_HEALTH_PRIVATE/chains$family") || return 1
    # Atomic -N refuses foreign chains. Record only successful creations; never
    # flush a pre-existing name or claim it after a failed create.
    for chain in nfqh_pre nfqh_post nfqh_forward nfqh_local nfqh_in nfqh_out; do
        "$cmd" -w -t mangle -N "$chain" || return 1
        printf '%s\n' "$chain" >> "$ASUS_HEALTH_PRIVATE/chains$family"
    done
    asus_ip_health_rules "$family" > "$ASUS_HEALTH_PRIVATE/rules$family" || return 1
    while IFS= read -r line; do set -- $line; "$cmd" -w -t mangle "$@" || return 1; done < "$ASUS_HEALTH_PRIVATE/rules$family"
    # Append after foreign MSS/mark rules so our ACCEPT does not skip them.
    "$cmd" -w -t mangle -A FORWARD -j nfqh_forward || return 1
    "$cmd" -w -t mangle -A INPUT -j nfqh_pre || return 1
    "$cmd" -w -t mangle -A OUTPUT -j nfqh_local || return 1
    # OUTPUT's route may be recomputed after policy marks change. Observe
    # only unmarked local TLS; probes/VPN-marked traffic stay fail-open.
    "$cmd" -w -t mangle -A OUTPUT -m mark --mark 0x0/0xffffffff -j nfqh_post
}

asus_ip_health_firewall_stop() {
    local family cmd marker chain chains parent
    for family in 4 6; do
        marker=$ASUS_HEALTH_PRIVATE/chains$family
        [ -f "$marker" ] && [ ! -L "$marker" ] || continue
        [ "$(LC_ALL=C ls -ln "$marker" | awk '{print $1 ":" $2 ":" $3}')" = '-rw-------:1:0' ] || continue
        cmd=iptables; [ "$family" != 6 ] || cmd=ip6tables
        # Remove only jumps to successfully created, recorded chains.
        for parent in PREROUTING POSTROUTING FORWARD INPUT OUTPUT; do
            case "$parent" in
                PREROUTING) chains=nfqh_pre;; POSTROUTING) chains=nfqh_post;;
                # The second name cleans the prior unpublished test adapter.
                # Both require recorded successful creation before any delete.
                FORWARD) chains='nfqh_forward nfqh_local';;
                INPUT) chains=nfqh_pre;; OUTPUT) chains=nfqh_local;;
            esac
            for chain in $chains; do
                grep -Fx "$chain" "$marker" >/dev/null || continue
                while "$cmd" -w -t mangle -D "$parent" -j "$chain" >/dev/null 2>&1; do :; done
            done
        done
        if grep -Fx nfqh_post "$marker" >/dev/null; then
            while "$cmd" -w -t mangle -D OUTPUT -m mark --mark 0x0/0xffffffff -j nfqh_post >/dev/null 2>&1; do :; done
        fi
        # Internal references must be flushed before deleting owned chains.
        for chain in nfqh_pre nfqh_post nfqh_forward nfqh_local nfqh_in nfqh_out; do
            grep -Fx "$chain" "$marker" >/dev/null || continue
            "$cmd" -w -t mangle -F "$chain" >/dev/null 2>&1 || :
        done
        for chain in nfqh_pre nfqh_post nfqh_forward nfqh_local nfqh_in nfqh_out; do
            grep -Fx "$chain" "$marker" >/dev/null || continue
            "$cmd" -w -t mangle -X "$chain" >/dev/null 2>&1 || :
        done
        rm -f "$marker" "$ASUS_HEALTH_PRIVATE/rules$family"
    done
}

asus_ip_health_stop() {
    local pids pid attempts=0 alive
    [ -d "$ASUS_HEALTH_PRIVATE" ] && [ ! -L "$ASUS_HEALTH_PRIVATE" ] || return 0
    asus_ip_health_php inactive core_stopped >/dev/null 2>&1 || :
    asus_ip_health_firewall_stop
    pids=$(asus_ip_health_php owned-pids 2>/dev/null) || return 1
    for pid in $pids; do case "$pid" in ''|*[!0-9]*) return 1;; esac; [ "$pid" -gt 1 ] || return 1; kill -TERM "$pid" 2>/dev/null || :; done
    while [ "$attempts" -lt 10 ]; do
        alive=0; for pid in $pids; do kill -0 "$pid" 2>/dev/null && alive=1; done
        [ "$alive" = 1 ] || return 0
        sleep 1; attempts=$((attempts + 1))
    done
    return 1
}

asus_ip_health_start() {
    local uid gid pid observer generation q addresses
    [ -f "$ASUS_HEALTH_LIB/worker.php" ] && [ -f "$ASUS_HEALTH_LIB/monitor.lua" ] && [ -f "$ASUS_HEALTH_LIB/dns.lua" ] || return 0
    asus_running || return 0
    asus_ip_health_directory "$ASUS_HEALTH_PRIVATE" 700 41c0 || return 1
    asus_ip_health_directory "$ASUS_HEALTH_PUBLIC" 755 41ed || return 1
    asus_ip_health_php enabled >/dev/null 2>&1 || { asus_ip_health_stop || :; return 0; }
    set -- $ASUS_WAN
    if [ "$#" != 1 ] || { [ "$(nvram get wan0_state_t 2>/dev/null)" = 2 ] && [ "$(nvram get wan1_state_t 2>/dev/null)" = 2 ]; }; then
        asus_ip_health_stop || :
        asus_ip_health_php inactive multiwan_unsupported >/dev/null 2>&1
        return 0
    fi
    [ "$NFQUEUE_NUM" -lt 65535 ] || return 1
    ASUS_HEALTH_QUEUE=$((NFQUEUE_NUM + 1));q=$ASUS_HEALTH_QUEUE
    ASUS_HEALTH_LAN=$(nvram get lan_ifname 2>/dev/null)
    asus_interface_valid "$ASUS_HEALTH_LAN" && [ "$ASUS_HEALTH_LAN" != "$ASUS_WAN" ] || { asus_ip_health_stop || :; return 1; }
    addresses=$(ip -o addr show dev "$ASUS_WAN") || return 1
    generation=$({ cat /proc/sys/kernel/random/boot_id; printf '%s\n' "$ASUS_WAN" "$addresses"; sha256sum "$RUN_DIR/runtime.conf"; } | sha256sum)
    generation=${generation%% *};pid=$(cat "$PIDFILE")
    asus_ip_health_php healthy "$generation" "$pid" >/dev/null 2>&1 && return 0
    asus_ip_health_stop || return 1
    if awk -v q="$q" '$1==q {found=1} END{exit !found}' /proc/net/netfilter/nfnetlink_queue; then asus_ip_health_php inactive queue_in_use >/dev/null 2>&1; return 0; fi
    if ! asus_ip_health_php available "$ASUS_WAN" >/dev/null 2>&1; then
        # A loaded module cannot fix unsupported SO_MARK/BINDTODEVICE. Do not
        # create a ready -> reconcile -> acquire loop on those kernels.
        asus_ip_health_php module >/dev/null 2>&1 || asus_ip_health_queue_sockets >/dev/null 2>&1 || :
        return 0
    fi
    uid=$(id -u "$USER") && gid=$(id -g "$USER") || return 1
    if [ ! -e "$ASUS_HEALTH_PUBLIC/events" ] && [ ! -L "$ASUS_HEALTH_PUBLIC/events" ]; then
        mkdir -m 700 "$ASUS_HEALTH_PUBLIC/events" || return 1
        # Transfer the directory last; never chown a path in an existing
        # engine-writable directory, where it could have been replaced.
        (umask 077; set -C; : > "$ASUS_HEALTH_PUBLIC/events/events.log") || return 1
        chown "$uid:$gid" "$ASUS_HEALTH_PUBLIC/events/events.log" || return 1
        chown "$uid:$gid" "$ASUS_HEALTH_PUBLIC/events" || return 1
    fi
    rm -f "$ASUS_HEALTH_PRIVATE/observer.pid"
    # Observation must never hold/replay segmented TLS/QUIC with the desync
    # bypass mark: that would hide the replay from the real core queue.
    "$NFQWS_BIN" --daemon --reasm-disable --pidfile="$ASUS_HEALTH_PRIVATE/observer.pid" --user="$USER" --qnum="$q" --fwmark=0x40000000 \
        --writable="$ASUS_HEALTH_PUBLIC/events" --lua-init=@/opt/etc/nfqws2/lua/zapret-lib.lua \
        --lua-init='IPHEALTH_MANIFEST="/tmp/nfqws2-asus-ip-health/active.txt"' \
        --lua-init=@/opt/lib/nfqws2-asus/ip-health/dns.lua --lua-init=@/opt/lib/nfqws2-asus/ip-health/monitor.lua \
        --filter-tcp=443 --payload=all --in-range=a --out-range=a --lua-desync=ip_health_tcp --new \
        --filter-udp=443 --payload=all --in-range=a --out-range=a --lua-desync=ip_health_udp --new \
        --filter-udp=1-65535 --payload=all --in-range=a --out-range=a --lua-desync=ip_health_dns 7>&- 8>&- 9>&- || return 1
    observer='';addresses=0
    while [ "$addresses" -lt 3 ]; do
        observer=$(cat "$ASUS_HEALTH_PRIVATE/observer.pid" 2>/dev/null)
        if asus_ip_health_php prepare "$pid" "$observer" "$q" "$ASUS_WAN" "$IPV6_ENABLED" "$generation" >/dev/null 2>&1; then break; fi
        sleep 1; addresses=$((addresses + 1))
    done
    # Register and prove queue ownership before attaching any packet rules.
    if [ "$addresses" = 3 ]; then asus_ip_health_stop || :; return 1; fi
    if ! asus_ip_health_firewall_family 4 || { [ "$IPV6_ENABLED" = 1 ] && ! asus_ip_health_firewall_family 6; }; then
        asus_ip_health_stop || :; return 1
    fi
    (
        trap '' HUP
        # Ash saves function redirections in extra FDs until it returns. Drop
        # inherited leases and caller stdio in this child before the function.
        exec </dev/null >"$ASUS_HEALTH_PRIVATE/worker.log" 2>&1 7>&- 8>&- 9>&-
        asus_ip_health_php loop &
    )
}
