#!/bin/sh
[ "$1" = pre-commit ] || exit 0
exec /usr/bin/php8-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/update/apk-precommit.php
