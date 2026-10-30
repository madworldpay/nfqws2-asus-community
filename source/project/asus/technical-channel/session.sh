#!/bin/sh
# The shell remains as a crash guardian if PHP is killed unexpectedly.
set -f
umask 077
# Do not retain a CGI mutation lease/session lock in this detached guardian.
# Preserve the shell's own script descriptor; close only inherited descriptors.
for task_fd_path in /proc/$$/fd/*; do
    task_fd=${task_fd_path##*/}
    case "$task_fd" in 0|1|2|*[!0-9]*) continue;; esac
    task_target=$(readlink "$task_fd_path" 2>/dev/null)
    [ "$task_target" = /opt/lib/nfqws2-asus/technical-channel/session.sh ] && continue
    eval "exec $task_fd>&-"
done
case "$1" in *[!a-f0-9]*|'') exit 1;; esac
[ "${#1}" = 32 ] || exit 1
/opt/bin/php-cgi -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/technical-channel/worker.php -- run "$1" &
child=$!
wait "$child"
exec /opt/bin/php-cgi -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/technical-channel/worker.php -- recover "$1"
