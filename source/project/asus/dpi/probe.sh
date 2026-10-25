#!/bin/sh
# A root-owned manifest is written by the coordinator, never by an HTTP client.
set -f
umask 077
. "${0%/*}/paths.sh" || exit 1
job=${1:-}
case "$job" in ''|*[!a-f0-9]*) exit 1;;esac
[ "${#job}" = 32 ] && [ "$("$bb" id -u)" = 0 ] || exit 1
run=$root/runs/$job
[ -d "$run" ] && [ ! -L "$run" ] && [ ! -L "$run/args" ] || exit 1
[ "$("$bb" ls -ldn "$run/args" | "$bb" awk '{print $3}')" = 0 ] || exit 1
[ ! -e "$run/closing" ] && [ -f "$run/ack" ] || exit 1
IFS=' ' read -r guard guard_start < "$run/guard.pid" || exit 1
case "$guard:$guard_start" in *[!0-9:]*|:*) exit 1;;esac
IFS= read -r line < "/proc/$guard/stat" || exit 1
rest=${line##*) };set -- $rest
[ "${1:-Z}" != Z ] && [ "${20:-}" = "$guard_start" ] || exit 1
IFS= read -r boot < "$run/boot" || exit 1
[ "$("$bb" cat /proc/sys/kernel/random/boot_id)" = "$boot" ] || exit 1
IFS= read -r line < /proc/self/stat || exit 1
rest=${line##*) };set -- $rest
printf '%s %s\n' "$$" "${20}" > "$run/probe.pid"
set --
while IFS= read -r arg || [ -n "$arg" ];do set -- "$@" "$arg";done < "$run/args"
[ "$#" -gt 0 ] || exit 1
"$bb" readlink -f "$1" > "$run/probe.exe" || exit 1
ulimit -S -v 196608 && ulimit -H -v 196608 || exit 1
ulimit -S -f 2048 && ulimit -H -f 2048 || exit 1
exec "$bb" start-stop-daemon -S -p "$run/unused-probe-lookup.pid" -c 65534:65534 -x "$bb" -- sh "$lib/drop.sh" "$@"
