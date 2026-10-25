#!/bin/sh
# Root-only fixed operations used by procd and the native web platform adapter.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
NFQWS_LIB=/usr/lib/nfqws2
NFQWS_RUN=/var/run/nfqws2-native
NFQWS_BIN=/usr/bin/nfqws2
. "$NFQWS_LIB/platform.sh" || exit 1
. "$NFQWS_LIB/firewall.sh" || exit 1

nfqws_preflight() (
    set -f
    local args file pid facts
    nfqws_load_config || exit 1
    [ -x "$NFQWS_BIN" ] && [ -r "$NFQWS_LIB/args.sh" ] || { echo engine_missing >&2; exit 1; }
    grep -Eq "^${USER}:[^:]*:[0-9]+:" /etc/passwd || { echo engine_user_missing >&2; exit 1; }
    NFQWS_WAN=$(nfqws_uplinks) || NFQWS_WAN=''
    # Validate capture/client settings even while the uplink is down.
    ( NFQWS_WAN=${NFQWS_WAN:-nfqws-wait}; nfqws_validate_rules ) || { echo invalid_firewall_config >&2; exit 1; }
    nfqws_flow_probe || exit 1
    local owned=0
    nfqws_firewall_owned || owned=$?
    [ "$owned" != 1 ] || { echo firewall_owner_conflict >&2; exit 1; }
    facts=$(nfqws_queue_facts "$NFQUEUE_NUM")
    case "$facts" in bound\ *)
        pid=$(nfqws_process_pid) || { echo queue_in_use >&2; exit 1; }
        [ "${facts##* }" = "$pid" ] || { echo queue_in_use >&2; exit 1; };;
    esac
    . "$NFQWS_LIB/args.sh" || exit 1
    ISP_INTERFACE=$NFQWS_WAN
    args=$(_startup_args) || exit 1
    [ "${#args}" -le 131072 ] || { echo engine_arguments_limit >&2; exit 1; }
    set -- $args
    # The engine checks options and file access before service/firewall changes.
    "$NFQWS_BIN" --dry-run "$@" > "$NFQWS_RUN/preflight.log" 2>&1 || { tail -n 8 "$NFQWS_RUN/preflight.log" >&2; exit 1; }
    file=$(mktemp "$NFQWS_RUN/launch.XXXXXX") || exit 1
    # Quote only, never interpolate a shell program from strategy text.
    printf "NFQWS_LAUNCH_ARGS='" > "$file"
    printf '%s' "$args" | sed "s/'/'\\\\''/g" >> "$file"
    printf "'\n" >> "$file"
    mv "$file" "$NFQWS_RUN/launch.env"
)

nfqws_capture() {
    nfqws_load_config || return 1
    # Kernel packages come from the running firmware's feed.
    modprobe nft_queue 2>/dev/null || return 1
    modprobe nfnetlink_queue 2>/dev/null || return 1
    [ -f /proc/sys/net/netfilter/nf_conntrack_acct ] || { echo conntrack_accounting_unavailable >&2; return 1; }
    sysctl -q -w net.netfilter.nf_conntrack_acct=1 || return 1
    NFQWS_WAN=$(nfqws_uplinks) || NFQWS_WAN=''
    if [ -z "$NFQWS_WAN" ]; then
        nfqws_firewall_stop || return 1
        printf 'waiting_uplink\n' > "$NFQWS_RUN/capture.state"
    else
        nfqws_firewall_apply || return 1
        printf 'ready\n' > "$NFQWS_RUN/capture.state"
    fi
}

nfqws_check() {
    local pid queue facts
    pid=$(nfqws_process_pid) || return 1
    queue=$(sed -n "s/^NFQUEUE_NUM='\([0-9]*\)'$/\1/p" "$NFQWS_RUN/config.env" 2>/dev/null)
    facts=$(nfqws_queue_facts "$queue")
    case "$facts" in bound\ *) [ "${facts##* }" = "$pid" ];; *) return 1;; esac
}

nfqws_diagnostics() {
    local pid=null queue=null facts state seq port running=false uplinks='' separator='' iface capture=unknown acceleration=unknown
    pid=$(nfqws_process_pid) && running=true || pid=null
    queue=$(sed -n "s/^NFQUEUE_NUM='\([0-9]*\)'$/\1/p" "$NFQWS_RUN/config.env" 2>/dev/null)
    case "$queue" in ''|*[!0-9]*) queue=null;; esac
    facts=$(nfqws_queue_facts "$queue"); set -- $facts; state=$1; seq=$2; port=$3
    if [ -f "$NFQWS_RUN/capture.state" ] && [ ! -L "$NFQWS_RUN/capture.state" ]; then
        capture=$(cat "$NFQWS_RUN/capture.state")
        case "$capture" in ready|waiting_uplink) ;; *) capture=unknown;; esac
    fi
    for iface in $(ISP_INTERFACE=''; nfqws_uplinks); do
        uplinks="$uplinks$separator\"$iface\""; separator=,
    done
    if nfqws_flow_probe >/dev/null 2>&1; then acceleration=$NFQWS_FLOW_STATE; fi
    printf '{"platform":"openwrt","process_running":%s,"pid":%s,"nfqueue":{"queue_number":%s,"state":"%s","sequence":%s,"port_id":%s},"capture":"%s","uplinks":[%s],"acceleration":"%s"}\n' "$running" "$pid" "$queue" "$state" "$seq" "$port" "$capture" "$uplinks" "$acceleration"
}

[ "$(id -u)" = 0 ] || { echo root_required >&2; exit 1; }
case "$1" in
    diagnostics) nfqws_diagnostics; exit $?;;
    status) if nfqws_check; then echo 'nfqws2 is running'; exit 0; else echo 'nfqws2 is stopped or queue is unavailable'; exit 1; fi;;
    check) nfqws_check; exit $?;;
    network-event) nfqws_process_pid >/dev/null || exit 0; exec /etc/init.d/nfqws2-native reload;;
esac
nfqws_runtime_directory || { echo unsafe_runtime_directory >&2; exit 1; }
exec 9>"$NFQWS_RUN/control.lock"
flock -x 9 || exit 1
case "$1" in
    preflight) nfqws_preflight;;
    firewall) nfqws_capture;;
    remove-firewall) nfqws_firewall_stop && rm -f "$NFQWS_RUN/capture.state";;
    check-started)
        tries=0
        while [ "$tries" -lt 30 ]; do nfqws_check && exit 0; tries=$((tries+1)); sleep 0.1; done
        echo queue_not_bound >&2; exit 1;;
    *) echo invalid_operation >&2; exit 1;;
esac
