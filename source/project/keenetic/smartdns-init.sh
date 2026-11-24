#!/bin/sh
case "${1:-}" in
    start|stop) ;;
    restart) "$0" stop && exec "$0" start; exit $? ;;
    *) exit 1 ;;
esac
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
exec /opt/bin/php-cgi -d register_argc_argv=1 -q -f /opt/share/nfqws-asus-web/keenetic-smartdns.php -- "$1"
