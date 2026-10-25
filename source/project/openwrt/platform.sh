#!/bin/sh
# Native OpenWrt facts. No model names or physical port assumptions.

nfqws_interface_valid() {
    [ -n "$1" ] && [ "${#1}" -le 15 ] || return 1
    case "$1" in *[!a-zA-Z0-9_.:-]*) return 1;; esac
    ip link show dev "$1" >/dev/null 2>&1
}

nfqws_uplinks() (
    set -f
    local iface dump found='' count=0 entry up proto routes target
    if [ -n "$ISP_INTERFACE" ]; then
        [ "${#ISP_INTERFACE}" -le 1024 ] || exit 1
        for iface in $ISP_INTERFACE; do
            count=$((count+1)); [ "$count" -le 64 ] && nfqws_interface_valid "$iface" || exit 1
            found="$found$iface
"
        done
    else
        dump=$(ubus call network.interface dump 2>/dev/null) || exit 1
        [ "${#dump}" -le 1048576 ] || exit 1
        found=$(printf '%s\n' "$dump" | jsonfilter -e '@.interface[*]' | while IFS= read -r entry; do
            [ "${#entry}" -le 65536 ] || continue
            up=$(jsonfilter -s "$entry" -e '@.up' 2>/dev/null)
            [ "$up" = true ] || continue
            proto=$(jsonfilter -s "$entry" -e '@.proto' 2>/dev/null)
            case "$proto" in wireguard|openvpn|ipsec|xfrm|gre|gretap|vxlan) continue;; esac
            iface=$(jsonfilter -s "$entry" -e '@.l3_device' 2>/dev/null)
            nfqws_interface_valid "$iface" || continue
            routes=$(jsonfilter -s "$entry" -e '@.route[@.mask=0].target' 2>/dev/null)
            for target in $routes; do
                case "$target" in 0.0.0.0|::|0:0:0:0:0:0:0:0) printf '%s\n' "$iface"; break;; esac
            done
        done)
    fi
    [ -n "$found" ] || exit 1
    printf '%s' "$found" | awk 'NF&&!seen[$0]++'
)

nfqws_runtime_directory() {
    local run=${NFQWS_RUN:-/var/run/nfqws2-native}
    [ ! -L "$run" ] || return 1
    if [ ! -e "$run" ]; then (umask 077; mkdir -p "$run") || return 1; fi
    # BusyBox stat is optional on OpenWrt; numeric ls is in the base system.
    [ -d "$run" ] && [ "$(LC_ALL=C ls -dn "$run" | awk '{print $1,$3}')" = 'drwx------ 0' ]
}

nfqws_load_config() {
    local file lib=${NFQWS_LIB:-/usr/lib/nfqws2} run=${NFQWS_RUN:-/var/run/nfqws2-native}
    nfqws_runtime_directory || return 1
    file=$(mktemp "$run/config.XXXXXX") || return 1
    if ! /usr/bin/php-cgi -n -d register_argc_argv=1 -q -f "$lib/config-cli.php" /etc/nfqws2/nfqws2.conf > "$file"; then
        rm -f "$file"; return 1
    fi
    # The parser emits only the fixed whitelist as shell-quoted literal data.
    . "$file" || { rm -f "$file"; return 1; }
    mv "$file" "$run/config.env"
}

nfqws_process_pid() {
    local pid info binary=${NFQWS_BIN:-/usr/bin/nfqws2}
    info=$(ubus call service list '{"name":"nfqws2-native"}' 2>/dev/null) || return 1
    pid=$(printf '%s\n' "$info" | jsonfilter -e '@["nfqws2-native"].instances.main.pid' 2>/dev/null)
    case "$pid" in ''|*[!0-9]*) return 1;; esac
    [ "$pid" -gt 1 ] && [ -d "/proc/$pid" ] || return 1
    [ "$(readlink -f "/proc/$pid/exe")" = "$(readlink -f "$binary")" ] || return 1
    printf '%s\n' "$pid"
}

nfqws_queue_facts() {
    local queue=$1 file=${2:-/proc/net/netfilter/nfnetlink_queue}
    case "$queue" in ''|*[!0-9]*) printf 'unknown null null\n'; return;; esac
    [ "$queue" -le 65535 ] && [ -r "$file" ] && [ -f "$file" ] || { printf 'unknown null null\n'; return; }
    awk -v q="$queue" '
    $1+0==q&&$1~/^[0-9]+$/ {
        found++;if(NF!=9)bad=1;
        for(i=1;i<=NF;i++)if($i!~/^[0-9]+$/)bad=1;
        if($8+0>4294967295)bad=1;seq=$8;port=$2;
    }
    END {if(bad||found>1)print "unknown null null";
      else if(found)printf "bound %s %s\n",seq,port;
      else print "unbound null null";}' "$file"
}

nfqws_wait_started() {
    local attempts=0
    while [ "$attempts" -lt 10 ]; do
        nfqws_check && return 0
        attempts=$((attempts+1))
        sleep 1 || return 1
    done
    printf 'queue_not_bound\n' >&2
    return 1
}
