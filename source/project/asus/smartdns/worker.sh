#!/bin/sh
# A separate owner enforces the deadline even during a blocking DNS lookup.
set -f
umask 077
bb=/opt/libexec/nfqws2-asus/busybox
root=$("$bb" readlink -f /opt/lib/nfqws2-asus/smartdns-engine) || exit 1
job=${1:-}
case "$job" in ''|*[!a-f0-9]*) exit 1;; esac
[ "${#job}" = 32 ] && [ -d "$root" ] && [ ! -L "$root" ] || exit 1
boot=$("$bb" cat /proc/sys/kernel/random/boot_id) || exit 1
startof() {
    local line rest
    [ "$1" -gt 1 ] 2>/dev/null || return 1
    IFS= read -r line 2>/dev/null < "/proc/$1/stat" || return 1
    rest=${line##*) }; set -- $rest
    [ "${1:-Z}" != Z ] && [ -n "${20:-}" ] || return 1
    printf '%s\n' "${20}"
}
same() {
    [ -n "$1" ] && [ -n "$2" ] && [ "$(startof "$1")" = "$2" ] &&
        [ "$("$bb" cat /proc/sys/kernel/random/boot_id)" = "$boot" ]
}
printf '%s %s %s\n' "$$" "$(startof "$$")" "$boot" > "$root/.guard-$job"
"$bb" mv "$root/.guard-$job" "$root/guard-$job" || exit 1
deadline=$("$bb" awk '{print $1+150}' /proc/uptime) || exit 1
reason=''
trap 'reason=interrupted' HUP INT TERM
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
/opt/bin/php-cgi -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/smartdns/worker.php -- "$job" >/dev/null 2>&1 &
worker=$!
worker_start=$(startof "$worker")
while same "$worker" "$worker_start"; do
    [ -z "$reason" ] || break
    if ! "$bb" awk -v end="$deadline" '{exit !($1<end)}' /proc/uptime; then reason=timed_out; break; fi
    "$bb" usleep 250000
done
if [ -n "$reason" ] && same "$worker" "$worker_start"; then
    # Freeze our own child before enumeration so it cannot spawn another probe.
    "$bb" kill -STOP "$worker" 2>/dev/null || :
    children=''
    set +f
    for path in /proc/[0-9]*/stat; do
        IFS= read -r line 2>/dev/null < "$path" || continue
        rest=${line##*) }; set -- $rest
        [ "${2:-}" = "$worker" ] || continue
        pid=${path#/proc/};pid=${pid%/stat};ticks=${20:-}
        [ -z "$ticks" ] || children="$children $pid:$ticks"
    done
    set -f
    for child in $children; do
        pid=${child%:*};ticks=${child#*:}
        if same "$pid" "$ticks"; then "$bb" kill -TERM "$pid" 2>/dev/null || :; fi
    done
    if same "$worker" "$worker_start"; then "$bb" kill -TERM "$worker" 2>/dev/null || :; "$bb" kill -CONT "$worker" 2>/dev/null || :; fi
    "$bb" usleep 1000000
    for child in $children; do
        pid=${child%:*};ticks=${child#*:}
        if same "$pid" "$ticks"; then "$bb" kill -KILL "$pid" 2>/dev/null || :; fi
    done
    if same "$worker" "$worker_start"; then "$bb" kill -KILL "$worker" 2>/dev/null || :; fi
fi
wait "$worker" 2>/dev/null || :
if [ -n "$reason" ]; then printf '%s\n' "$reason" > "$root/outcome-$job"; fi
exit 0
