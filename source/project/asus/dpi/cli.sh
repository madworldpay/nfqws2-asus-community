#!/bin/sh
# Resolve only the verified optional component; leave other installations alone.
umask 077
binary=$(/opt/bin/php-cgi -q -f /opt/lib/nfqws2-asus/dpi/cli.php) || {
    printf '%s\n' 'Install DPI Detector in NFQWS2 WebUI first / Сначала установите DPI Detector в WebUI NFQWS2.' >&2
    exit 1
}
[ -n "$binary" ] && [ -x "$binary" ] || exit 1
exec "$binary" "$@"
