# The Keenetic package uses Entware's BusyBox and the stock interface.
bb=/opt/bin/busybox
root=/opt/var/lib/nfqws2-asus/dpi-detector
lib=/opt/lib/nfqws2-asus/dpi
install_root=/opt/lib/nfqws2-asus/dpi-detector
php=/opt/bin/php-cgi
terminal_control=/opt/share/nfqws-asus-web/dpi-terminal-lifecycle.php
probe_path=/opt/bin:/usr/bin:/bin
stop_ticks=24
pause_tick() { "$bb" usleep 250000; }
owned_guard_exe() { [ "$1" = "$("$bb" readlink -f "$bb")" ]; }
