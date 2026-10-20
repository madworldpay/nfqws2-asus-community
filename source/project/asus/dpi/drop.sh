#!/bin/sh
# Verify the real post-drop identity before executing even --version.
set -f
uids=0;gids=0;caps=0
while read -r key a b c d; do
    case "$key" in
        Uid:) [ "$a:$b:$c:$d" = 65534:65534:65534:65534 ] || exit 126;uids=1;;
        Gid:) [ "$a:$b:$c:$d" = 65534:65534:65534:65534 ] || exit 126;gids=1;;
        Groups:) case "$a" in ''|65534) [ -z "$b$c$d" ] || exit 126;;*)exit 126;;esac;;
        CapInh:|CapPrm:|CapEff:|CapAmb:) case "$a" in ''|*[!0]*)exit 126;;esac;caps=$((caps+1));;
    esac
done < /proc/self/status
[ "$uids:$gids" = 1:1 ] && [ "$caps" -ge 3 ] && [ "$#" -gt 0 ] || exit 126
exec "$@"
