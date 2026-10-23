#!/bin/sh

PIDFILE="/opt/var/run/nfqws2.pid"
if [ ! -f "$PIDFILE" ] || ! kill -0 $(cat "$PIDFILE") 2>/dev/null; then
  exit 0
fi
if [ "$table" != "mangle" ] && [ "$table" != "nat" ]; then
  exit 0
fi

# $type is `iptables` or `ip6tables`
for attempt in 1 2 3 4 5; do
  /opt/etc/init.d/S51nfqws2 firewall_"$type"
  rc=$?
  [ "$rc" -eq 0 ] && exit 0
  [ "$attempt" -eq 5 ] && break
  sleep 1
done
exit "$rc"
