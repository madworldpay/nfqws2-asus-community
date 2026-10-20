#!/bin/sh
# Native, bounded owner of an isolated validation session. Never changes DNS.
set -f
umask 077
bb=/bin/busybox
root=/opt/etc/nfqws-asus-web/smartdns
lib=/opt/lib/nfqws2-asus/smartdns
updates=/opt/var/lib/nfqws2-asus/updates
mode=guard
if [ "${1:-}" = session ]; then
    [ "$#" = 4 ] || exit 2
    mode=session;job=$2;parent=$3;parent_ticks=$4
else
    [ "$#" = 1 ] || exit 2
    job=$1
fi
case "$job" in ''|*[!a-f0-9]*) exit 2;; esac
[ "${#job}" = 32 ] || exit 2
run=$root/jobs/$job
[ -d "$run" ] && [ ! -L "$root" ] && [ ! -L "$root/jobs" ] && [ ! -L "$run" ] || exit 2
IFS= read -r boot < /proc/sys/kernel/random/boot_id || exit 2

startof() {
    local line rest
    case "$1" in ''|*[!0-9]*) return 1;; esac
    [ "$1" -gt 1 ] 2>/dev/null || return 1
    IFS= read -r line 2>/dev/null < "/proc/$1/stat" || return 1
    rest=${line##*) };set -- $rest
    [ "${1:-Z}" != Z ] && [ -n "${20:-}" ] || return 1
    printf '%s\n' "${20}"
}
same() { [ -n "$2" ] && [ "$(startof "$1")" = "$2" ]; }
before() { "$bb" awk -v end="$1" '{exit !($1<end)}' /proc/uptime; }
own_session() {
    local line rest
    IFS= read -r line < "/proc/$$/stat" || return 1
    rest=${line##*) };set -- $rest
    [ "${3:-}" = "$$" ] && [ "${4:-}" = "$$" ]
}
end_session() {
    # The live anchor proves ownership of the whole session even after PHP
    # dies. Its PID cannot be reused while we are checking/signalling it.
    own_session || exit 2
    trap '' HUP INT TERM
    kill -TERM "-$$" 2>/dev/null || :
    "$bb" sleep 1
    kill -KILL "-$$" 2>/dev/null || :
    exit 2
}

if [ "$mode" = session ]; then
    same "$parent" "$parent_ticks" && own_session || exit 2
    IFS=' ' read -r p t b deadline extra < "$run/guard" || exit 2
    [ -z "$extra" ] && [ "$p" = "$parent" ] && [ "$t" = "$parent_ticks" ] && [ "$b" = "$boot" ] || exit 2
    # Our direct parent must be the owner that created the protected proof.
    IFS= read -r line < "/proc/$$/stat" || exit 2
    rest=${line##*) };set -- $rest
    [ "${2:-}" = "$parent" ] || exit 2
    trap ':' HUP INT TERM
    printf '%s %s %s\n' "$$" "$(startof "$$")" "$boot" > "$run/.anchor"
    "$bb" mv "$run/.anchor" "$run/anchor" || end_session
    unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
    # Only the two shell owners retain the updater/DNS leases. An engine or
    # helper must never accidentally keep them after the owner has finished.
    (
        exec 8>&- 9>&-
        exec /opt/bin/php-cgi -d register_argc_argv=1 -q -f "$lib/config-worker.php" -- "$job"
    ) >/dev/null 2>&1 &
    worker=$!;worker_ticks=$(startof "$worker")
    printf '%s %s %s\n' "$worker" "$worker_ticks" "$boot" > "$run/worker"
    while same "$worker" "$worker_ticks"; do
        same "$parent" "$parent_ticks" && before "$deadline" || end_session
        "$bb" sleep 1
    done
    wait "$worker";rc=$?
    if [ "$rc" = 0 ]; then printf '%s\n' finished > "$run/done";else printf '%s\n' worker_lost > "$run/done";fi
    # Stay alive until the owner cleans our group, or clean it ourselves if
    # the owner disappears. Exiting here would orphan engine grandchildren.
    while same "$parent" "$parent_ticks" && before "$deadline"; do "$bb" sleep 1;done
    end_session
fi

[ -f "$updates/apply.lock" ] && [ ! -L "$updates/apply.lock" ] || exit 2
exec 8>>"$updates/apply.lock" || exit 2
/usr/bin/flock -s -n 8 || exit 3
exec 9>>"$root/config.lock" || exit 2
lock_attempt=0
while ! /usr/bin/flock -n 9; do
    lock_attempt=$((lock_attempt+1));[ "$lock_attempt" -lt 20 ] || exit 3
    "$bb" sleep 0.1
done
ticks=$(startof "$$") || exit 2
deadline=$("$bb" awk '{printf "%.3f\n",$1+150}' /proc/uptime) || exit 2
printf '%s %s %s %s\n' "$$" "$ticks" "$boot" "$deadline" > "$run/.guard"
"$bb" mv "$run/.guard" "$run/guard" || exit 2
reason=''
trap 'reason=interrupted' HUP INT TERM
"$lib/session-owner" "$job" "$$" "$ticks" 8>&8 9>&9 >/dev/null 2>&1 &
anchor=$!;anchor_ticks=$(startof "$anchor")
while same "$anchor" "$anchor_ticks"; do
    [ -z "$reason" ] || break
    before "$deadline" || { reason=timed_out;break; }
    if [ -f "$run/done" ] && [ ! -L "$run/done" ]; then
        IFS= read -r reason < "$run/done"
        case "$reason" in finished|worker_lost) :;; *) reason=interrupted;; esac
        break
    fi
    "$bb" sleep 1
done
if [ -z "$reason" ]; then
    if before "$deadline"; then reason=worker_lost;else reason=timed_out;fi
fi
if same "$anchor" "$anchor_ticks"; then
    # Check the session ID as well as PID/starttime before a group signal.
    IFS= read -r line < "/proc/$anchor/stat" || exit 2
    rest=${line##*) };set -- $rest
    if [ "${3:-}" = "$anchor" ] && [ "${4:-}" = "$anchor" ]; then
        kill -TERM "-$anchor" 2>/dev/null || :
        "$bb" sleep 1
        if same "$anchor" "$anchor_ticks"; then kill -KILL "-$anchor" 2>/dev/null || :;fi
    fi
fi
wait "$anchor" 2>/dev/null || :
printf '%s\n' "$reason" > "$run/.outcome"
"$bb" mv "$run/.outcome" "$run/outcome" || exit 2
# No explicit LOCK_UN: the anchor inherited these open file descriptions.
# Closing the owner's FDs cannot unlock a surviving anchor's protection.
exit 0
