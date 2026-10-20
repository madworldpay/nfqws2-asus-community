#!/bin/sh
# Independent of PHP and /opt after the initial guard lease handshake.
set -f
umask 077
[ "$#" = 2 ] || exit 2
case "$2" in ''|*[!a-f0-9]*) exit 2;; esac
[ "${#2}" = 32 ] || exit 2
command=$1;request=$2
case "$command" in guard|rollback|confirm|forward|dns) :;; *) exit 2;; esac
. /jffs/nfqws2-asus-smartdns/native-common.sh || exit 2
IFS= read -r sd_current_boot < /proc/sys/kernel/random/boot_id || exit 2
sd_lock;result=$?
[ "$result" = 0 ] || exit "$result"
sd_state_load && [ "$sd_request_id" = "$request" ] || exit 2

if [ "$command" = dns ]; then sd_dns53;result=$?;sd_unlock;exit "$result";fi
if [ "$command" = forward ]; then
    sd_forward;result=$?
    if [ "$result" != 0 ]; then printf '%s\n' "$sd_error";fi
    sd_unlock;exit "$result"
fi

if [ "$command" = rollback ]; then
    sd_rollback;result=$?;sd_unlock;exit "$result"
fi
[ "$sd_boot_id" = "$sd_current_boot" ] || exit 2
if [ "$command" = confirm ]; then
    if [ "$sd_phase" = confirmed ]; then sd_unlock;exit 0;fi
    if [ "$sd_phase" != awaiting_confirmation ] || ! sd_before "$sd_deadline" ||
        ! sd_runtime_alive || ! sd_same "$sd_guard_pid" "$sd_guard_ticks" || ! sd_forward_ready || ! sd_dns53; then sd_unlock;exit 2;fi
    sd_phase=confirmed;sd_state_save || exit 2
    sd_log confirmed;sd_unlock;exit 0
fi

# Refuse duplicate owners and stale/unknown phase. No deadline guessed from
# wall-clock time; the forwarding operation sets its own monotonic deadline.
[ "$sd_phase" = prepared ] || exit 2
if [ "$sd_runtime_pid" != 0 ]; then sd_runtime_alive || exit 2;fi
if [ "$sd_guard_pid" != 0 ] && sd_same "$sd_guard_pid" "$sd_guard_ticks"; then exit 2;fi
sd_protected "$sd_updates/apply.lock" - && [ -d "$sd_opt/smartdns" ] && [ ! -L "$sd_opt/smartdns" ] || exit 2
exec 8>>"$sd_updates/apply.lock" || exit 2
/usr/bin/flock -s -n 8 || exit 3
exec 9>>"$sd_opt/smartdns/config.lock" || exit 2
sd_attempt=0
while ! /usr/bin/flock -n 9; do
    sd_attempt=$((sd_attempt+1));[ "$sd_attempt" -lt 20 ] || exit 3
    "$sd_bb" sleep 0.1
done
sd_guard_pid=$$;sd_guard_ticks=$(sd_startof "$$")
sd_state_save || exit 2
sd_owned_child=;sd_owned_ticks=
if [ "$sd_runtime_pid" = 0 ]; then
    # The guardian creates the child, so PHP/browser loss cannot leave an
    # unknown engine between launch and transfer of ownership.
    sd_unlock
    /bin/sh /opt/lib/nfqws2-asus/smartdns/runtime.sh start "$request" </dev/null >/dev/null 2>&1 7>&- 8>&- 9>&- &
    sd_owned_child=$!;sd_owned_ticks=$(sd_startof "$sd_owned_child");sd_start_wait=0
    while [ "$sd_start_wait" -lt 5 ]; do
        if sd_state_load && [ "$sd_runtime_pid" = "$sd_owned_child" ] && sd_runtime_alive; then break;fi
        sd_same "$sd_owned_child" "$sd_owned_ticks" || break
        sd_start_wait=$((sd_start_wait+1));"$sd_bb" sleep 1
    done
    sd_lock && sd_state_load || exit 2
    if [ "$sd_guard_pid" != "$$" ] || [ "$sd_runtime_pid" != "$sd_owned_child" ] || ! sd_runtime_alive; then
        if sd_same "$sd_owned_child" "$sd_owned_ticks"; then
            kill -TERM "$sd_owned_child" 2>/dev/null || :;"$sd_bb" sleep 1
            if sd_same "$sd_owned_child" "$sd_owned_ticks"; then kill -KILL "$sd_owned_child" 2>/dev/null || :;fi
        fi
        wait "$sd_owned_child" 2>/dev/null || :
        sd_rollback || :;sd_unlock;exit 2
    fi
fi
[ ! -L "$sd_root/ready" ] || exit 2
printf '%s %s %s %s\n' "$request" "$$" "$sd_guard_ticks" "$sd_boot_id" > "$sd_root/.ready.$$"
"$sd_bb" mv "$sd_root/.ready.$$" "$sd_root/ready" || exit 2
sd_prepare_end=$("$sd_bb" awk '{printf "%.3f\n",$1+30}' /proc/uptime)
sd_log guard_ready;sd_unlock
sd_signal=0;sd_leased=1;sd_stalled=0
trap 'sd_signal=1' HUP INT TERM
while :; do
    "$sd_bb" sleep 1
    sd_lock;sd_lock_result=$?
    if [ "$sd_lock_result" = 3 ]; then continue;fi
    if [ "$sd_lock_result" != 0 ]; then sd_log invalid_state || :;exit 2;fi
    if ! sd_state_load || [ "$sd_request_id" != "$request" ] || [ "$sd_boot_id" != "$sd_current_boot" ]; then
        sd_log invalid_state;sd_unlock;exit 2
    fi
    # A failed durable transition must not turn into a DNS restart every
    # second. Keep the owner/lease and allow an explicit verified retry.
    if [ "$sd_stalled" = 1 ] && [ "$sd_phase" != rolled_back ]; then sd_unlock;continue;fi
    case "$sd_phase" in
        rolled_back)
            sd_unlock
            if [ -n "$sd_owned_child" ] && ! sd_same "$sd_owned_child" "$sd_owned_ticks"; then wait "$sd_owned_child" 2>/dev/null || :;fi
            exit 0;;
        confirmed)
            if [ "$sd_leased" = 1 ]; then exec 8>&- 9>&-;sd_leased=0;fi
            if [ "$sd_signal" = 1 ] || [ ! -d "$sd_opt" ] || [ ! -x "$sd_runtime_exe" ] || ! sd_runtime_alive; then sd_log runtime_lost;sd_rollback || sd_stalled=1;fi;;
        prepared|awaiting_confirmation)
            sd_expired=0
            if [ "$sd_phase" = prepared ]; then sd_before "$sd_prepare_end" || sd_expired=1
            else sd_before "$sd_deadline" || sd_expired=1;fi
            if [ "$sd_signal" = 1 ] || [ "$sd_expired" = 1 ] || [ ! -d "$sd_opt" ] || [ ! -x "$sd_runtime_exe" ] || ! sd_runtime_alive; then
                if [ "$sd_expired" = 1 ]; then sd_log timed_out;else sd_log interrupted;fi
                sd_rollback || sd_stalled=1
            fi;;
        rolling_back) sd_rollback || sd_stalled=1;;
        conflict) :;;
    esac
    sd_unlock
done
