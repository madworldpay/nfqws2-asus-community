#!/bin/sh
# NFQWS_DEVICE_PROFILES_EXPERIMENT: private OpenWrt integration, not a boot service.
NFQWS_LAB_RUN=${NFQWS_LAB_RUN:-/var/run/nfqws2-native/device-profiles/active}

nfqws_lab_php() {
    /usr/bin/php-cgi -n -d register_argc_argv=1 -d max_execution_time=0 \
        -d memory_limit=48M -q -f /usr/share/nfqws2-web/device-profiles-runtime.php -- "$@"
}
nfqws_lab_preflight() { nfqws_lab_php preflight "${NFQWS_WAN:-}"; }
nfqws_lab_definitions() {
    [ ! -f "$NFQWS_LAB_RUN/rules-definitions.nft" ] || cat "$NFQWS_LAB_RUN/rules-definitions.nft"
}
nfqws_lab_dispatch() {
    case "$1" in original|reply) ;; *) return 1;; esac
    [ ! -f "$NFQWS_LAB_RUN/rules-$1.nft" ] || cat "$NFQWS_LAB_RUN/rules-$1.nft"
}
nfqws_lab_ports() {
    local value=$1 protocol=$2
    case "$protocol" in tcp|udp) ;; *) return 1;; esac
    [ ! -f "$NFQWS_LAB_RUN/flow-$protocol" ] || value=$(cat "$NFQWS_LAB_RUN/flow-$protocol")
    nfqws_ports_valid "$value" || return 1
    printf '%s' "$value" | tr : -
}
nfqws_lab_instances() {
    local slot args
    set -f
    for slot in 0 1 2 3; do
        [ -f "$NFQWS_LAB_RUN/args.$slot" ] || continue
        args=$(cat "$NFQWS_LAB_RUN/args.$slot") || return 1
        [ -n "$args" ] && [ "${#args}" -le 131072 ] || return 1
        # Validated argv data, exactly as in the ordinary native service.
        set -- $args
        procd_open_instance "device_profile_$slot"
        procd_set_param command /usr/bin/nfqws2 "$@"
        procd_set_param stdout 0
        procd_set_param stderr 0
        procd_close_instance
    done
    if [ -f "$NFQWS_LAB_RUN/enabled" ]; then
        procd_open_instance device_profiles_watch
        procd_set_param command /bin/sh /usr/lib/nfqws2/device-profiles-native.sh reconcile-loop
        procd_set_param stdout 0
        procd_set_param stderr 0
        procd_close_instance
    fi
}
nfqws_lab_check() {
    local attempt=0
    while [ "$attempt" -lt 16 ]; do
        nfqws_lab_php check >/dev/null 2>&1 && return 0
        attempt=$((attempt+1)); sleep 0.5
    done
    return 1
}

nfqws_lab_main() {
    [ "$(id -u)" = 0 ] || return 1
    local action=$1 id=${2:-}
    case "$action" in
        work|guard|validate)
            [ "${#id}" = 32 ] || return 2
            case "$id" in *[!0-9a-f]*) return 2;; esac;;
        reconcile|reconcile-loop) [ "$#" = 1 ] || return 2;;
        *) return 2;;
    esac
    if [ "$action" = reconcile-loop ]; then
        while :; do
            sleep 15
            /bin/sh /usr/lib/nfqws2/device-profiles-native.sh reconcile >/dev/null 2>&1
        done
    fi
    . /usr/lib/nfqws2/update/service-lease.sh || return 1
    if ! nfqws_native_update_enter core restart; then
        case "$action" in work|guard) nfqws_lab_php queued-failure "$id";; esac
        return 1
    fi
    case "$action" in
        work) nfqws_lab_php work "$id";;
        guard) nfqws_lab_php guard "$id";;
        reconcile)
            exec 9>/var/run/nfqws2-native/control.lock || return 1
            /usr/bin/flock -x -n 9 || return 0
            nfqws_lab_php reconcile;;
        validate)
            . /usr/lib/nfqws2/platform.sh || return 1
            . /usr/lib/nfqws2/firewall.sh || return 1
            nfqws_load_config || return 1
            NFQWS_WAN=$(nfqws_uplinks) || NFQWS_WAN=''
            nfqws_lab_php pending "$id" "$NFQWS_WAN" || return 1
            NFQWS_LAB_RUN=/var/run/nfqws2-native/device-profiles/pending-$id
            export NFQWS_LAB_RUN
            [ -n "$NFQWS_WAN" ] || NFQWS_WAN=nfqws-wait
            nfqws_flow_probe || return 1
            umask 077
            (
                printf 'add table inet nfqws2_native\ndelete table inet nfqws2_native\n'
                nfqws_render_rules && nfqws_render_flow apply
            ) > "$NFQWS_LAB_RUN/rules.full.nft" || return 1
            /usr/sbin/nft -c -f "$NFQWS_LAB_RUN/rules.full.nft";;
    esac
}

# Sourcing provides hooks only. CLI actions use this exact installed root path.
if [ "$0" = /usr/lib/nfqws2/device-profiles-native.sh ] && [ "${NFQWS_LAB_EXECUTING:-0}" != 1 ]; then
    NFQWS_LAB_EXECUTING=1
    nfqws_lab_main "$@"
    exit $?
fi
