#!/bin/sh
# Optional sidecar in the existing native procd service; never changes core args.
NFQWS_HEALTH_LIB=/usr/lib/nfqws2/ip-health
NFQWS_HEALTH_PUBLIC=/tmp/nfqws2-native-ip-health
NFQWS_HEALTH_PRIVATE=$(readlink -f "${NFQWS_RUN:-/var/run/nfqws2-native}")/ip-health-private

nfqws_health_php() {
    if [ -f /usr/lib/php8/sockets.so ]; then
        /usr/bin/php-cgi -n -d extension=/usr/lib/php8/sockets.so -d register_argc_argv=1 -q -f "$NFQWS_HEALTH_LIB/worker.php" -- "$@"
    else
        /usr/bin/php-cgi -n -d register_argc_argv=1 -q -f "$NFQWS_HEALTH_LIB/worker.php" -- "$@"
    fi
}

nfqws_health_directory() {
    local path=$1 mode=$2 expected=$3
    [ ! -L "$path" ] || return 1
    if [ ! -e "$path" ]; then mkdir -m "$mode" "$path" || return 1; fi
    [ -d "$path" ] && [ "$(LC_ALL=C ls -dn "$path" | awk '{print $1 ":" $3}')" = "$expected:0" ]
}

nfqws_health_rules() (
    set -f
    nfqws_validate_rules || exit 1
    set -- $NFQWS_WAN
    [ "$#" = 1 ] && [ "$NFQUEUE_NUM" -lt 65535 ] && [ "$NFQWS_HEALTH_QUEUE" = "$((NFQUEUE_NUM + 1))" ] || exit 1
    local chain direction
    printf 'create table inet nfqws2_health {\n comment "NFQWS2 IP Health v1"\n'
    nfqws_client_set clients4 ipv4_addr "$ASUS_CLIENTS4"
    nfqws_client_set clients6 ipv6_addr "$ASUS_CLIENTS6"
    for chain in prerouting postrouting forward output; do
        printf ' chain %s {\n  type filter hook %s priority mangle + 1; policy accept;\n' "$chain" "$chain"
        printf '  meta mark & 0x40000000 != 0 return\n'
        [ "$IPV6_ENABLED" = 1 ] || printf '  meta nfproto ipv6 return\n'
        case "$chain" in
            prerouting) printf '  iifname "%s" ct direction reply jump reply\n' "$NFQWS_WAN";;
            postrouting) printf '  oifname "%s" ct direction original jump original\n' "$NFQWS_WAN";;
            forward|output)
                if [ "$chain" = forward ]; then printf '  iifname != "%s" return\n  ct direction != reply return\n' "$NFQWS_WAN"; fi
                printf '  oifname { "%s", "lo" } return\n' "$NFQWS_WAN"
                case "$ASUS_CLIENT_MODE" in
                    include) printf '  meta nfproto ipv4 ip daddr != @clients4 return\n  meta nfproto ipv6 ip6 daddr != @clients6 return\n';;
                    exclude) printf '  meta nfproto ipv4 ip daddr @clients4 return\n  meta nfproto ipv6 ip6 daddr @clients6 return\n';;
                esac
                printf '  udp sport 53 counter queue num %s bypass\n' "$NFQWS_HEALTH_QUEUE";;
        esac
        printf ' }\n'
    done
    for direction in original reply; do
        printf ' chain %s {\n' "$direction"
        nfqws_client_rules
        if [ "$direction" = original ]; then
            printf '  tcp dport 443 counter queue num %s bypass\n  udp dport 443 counter queue num %s bypass\n' "$NFQWS_HEALTH_QUEUE" "$NFQWS_HEALTH_QUEUE"
        else
            printf '  tcp sport 443 counter queue num %s bypass\n' "$NFQWS_HEALTH_QUEUE"
        fi
        printf ' }\n'
    done
    printf '}\n'
)

nfqws_health_firewall_owned() {
    local existing
    existing=$(nft list table inet nfqws2_health 2>/dev/null) || return 2
    # nft uses a tab in its canonical listing, unlike our input indentation.
    printf '%s\n' "$existing" | grep -Eq '^[[:space:]]+comment "NFQWS2 IP Health v1"$'
}

nfqws_health_firewall_apply() {
    local owned=0 file
    nfqws_health_firewall_owned || owned=$?
    # Startup first tears down its proven old sidecar. Any existing table here
    # is a collision; create (not add+delete) also closes a concurrent collision.
    [ "$owned" = 2 ] || return 1
    file=$(mktemp "$NFQWS_HEALTH_PRIVATE/rules.XXXXXX") || return 1
    nfqws_health_rules > "$file" || { rm -f "$file"; return 1; }
    nft -c -f "$file" && nft -f "$file"
    local rc=$?; rm -f "$file"; return "$rc"
}

nfqws_health_firewall_stop() {
    local owned=0
    nfqws_health_firewall_owned || owned=$?
    case "$owned" in 2) return 0;; 1) return 1;; esac
    nft delete table inet nfqws2_health && return 0
    # The supervisor can reap its observer concurrently with an explicit stop.
    owned=0; nfqws_health_firewall_owned || owned=$?
    [ "$owned" = 2 ]
}

nfqws_health_stop() {
    local pids pid attempt=0 alive
    [ -d "$NFQWS_HEALTH_PRIVATE" ] && [ ! -L "$NFQWS_HEALTH_PRIVATE" ] || return 0
    nfqws_health_php inactive core_stopped >/dev/null 2>&1 || :
    nfqws_health_firewall_stop || return 1
    pids=$(nfqws_health_php owned-pids 2>/dev/null) || return 1
    for pid in $pids; do case "$pid" in ''|*[!0-9]*) return 1;; esac; [ "$pid" -gt 1 ] || return 1; kill -TERM "$pid" 2>/dev/null || :; done
    while [ "$attempt" -lt 10 ]; do
        alive=0; for pid in $pids; do kill -0 "$pid" 2>/dev/null && alive=1; done
        [ "$alive" = 1 ] || return 0
        sleep 1; attempt=$((attempt + 1))
    done
    return 1
}

nfqws_health_start() {
    local pid all selected addresses generation observer attempt=0 uid gid queue
    pid=$(nfqws_process_pid) || return 0
    nfqws_health_directory "$NFQWS_HEALTH_PRIVATE" 700 drwx------ || return 1
    nfqws_health_directory "$NFQWS_HEALTH_PUBLIC" 755 drwxr-xr-x || return 1
    nfqws_health_php enabled >/dev/null 2>&1 || { nfqws_health_stop || :; return 0; }
    all=$(ISP_INTERFACE=''; nfqws_uplinks) || all=''
    selected=$(nfqws_uplinks) || selected=''
    set -- $all; [ "$#" = 1 ] || { nfqws_health_stop || :; nfqws_health_php inactive multiwan_unsupported >/dev/null 2>&1; return 0; }
    set -- $selected; [ "$#" = 1 ] && [ "$selected" = "$all" ] || { nfqws_health_stop || :; nfqws_health_php inactive multiwan_unsupported >/dev/null 2>&1; return 0; }
    NFQWS_WAN=$selected
    [ "$NFQUEUE_NUM" -lt 65535 ] || return 0
    NFQWS_HEALTH_QUEUE=$((NFQUEUE_NUM + 1)); queue=$NFQWS_HEALTH_QUEUE
    nfqws_health_stop || return 1
    case "$(nfqws_queue_facts "$queue")" in 'unbound null null') ;; *) nfqws_health_php inactive queue_in_use >/dev/null 2>&1; return 0;; esac
    nfqws_health_php available "$NFQWS_WAN" >/dev/null 2>&1 || return 0
    addresses=$(ip -o addr show dev "$NFQWS_WAN") || return 1
    [ "${#addresses}" -le 65536 ] || return 1
    generation=$({ cat /proc/sys/kernel/random/boot_id; printf '%s\n' "$NFQWS_WAN" "$addresses"; sha256sum "$NFQWS_RUN/config.env"; } | sha256sum)
    generation=${generation%% *}
    uid=$(id -u "$USER") && gid=$(id -g "$USER") || return 1
    if [ ! -e "$NFQWS_HEALTH_PUBLIC/events" ] && [ ! -L "$NFQWS_HEALTH_PUBLIC/events" ]; then
        mkdir -m 700 "$NFQWS_HEALTH_PUBLIC/events" || return 1
        (umask 077; set -C; : > "$NFQWS_HEALTH_PUBLIC/events/events.log") || return 1
        chown "$uid:$gid" "$NFQWS_HEALTH_PUBLIC/events/events.log" || return 1
        chown "$uid:$gid" "$NFQWS_HEALTH_PUBLIC/events" || return 1
    fi
    rm -f "$NFQWS_HEALTH_PRIVATE/observer.pid"
    "$NFQWS_BIN" --daemon --pidfile="$NFQWS_HEALTH_PRIVATE/observer.pid" --user="$USER" --qnum="$queue" --fwmark=0x40000000 \
        --writable="$NFQWS_HEALTH_PUBLIC/events" --lua-init=@/etc/nfqws2/lua/zapret-lib.lua \
        --lua-init='IPHEALTH_MANIFEST="/tmp/nfqws2-native-ip-health/active.txt"' \
        --lua-init=@/usr/lib/nfqws2/ip-health/dns.lua --lua-init=@/usr/lib/nfqws2/ip-health/monitor.lua \
        --filter-tcp=443 --payload=all --in-range=a --out-range=a --lua-desync=ip_health_tcp --new \
        --filter-udp=443 --payload=all --in-range=a --out-range=a --lua-desync=ip_health_udp --new \
        --filter-udp=1-65535 --payload=all --in-range=a --out-range=a --lua-desync=ip_health_dns 7>&- 8>&- 9>&- || return 1
    while [ "$attempt" -lt 3 ]; do
        observer=$(cat "$NFQWS_HEALTH_PRIVATE/observer.pid" 2>/dev/null)
        if nfqws_health_php prepare "$pid" "$observer" "$queue" "$NFQWS_WAN" "$IPV6_ENABLED" "$generation" >/dev/null 2>&1; then break; fi
        sleep 1; attempt=$((attempt + 1))
    done
    if [ "$attempt" = 3 ] || ! nfqws_health_firewall_apply; then nfqws_health_stop || :; return 1; fi
    # This becomes the existing procd instance's foreground process. Its own
    # ticks take short update leases; no inherited lease blocks future updates.
    exec 7>&- 8>&- 9>&-
    nfqws_health_php loop
    local rc=$?
    nfqws_health_stop || :
    return "$rc"
}
