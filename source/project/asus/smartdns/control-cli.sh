#!/bin/sh
[ "$#" = 1 ] || { printf '%s\n' 'Usage: nfqws2-smartdns-control status|rollback' >&2;exit 2; }
case "$1" in status|rollback) exec /bin/sh /opt/lib/nfqws2-asus/smartdns/control.sh "$1";; *) exit 2;; esac
