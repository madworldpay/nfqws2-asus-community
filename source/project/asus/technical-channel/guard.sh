#!/bin/sh
set -f
umask 077
exec /opt/bin/php-cgi -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/technical-channel/worker.php -- guard "$1"
