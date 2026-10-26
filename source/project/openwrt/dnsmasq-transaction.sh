#!/bin/sh
# Child-local hook at the native procd commit boundary. Never replace a system
# script/binary or reconstruct a service from its incomplete status projection.
set -f
umask 077
nfqws_dns_id=${1:-};nfqws_dns_mode=${2:-};nfqws_dns_instance=${3:-}
[ "$#" = 3 ] || exit 2
case "$nfqws_dns_id" in ''|*[!a-f0-9]*) exit 2;; esac
[ "${#nfqws_dns_id}" = 32 ] || exit 2
case "$nfqws_dns_mode" in forward|restore) :;; *) exit 2;; esac
case "$nfqws_dns_instance" in ''|*[!A-Za-z0-9_]*) exit 2;; esac
[ "${#nfqws_dns_instance}" -le 64 ] || exit 2
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
nfqws_dns_ctl() {
    local nfqws_dns_op=$1
    shift
    /usr/bin/php-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/smartdns/native-control.php -- "$nfqws_dns_op" "$nfqws_dns_id" "$nfqws_dns_mode" "$nfqws_dns_instance" "$@"
}
nfqws_dns_nonce=$(nfqws_dns_ctl resolver-preflight) || exit 2
case "$nfqws_dns_nonce" in ''|*[!a-f0-9]*) exit 2;; esac
[ "${#nfqws_dns_nonce}" = 16 ] || exit 2
nfqws_dns_payload() (
    # We are inside procd's commit callback, with its original typed tree
    # still present. Do not json_load/reparse: jshn -r sanitizes mount keys.
    # Compare the complete frame before adding the one owned generation.
    [ "$(json_dump)" = "$1" ] || exit 2
    json_select instances && json_select "$nfqws_dns_instance" || exit 2
    local nfqws_dns_type
    if json_get_type nfqws_dns_type env; then
        [ "$nfqws_dns_type" = object ] && json_select env || exit 2
    else
        json_add_object env || exit 2
    fi
    # Never overwrite an operator's value in the reserved namespace.
    if json_get_type nfqws_dns_type NFQWS2_DNS_GENERATION; then exit 2; fi
    json_add_string NFQWS2_DNS_GENERATION "$nfqws_dns_id:$nfqws_dns_mode:$nfqws_dns_nonce" || exit 2
    json_select ''
    json_dump
)
nfqws_dns_committed=0
ubus() {
    case "$1:$2:$3" in
        call:service:add)
            [ "$#" = 4 ] && [ "$nfqws_dns_committed" = 0 ] || return 2
            nfqws_dns_commit=$(nfqws_dns_payload "$4") || { printf '%s\n' 'Native SmartDNS: hook_conflict' >&2; return 2; }
            printf '%s' "$nfqws_dns_commit" | nfqws_dns_ctl resolver-swap "$nfqws_dns_nonce" || return 2
            /bin/ubus call service add "$nfqws_dns_commit" || return 2
            nfqws_dns_committed=1
            ;;
        call:service:list|call:service:get_data|call:service:validate)
            /bin/ubus "$@";;
        *)
            # A changed native framework must fail before an unknown service
            # mutation, including invocations with new command-line switches.
            for nfqws_dns_arg in "$@"; do [ "$nfqws_dns_arg" != service ] || return 2; done
            /bin/ubus "$@";;
    esac
}
# rc.common selects service.add for this selected-instance call. Its original
# metadata, jail, file monitoring and triggers pass unchanged. One owned
# environment generation forces a planned restart even for an otherwise
# identical frame; procd may correctly elide an ordinary repeated start.
set -- /etc/init.d/dnsmasq start "$nfqws_dns_instance"
. /etc/rc.common
[ "$nfqws_dns_committed" = 1 ] || exit 2
