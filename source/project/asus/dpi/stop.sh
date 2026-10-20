#!/bin/sh
# Stop only guardians whose protected boot/start/executable identity still matches.
set -f
bb=/opt/libexec/nfqws2-asus/busybox
root=/opt/var/lib/nfqws2-asus/dpi-detector/runs
[ -d "$root" ] || exit 0
[ ! -L "$root" ] || exit 1
boot=$("$bb" cat /proc/sys/kernel/random/boot_id) || exit 1
same() {
    local line rest exe
    IFS= read -r line 2>/dev/null < "/proc/$pid/stat" || return 1
    rest=${line##*) };set -- $rest
    [ "${1:-}" != Z ] && [ "${20:-}" = "$start" ] || return 1
    exe=$("$bb" readlink "/proc/$pid/exe") || return 1
    case "$exe" in /opt/libexec/nfqws2-asus/busybox|/opt/libexec/nfqws2-asus/armv7-2.6/busybox|/opt/libexec/nfqws2-asus/armv7-3.2/busybox) return 0;;*)return 1;;esac
}
result=0
set +f
for run in "$root"/*; do
    [ -d "$run" ] && [ ! -L "$run" ] || continue
    job=${run##*/};case "$job" in *[!a-f0-9]*)continue;;esac
    [ "${#job}" = 32 ] || continue
    [ -f "$run/guard.pid" ] && [ ! -L "$run/guard.pid" ] || continue
    [ "$("$bb" stat -t "$run" | "$bb" awk '{print $5}')" = 0 ] || exit 1
    [ "$("$bb" cat "$run/boot" 2>/dev/null)" = "$boot" ] || continue
    IFS=' ' read -r pid start < "$run/guard.pid"
    case "$pid:$start" in *[!0-9:]*|:*|0:*|1:*)exit 1;;esac
    same || continue
    "$bb" kill -TERM "$pid" || { result=1;continue; }
    n=0;while same && [ "$n" -lt 24 ];do "$bb" usleep 250000;n=$((n+1));done
    same && result=1
 done
exit "$result"
