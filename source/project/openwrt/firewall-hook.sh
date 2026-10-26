#!/bin/sh
# fw4 invokes this after rebuilding its rules. A stopped service stays stopped.
/usr/lib/nfqws2/control.sh check >/dev/null 2>&1 || exit 0
exec /usr/lib/nfqws2/control.sh firewall
