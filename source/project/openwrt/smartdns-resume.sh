#!/bin/sh
# The common boot policy holds one owner throughout its bounded retry budget.
set -f
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
exec /usr/bin/php-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/smartdns/control.php -- boot-resume
