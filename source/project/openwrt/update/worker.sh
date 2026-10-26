#!/bin/sh
set -f
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
[ "$#" = 2 ] || exit 2
case "$1" in guard-check|guard-prepare) ;; *) exit 2;; esac
case "$2" in ''|*[!a-f0-9]*) exit 2;; esac
[ "${#2}" = 32 ] || exit 2
exec /usr/bin/php8-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/update/worker.php -- "$1" "$2"
