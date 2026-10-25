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
    /usr/bin/php-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/smartdns/native-control.php -- "$1" "$nfqws_dns_id" "$nfqws_dns_mode" "$nfqws_dns_instance"
}
nfqws_dns_ctl resolver-preflight || exit 2
nfqws_dns_committed=0
ubus() {
    case "$1:$2:$3" in
        call:service:add)
            [ "$#" = 4 ] && [ "$nfqws_dns_committed" = 0 ] || return 2
            printf '%s' "$4" | nfqws_dns_ctl resolver-swap || return 2
            /bin/ubus "$@" || return 2
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
# metadata, jail, file monitoring, environment and triggers pass unchanged.
set -- /etc/init.d/dnsmasq start "$nfqws_dns_instance"
. /etc/rc.common
[ "$nfqws_dns_committed" = 1 ] || exit 2
