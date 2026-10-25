#!/bin/sh
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
exec /usr/bin/php-cgi -d cgi.force_redirect=0 -d cgi.fix_pathinfo=0 \
    -d sys_temp_dir=/tmp/nfqws2-native-web -d upload_tmp_dir=/tmp/nfqws2-native-web \
    -d session.save_path=/tmp/nfqws2-native-web/sessions -d doc_root=/usr/share/nfqws2-web
