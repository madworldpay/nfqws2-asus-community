#!/bin/sh
# Keep the vendor's relative musl loader, without its sysctl/init wrapper.
umask 077
directory=$(/opt/bin/php-cgi -q -f /opt/lib/nfqws2-asus/smartdns/cli.php) || {
    printf '%s\n' 'Install SmartDNS from the NFQWS2 panel first.' >&2
    exit 1
}
cd "$directory" || exit 1
exec ./smartdns "$@"
