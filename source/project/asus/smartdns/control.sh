#!/bin/sh
# Private root entry; no arbitrary command, path or profile argument.
set -f
[ "$#" = 1 ] || exit 2
case "$1" in status|rollback|upgrade|remove|resume|queue-resume) ;; *) exit 2;; esac
if [ "$1" = queue-resume ]; then
    [ -f /opt/etc/nfqws-asus-web/smartdns/resume-intent.json ] || exit 0
    exec /opt/libexec/nfqws2-asus/busybox start-stop-daemon -S -b -p /opt/var/run/nfqws2-smartdns-resume.pid -x /bin/sh -- /opt/lib/nfqws2-asus/smartdns/control.sh resume
fi
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
exec /opt/bin/php-cgi -n -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/smartdns/control.php -- "$1"
