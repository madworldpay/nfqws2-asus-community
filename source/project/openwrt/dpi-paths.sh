# Native OpenWrt paths. The package installs this root-owned fixed module.
bb=/bin/busybox
root=/tmp/nfqws2-native-state/dpi-detector
lib=/usr/lib/nfqws2/dpi
install_root=/usr/lib/nfqws2/dpi-detector
php=/usr/bin/php-cgi
terminal_control=/usr/share/nfqws2-web/dpi-terminal-lifecycle.php
probe_path=/usr/sbin:/usr/bin:/sbin:/bin
stop_ticks=6
pause_tick() { "$bb" sleep 1; }
owned_guard_exe() { [ "$1" = /bin/busybox ]; }
