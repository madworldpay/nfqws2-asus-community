#!/opt/libexec/nfqws2-asus/busybox sh
umask 077
set -f
[ "$#" = 1 ] || exit 1
case "$1" in ''|*[!a-f0-9]*) exit 1;; esac
[ "${#1}" = 32 ] || exit 1
exec /opt/bin/php-cgi -n -d extension=/opt/lib/php8/openssl.so -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/update/worker.php -- guard-check "$1"
