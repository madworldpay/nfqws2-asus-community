#!/bin/sh
# Stock KeeneticOS owns S51nfqws2; it has no diagnostics subcommand.
PATH=/opt/sbin:/opt/bin:/opt/usr/sbin:/opt/usr/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
NFQWS_BIN=/opt/usr/bin/nfqws2
PIDFILE=/opt/var/run/nfqws2.pid
. /opt/lib/nfqws2-asus/diagnostics.sh || exit 1

ASUS_DIAGNOSTIC_PROCESS=$(asus_diagnostic_process)
queue=null
case "$ASUS_DIAGNOSTIC_PROCESS" in
    true)
        # The live argv includes the queue actually passed by the stock service,
        # including when its saved .run settings differ from the editable config.
        pid=$(cat "$PIDFILE" 2>/dev/null) || exit 1
        case "$pid" in ''|*[!0-9]*) exit 1 ;; esac
        queue=$(tr '\000' '\n' 2>/dev/null < "/proc/$pid/cmdline" | awk '
            /^--qnum=/ {
                count++; q=substr($0,8)
                if (q !~ /^[0-9]+$/ || q+0 > 65535) invalid=1
            }
            END { if (count == 1 && !invalid) printf "%.0f\n",q; else print "null" }')
        if [ "$(asus_diagnostic_process)" != true ] || [ "$(cat "$PIDFILE" 2>/dev/null)" != "$pid" ]; then
            ASUS_DIAGNOSTIC_PROCESS=null
            queue=null
        fi
        ;;
    false) queue=$(asus_diagnostic_queue /opt/etc/nfqws2/nfqws2.conf) ;;
esac
asus_diagnostics_json "$queue"
