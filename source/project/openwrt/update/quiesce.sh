#!/bin/sh
set -f
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ "$#" = 2 ] || exit 2
case "$1" in upgrade|remove) ;; *) exit 2;; esac
case "$2" in ipk|apk) NFQWS_PKG_FORMAT=$2;; *) exit 2;; esac
. /usr/lib/nfqws2/update/package-functions.sh || exit 1
nfqws_package_snapshot && nfqws_package_stop_services_internal "$1"
