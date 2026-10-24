#!/bin/sh
# Fixed native entry points; neither config paths nor commands come from HTTP.
set -f
umask 077
case "${1:-}" in
    postconf)
        [ "$#" = 2 ] || exit 2
        case "$2" in
            /tmp/etc/dnsmasq.conf) :;;
            /etc/dnsmasq.conf)
                # Merlin may pass its firmware alias. Still mutate only the
                # fixed canonical config, never an arbitrary supplied path.
                [ "$(/bin/busybox readlink -f /etc/dnsmasq.conf)" = /tmp/etc/dnsmasq.conf ] || exit 2;;
            *) exit 2;;
        esac;;
    boot|upgrade|remove) [ "$#" = 1 ] || exit 2;;
    *) exit 2;;
esac
. /jffs/nfqws2-asus-smartdns/native-common.sh || exit 2
IFS= read -r sd_current_boot < /proc/sys/kernel/random/boot_id || exit 2

if [ "$1" != postconf ]; then
    # A fresh install is inert. A broken existing state must block package
    # removal, since deleting recovery tools could strand live forwarding.
    [ -e "$sd_root/state" ] || exit 0
    sd_protected "$sd_root" d && sd_protected "$sd_root/state" - && sd_state_load || exit 2
    [ "$sd_phase" != rolled_back ] || exit 0
    exec /bin/sh "$sd_root/recovery.sh" rollback "$sd_request_id"
fi

# On a new boot, lost USB/runtime/guardian or an expired trial, retain the
# freshly generated native DNS config. Never forward into a dead listener.
sd_protected "$sd_root" d && sd_protected "$sd_root/state" - && sd_state_load || exit 0
[ "$sd_boot_id" = "$sd_current_boot" ] && [ -d "$sd_opt" ] && [ -x "$sd_runtime_exe" ] && sd_runtime_alive && sd_same "$sd_guard_pid" "$sd_guard_ticks" || exit 0
case "$sd_phase" in
    awaiting_confirmation) sd_before "$sd_deadline" || exit 0;;
    confirmed|conflict) :;;
    *) exit 0;;
esac
sd_config=/tmp/etc/dnsmasq.conf
# Merlin creates this fixed root-owned file before calling postconf and only
# chmods it to 0644 afterwards. Remove staging write permissions ourselves;
# keep the ordinary protection checks for every subsequent read and edit.
if ! sd_protected "$sd_config" -; then
    [ ! -L "$sd_config" ] || exit 2
    "$sd_bb" ls -ldn "$sd_config" 2>/dev/null | "$sd_bb" awk -v owner="$sd_owner" '
        NR==1 {ok=($3==owner && $2==1 && ($1=="-rw-rw-rw-" || $1=="-rw-rw-r--"))}
        END {exit !(NR==1 && ok)}' || exit 2
    "$sd_bb" chmod go-w "$sd_config" || exit 2
fi
sd_protected "$sd_config" - && sd_protected "$sd_root/forwarding.awk" - || exit 2
sd_size=$("$sd_bb" wc -c < "$sd_config")
[ "$sd_size" -le 262144 ] 2>/dev/null || exit 2
"$sd_bb" tr -d '\000' < "$sd_config" | "$sd_bb" cmp -s "$sd_config" - || exit 2
sd_next=$sd_config.nfqws2.new
[ ! -e "$sd_next" ] && [ ! -L "$sd_next" ] || exit 2
trap '"$sd_bb" rm -f "$sd_next"' EXIT
# Preserve the firmware file mode and owner through the atomic replace.
"$sd_bb" cp -p "$sd_config" "$sd_next" || exit 2
sd_sources=$(sd_config_fingerprint "$sd_config") || exit 2
sd_render_forwarding "$sd_config" > "$sd_next" || exit 2
/usr/sbin/dnsmasq --test --conf-file="$sd_next" >/dev/null 2>&1 7>&- 8>&- 9>&- &
sd_child=$!;sd_child_ticks=$(sd_startof "$sd_child");sd_wait=0
while sd_same "$sd_child" "$sd_child_ticks"; do
    if [ "$sd_wait" -ge 5 ]; then
        kill -TERM "$sd_child" 2>/dev/null || :;"$sd_bb" sleep 1
        if sd_same "$sd_child" "$sd_child_ticks"; then kill -KILL "$sd_child" 2>/dev/null || :;fi
        wait "$sd_child" 2>/dev/null || :;exit 2
    fi
    sd_wait=$((sd_wait+1));"$sd_bb" sleep 1
done
wait "$sd_child" || exit 2
# Recheck liveness after the syntax test: no stale forwarding if USB was
# removed while the parser was running. A later failure is the guard's job.
sd_runtime_alive && sd_same "$sd_guard_pid" "$sd_guard_ticks" || exit 2
sd_current_sources=$(sd_config_fingerprint "$sd_config") || exit 2
[ "$sd_sources" = "$sd_current_sources" ] || exit 2
"$sd_bb" mv "$sd_next" "$sd_config" || exit 2
exit 0
