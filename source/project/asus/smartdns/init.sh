#!/bin/sh
# Entware startup, independent from NFQWS2 and ARK. No profile means no action.
case "${1:-}" in
    start) /bin/sh /opt/lib/nfqws2-asus/smartdns/control.sh queue-resume;;
    stop) [ ! -f /opt/etc/nfqws-asus-web/smartdns/resume-intent.json ] || /bin/sh /opt/lib/nfqws2-asus/smartdns/control.sh upgrade;;
    restart) "$0" stop && "$0" start;;
    *) exit 2;;
esac
