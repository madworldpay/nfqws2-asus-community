#!/bin/sh
# A fixed foreground engine, launched as the guardian's direct child. The
# journal's executable field is identity data and is never executed.
set -f
umask 077
[ "$#" = 2 ] || exit 2
case "$2" in ''|*[!a-f0-9]*) exit 2;; esac
[ "${#2}" = 32 ] || exit 2
case "$1" in start|stop|verify) :;; *) exit 2;; esac
command=$1;request=$2
. /jffs/nfqws2-asus-smartdns/native-common.sh || exit 2
IFS= read -r sd_current_boot < /proc/sys/kernel/random/boot_id || exit 2
sd_lock && sd_state_load && [ "$sd_request_id" = "$request" ] && [ "$sd_boot_id" = "$sd_current_boot" ] || exit 2
if [ "$command" = verify ]; then sd_runtime_alive;result=$?;sd_unlock;exit "$result";fi
if [ "$command" = stop ]; then
    # Only the verified restore path may stop an engine in active use.
    [ "$sd_phase" = rolled_back ] || { sd_unlock;exit 2; }
    sd_stop_runtime;result=$?;sd_unlock;exit "$result"
fi
[ "$sd_phase" = prepared ] && [ "$sd_runtime_pid" = 0 ] && sd_same "$sd_guard_pid" "$sd_guard_ticks" || exit 2
IFS= read -r sd_line < "/proc/$$/stat" || exit 2
sd_rest=${sd_line##*) };set -- $sd_rest
[ "${2:-}" = "$sd_guard_pid" ] || exit 2
sd_engine=$("$sd_bb" readlink -f /opt/lib/nfqws2-asus/smartdns-engine) || exit 2
sd_run=$sd_opt/smartdns/jobs/$request
sd_protected "$sd_engine" d && sd_protected "$sd_run" d && sd_protected "$sd_run/engine.digest" - && sd_protected "$sd_run/runtime.conf" - || exit 2
IFS= read -r sd_digest < "$sd_run/engine.digest" || exit 2
case "$sd_digest" in ''|*[!a-f0-9]*) exit 2;; esac
[ "${#sd_digest}" = 64 ] && [ "$("$sd_bb" readlink "$sd_engine/current")" = "$sd_digest" ] || exit 2
sd_bundle=$sd_engine/$sd_digest
sd_protected "$sd_bundle" d && sd_protected "$sd_bundle/smartdns" - && [ -x "$sd_bundle/smartdns" ] || exit 2
sd_size=$("$sd_bb" wc -c < "$sd_run/runtime.conf")
[ "$sd_size" -le 131072 ] 2>/dev/null || exit 2
sd_runtime_pid=$$;sd_runtime_ticks=$(sd_startof "$$");sd_runtime_exe=$sd_bundle/smartdns
sd_state_save || exit 2
sd_unlock
cd "$sd_bundle" || exit 2
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
exec ./smartdns -f -c "$sd_run/runtime.conf" -p "$sd_run/runtime.pid"
