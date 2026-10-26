#!/bin/sh
# This process owns the lifetime even when HTTP, browser or PHP worker disappears.
set -f
umask 077
. "${0%/*}/paths.sh" || exit 1
job=${1:-}
case "$job" in ''|*[!a-f0-9]*) exit 1;; esac
[ "${#job}" = 32 ] || exit 1
run=$root/runs/$job
[ -d "$run" ] && [ ! -L "$run" ] || exit 1
uid=$("$bb" id -u)
[ "$("$bb" ls -ldn "$run" | "$bb" awk '{print $3}')" = "$uid" ] || exit 1
boot=$("$bb" cat /proc/sys/kernel/random/boot_id) || exit 1
guard_exe=$("$bb" readlink "/proc/$$/exe") || exit 1
printf '%s\n' "$boot" > "$run/boot"
startof() {
    local line rest
    [ "$1" -gt 1 ] 2>/dev/null || return 1
    IFS= read -r line 2>/dev/null < "/proc/$1/stat" || return 1
    rest=${line##*) }; set -- $rest
    [ "${1:-}" != Z ] && [ -n "${20:-}" ] || return 1
    printf '%s\n' "${20}"
}
same() {
    [ -n "$1" ] && [ -n "$2" ] && [ "$(startof "$1")" = "$2" ] &&
        [ "$("$bb" cat /proc/sys/kernel/random/boot_id)" = "$boot" ]
}
# Only direct children spawned here are signalled, with continuous PID/start/boot
# identity across exec. Registry files are evidence, never authority to kill a PID.
signalprobe() {
    if same "$probe" "$probe_start"; then "$bb" kill -"$1" "$probe" 2>/dev/null; fi
    return 0
}
worker='';worker_start='';probe='';probe_start='';reason='';ending=0
trap 'reason=cancelled; ending=1' HUP INT TERM
printf '%s %s\n' "$$" "$(startof "$$")" > "$run/guard.pid"
# Readiness precedes the worker: even an immediate first request is admitted.
printf 'ready\n' > "$run/ack"
"$php" -d register_argc_argv=1 -q -f "$lib/worker.php" -- "$job" >/dev/null 2>&1 &
worker=$!
worker_start=$(startof "$worker")
while same "$worker" "$worker_start"; do
    [ "$ending" = 0 ] || break
    if [ -e "$run/cancel" ]; then reason=cancelled; break; fi
    deadline=''; IFS= read -r deadline < "$run/deadline" || :
    if ! "$bb" awk -v limit="$deadline" 'BEGIN {if(limit !~ /^[0-9]+([.][0-9]+)?$/)exit 1} {exit !($1<limit)}' /proc/uptime; then reason=timed_out; break; fi
    if [ -f "$run/probe.deadline" ]; then
        deadline=''; IFS= read -r deadline < "$run/probe.deadline" || :
        if ! "$bb" awk -v limit="$deadline" 'BEGIN {if(limit !~ /^[0-9]+([.][0-9]+)?$/)exit 1} {exit !($1<limit)}' /proc/uptime; then reason=timed_out; break; fi
    fi
    total=$("$bb" du -sk "$run" | "$bb" awk '{print $1}')
    work=/tmp/nfqws2-dpi/$job
    if [ -d "$work" ] && [ ! -L "$work" ]; then worksize=$("$bb" du -sk "$work" | "$bb" awk '{print $1}');total=$((total+worksize));fi
    [ "$total" -le 4096 ] 2>/dev/null || { reason=output_limit; break; }
    set +f
    for file in "$run"/g*.stdout "$run"/g*.stderr; do
        [ -f "$file" ] || continue
        limit=1048576;case "$file" in *.stderr)limit=65536;;esac
        bytes=$("$bb" wc -c < "$file")
        [ "$bytes" -le "$limit" ] 2>/dev/null || { reason=output_limit; break; }
    done
    set -f
    [ -z "$reason" ] || break
    if [ -n "$probe" ] && ! same "$probe" "$probe_start"; then
        wait "$probe"; code=$?
        printf '%s\n' "$code" > "$run/probe.exit.new"
        probe='';probe_start=''
        "$bb" rm -f "$run/probe.deadline"
        # Publish last: PHP may immediately request the next group, including
        # its new deadline. Cleanup above must never remove that new deadline.
        "$bb" mv "$run/probe.exit.new" "$run/probe.exit"
    fi
    if [ -z "$probe" ] && [ -f "$run/probe.request" ] && [ ! -L "$run/probe.request" ]; then
        cwd='';IFS= read -r cwd < "$run/probe.cwd" || :
        case "$cwd" in /|"/tmp/nfqws2-dpi/$job") :;; *) reason=invalid_state;break;; esac
        "$bb" rm -f "$run/probe.request"
        (
            cd "$cwd" || exit 1
            exec "$bb" env -i PATH="$probe_path" LANG=C LC_ALL=C TZ=UTC HOME="$cwd" XDG_CONFIG_HOME="$cwd" XDG_CACHE_HOME="$cwd" XDG_STATE_HOME="$cwd" TMPDIR="$cwd" TOKIO_WORKER_THREADS=1 "$bb" sh "$lib/probe.sh" "$job"
        ) < /dev/null >> "$run/g0.stdout" 2>> "$run/g0.stderr" &
        probe=$!
        probe_start=$(startof "$probe")
        # $! is our child before it can register or exec. A suspended child is
        # therefore still owned and terminated if PHP disappears at this point.
        if [ -n "$probe_start" ]; then printf '%s %s\n' "$probe" "$probe_start" > "$run/spawn.pid"; fi
    fi
    pause_tick
done
printf '%s\n' "$reason" > "$run/ending.reason"
printf 'closed\n' > "$run/closing"
if [ -z "$reason" ] && [ -e "$run/cancel" ]; then reason=cancelled; fi
if [ -n "$reason" ]; then
    signalprobe TERM
    if same "$worker" "$worker_start"; then "$bb" kill -TERM "$worker" 2>/dev/null; fi
    "$bb" sleep 2
    signalprobe KILL
    if same "$worker" "$worker_start"; then "$bb" kill -KILL "$worker" 2>/dev/null; fi
else
    # A failed/dead coordinator must not leave its registered network probe live.
    signalprobe TERM
    "$bb" sleep 2
    signalprobe KILL
fi
wait "$worker"; code=$?
[ -z "$probe" ] || wait "$probe"
[ -n "$reason" ] || { [ "$code" = 0 ] && reason=completed || reason=interrupted; }
set +f
"$bb" rm -f -- "$run"/g*.stdout "$run"/g*.stderr
"$bb" rm -rf -- "/tmp/nfqws2-dpi/$job"
# PHP finally is not run after TERM/KILL. Clean only this install's own regular
# staging files; active hash binaries and manual installations are never touched.
for file in "$install_root/.stage-$job" "$install_root/.active-$job"; do
    [ -f "$file" ] && [ ! -L "$file" ] || continue
    set -- $("$bb" ls -ldn "$file")
    [ "$3" = "$uid" ] && [ "$2" = 1 ] && "$bb" rm -f -- "$file"
done
"$bb" awk '{print $1}' /proc/uptime > "$run/ended.uptime"
printf '%s\n' "$reason" > "$run/outcome.new"
"$bb" mv "$run/outcome.new" "$run/outcome"
exit 0
