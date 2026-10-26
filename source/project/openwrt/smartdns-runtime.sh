#!/bin/sh
# Independent procd owner. Never drop the engine before verified DNS rollback.
set -f
umask 077
root=/tmp/nfqws2-native-state/smartdns-runtime
lib=/usr/lib/nfqws2/smartdns
ctl() { /usr/bin/php-cgi -d register_argc_argv=1 -q -f "$lib/native-control.php" -- "$@"; }
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
spec=$(ctl launch) || exit 2
[ -n "$spec" ] || exit 0
set -- $spec
[ "$#" = 2 ] || exit 2
id=$1;digest=$2
case "$id$digest" in *[!a-f0-9]*) exit 2;; esac
[ "${#id}" = 32 ] && [ "${#digest}" = 64 ] || exit 2
exec 8>>/tmp/nfqws2-native-state/updates/apply.lock || exit 2
/usr/bin/flock -s -n 8 || exit 3
startof() {
    local line rest
    IFS= read -r line 2>/dev/null < "/proc/$1/stat" || return 1
    rest=${line##*) };set -- $rest
    [ "${1:-Z}" != Z ] && [ -n "${20:-}" ] || return 1
    printf '%s\n' "${20}"
}
same() { [ -n "$2" ] && [ "$(startof "$1")" = "$2" ]; }
engine=/usr/lib/nfqws2/smartdns-engine/$digest/smartdns
"$engine" -f -c "$root/runtime.conf" -p "$root/runtime.pid" 8>&- >/dev/null 2>&1 &
child=$!;ticks=$(startof "$child")
cleanup() {
    trap '' HUP INT TERM
    # A conflict retains the child and backup. The service preflight blocks
    # an intentional stop until the panel has restored its owned DNS include.
    while :; do
        ctl exit "$id" >/dev/null 2>&1;rc=$?
        case "$rc" in 0|1) break;; esac
        /bin/busybox sleep 1
    done
    if same "$child" "$ticks"; then kill -TERM "$child" 2>/dev/null || :; fi
    n=0
    while same "$child" "$ticks" && [ "$n" -lt 3 ]; do /bin/busybox sleep 1;n=$((n+1));done
    if same "$child" "$ticks"; then kill -KILL "$child" 2>/dev/null || :; fi
    wait "$child" 2>/dev/null || :
    exit 0
}
trap cleanup HUP INT TERM
n=0
while ! ctl ready "$id" "$$" "$child" >/dev/null 2>&1; do
    same "$child" "$ticks" || cleanup
    n=$((n+1));[ "$n" -lt 5 ] || cleanup
    /bin/busybox sleep 1
done
while :; do
    ctl tick "$id" >/dev/null 2>&1;rc=$?
    case "$rc" in
        0|3) :;;
        10) exec 8>&-;;
        1) cleanup;;
        *) /bin/busybox sleep 1;continue;;
    esac
    /bin/busybox sleep 1
done
