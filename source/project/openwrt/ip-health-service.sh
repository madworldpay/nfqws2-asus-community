#!/bin/sh
# Invoked only by the existing core procd service, never independently at boot.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ "$(id -u)" = 0 ] || exit 1
NFQWS_LIB=/usr/lib/nfqws2
NFQWS_RUN=/var/run/nfqws2-native
NFQWS_BIN=/usr/bin/nfqws2
. "$NFQWS_LIB/update/service-lease.sh" || exit 1
nfqws_native_update_enter core firewall || exit 0
. "$NFQWS_LIB/platform.sh" || exit 1
. "$NFQWS_LIB/firewall.sh" || exit 1
. "$NFQWS_LIB/ip-health/runtime.sh" || exit 1
# Core preflight already generated this protected, shell-quoted whitelist. Do
# not parse a possibly newly edited config while observing an older process.
[ -f "$NFQWS_RUN/config.env" ] && [ ! -L "$NFQWS_RUN/config.env" ] || exit 0
[ "$(LC_ALL=C ls -ln "$NFQWS_RUN/config.env" | awk '{print $1 ":" $2 ":" $3}')" = '-rw-------:1:0' ] || exit 0
. "$NFQWS_RUN/config.env" || exit 0
attempt=0
while [ "$attempt" -lt 10 ]; do
    pid=$(nfqws_process_pid) || pid=''
    if [ -n "$pid" ]; then
        case "$(nfqws_queue_facts "$NFQUEUE_NUM")" in "bound "*" $pid") break;; esac
    fi
    sleep 1; attempt=$((attempt + 1))
done
[ "$attempt" -lt 10 ] || exit 0
# Sidecar failure is reported in its RAM status, never as a main-core failure.
nfqws_health_start
