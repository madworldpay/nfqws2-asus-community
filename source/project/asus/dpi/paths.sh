# Installed beside the guardian; never selected from HTTP or ambient variables.
bb=/opt/libexec/nfqws2-asus/busybox
root=/opt/var/lib/nfqws2-asus/dpi-detector
lib=/opt/lib/nfqws2-asus/dpi
install_root=/opt/lib/nfqws2-asus/dpi-detector
php=/opt/bin/php-cgi
probe_path=/opt/bin:/usr/bin:/bin
stop_ticks=24
pause_tick() { "$bb" usleep 250000; }
owned_guard_exe() {
    case "$1" in /opt/libexec/nfqws2-asus/busybox|/opt/libexec/nfqws2-asus/armv7-2.6/busybox|/opt/libexec/nfqws2-asus/armv7-3.2/busybox) return 0;;*)return 1;;esac
}
