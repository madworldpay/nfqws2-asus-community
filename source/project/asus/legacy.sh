#!/bin/sh
# One exact-image optional backend. No kernel-version-wide module fallback.
asus_legacy_digest() { /opt/libexec/nfqws2-asus/busybox sha256sum "$1"; }

asus_legacy_check() {
    local actual
    actual=$(asus_legacy_digest "$1") || return 1
    [ "${actual%% *}" = "$2" ]
}

asus_legacy_fingerprints() {
    asus_legacy_check /usr/sbin/iptables c4a8633d3a310108dac7bd458ab0a559dfe6f92f823575f7af96f69f2f11ed05 &&
    asus_legacy_check /sbin/rc 82fb775dcb954d2b7cbc0710e074ded96aa706c2887d32f039ac8cb33df615c7 &&
    asus_legacy_check /bin/busybox 1cd3f3f563b28cfdb06d80e7b70f21e4b42736ea63b62149003e02f02e66e45f &&
    asus_legacy_check /opt/lib/nfqws2-asus/legacy/rt-ac87u-384.13_10/nfnetlink_queue.ko 1e5fd88ebf5830d56f6b151de0c791f02b3c3db0a539490fbf32709add0151ab
}

asus_load_legacy_module() {
    [ "$(nvram get productid 2>/dev/null)" = RT-AC87U ] &&
    [ "$(nvram get firmver 2>/dev/null)" = 3.0.0.4 ] &&
    [ "$(nvram get buildno 2>/dev/null)" = 384.13 ] &&
    [ "$(nvram get extendno 2>/dev/null)" = 10 ] &&
    [ "$(uname -rm)" = '2.6.36.4brcmarm armv7l' ] || return 1
    asus_legacy_fingerprints || return 1
    # Kernel vermagic/MODVERSIONS checks remain authoritative; never force.
    insmod /opt/lib/nfqws2-asus/legacy/rt-ac87u-384.13_10/nfnetlink_queue.ko
}
