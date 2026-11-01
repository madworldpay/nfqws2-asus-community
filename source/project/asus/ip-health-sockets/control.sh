#!/bin/sh
# Fixed optional-capability entry. No HTTP-selected package, command or path.
set -f
[ "$#" = 1 ] || exit 2
case "$1" in queue|run|status) ;; *) exit 2;; esac
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
if [ "$1" = queue ]; then
    exec /opt/libexec/nfqws2-asus/busybox start-stop-daemon -S -b -p /opt/var/run/nfqws2-ip-health-sockets.pid -x /bin/sh -- /opt/lib/nfqws2-asus/ip-health-sockets/control.sh run </dev/null >/dev/null 2>&1 7>&- 8>&- 9>&-
fi
/opt/bin/php-cgi -n -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/ip-health-sockets/worker.php -- "$1" 7>&- 8>&- 9>&-
result=$?
[ "$1" = run ] || exit "$result"
# PHP has exited: native manager mutex, capability and updater leases are all
# closed before normal lifecycle reconciliation. Reconcile preserves stop intent.
[ "$result" = 0 ] || { [ "$result" = 2 ] && exit 0; exit "$result"; }
exec /opt/etc/init.d/S51nfqws2 reconcile </dev/null >/dev/null 2>&1 7>&- 8>&- 9>&-
