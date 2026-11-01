#!/bin/sh
# Fixed asynchronous core reconcile. No paths/actions come from HTTP fields.
PATH=/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ "$(id -u)" = 0 ] || exit 1
[ "$#" = 1 ] || exit 2
case "$1" in queue|worker) ;; *) exit 2;; esac
run=/tmp/nfqws2-asus
private=$run/ip-health-private
entry=/opt/lib/nfqws2-asus/ip-health/control.sh
bb=/opt/libexec/nfqws2-asus/busybox
# A stopped core without a sidecar has nothing to reconcile. Never manufacture
# persistent state or relax the core's private runtime to queue a request.
[ -e "$private" ] || [ -L "$private" ] || exit 0
for path in "$run" "$private"; do
    [ -d "$path" ] && [ ! -L "$path" ] && [ "$(LC_ALL=C ls -dn "$path" | awk '{print $1 ":" $3}')" = 'drwx------:0' ] || exit 1
done
if [ "$1" = queue ]; then
    (trap '' HUP; "$bb" sh "$entry" worker </dev/null >/dev/null 2>&1 7>&- 8>&- 9>&- &)
    exit $?
fi
# The coordinator's duplicate lease is distinct from the core/update leases.
exec 7>&- 8>&- 9>&-
umask 077
for path in "$private/reconcile.lock" "$private/reconcile.log"; do
    [ ! -L "$path" ] || exit 1
    if [ -e "$path" ]; then
        [ -f "$path" ] && [ "$(LC_ALL=C ls -ln "$path" | awk '{print $1 ":" $2 ":" $3}')" = '-rw-------:1:0' ] || exit 1
    fi
done
exec 9>>"$private/reconcile.lock" || exit 1
/opt/bin/flock -n 9 || exit 0
exec >"$private/reconcile.log" 2>&1
/opt/etc/init.d/S51nfqws2 reconcile 7>&- 8>&- 9>&-
