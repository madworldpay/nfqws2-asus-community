#!/bin/sh
# Stop only guardians whose protected boot/start/executable identity still matches.
set -f
. "${0%/*}/paths.sh" || exit 1
root=$root/runs
[ -d "$root" ] || exit 0
[ ! -L "$root" ] || exit 1
boot=$("$bb" cat /proc/sys/kernel/random/boot_id) || exit 1
same() {
    local line rest exe
    IFS= read -r line 2>/dev/null < "/proc/$pid/stat" || return 1
    rest=${line##*) };set -- $rest
    [ "${1:-}" != Z ] && [ "${20:-}" = "$start" ] || return 1
    exe=$("$bb" readlink "/proc/$pid/exe") || return 1
    owned_guard_exe "$exe"
}
result=0
set +f
for run in "$root"/*; do
    [ -d "$run" ] && [ ! -L "$run" ] || continue
    job=${run##*/};case "$job" in *[!a-f0-9]*)continue;;esac
    [ "${#job}" = 32 ] || continue
    [ -f "$run/guard.pid" ] && [ ! -L "$run/guard.pid" ] || continue
    [ "$("$bb" ls -ldn "$run" | "$bb" awk '{print $3}')" = 0 ] || exit 1
    [ "$("$bb" cat "$run/boot" 2>/dev/null)" = "$boot" ] || continue
    IFS=' ' read -r pid start < "$run/guard.pid"
    case "$pid:$start" in *[!0-9:]*|:*|0:*|1:*)exit 1;;esac
    same || continue
    "$bb" kill -TERM "$pid" || { result=1;continue; }
    n=0;while same && [ "$n" -lt "$stop_ticks" ];do pause_tick;n=$((n+1));done
    same && result=1
 done
exit "$result"
