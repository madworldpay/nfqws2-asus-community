#!/bin/sh
exec /opt/bin/php-cgi -d sys_temp_dir=/tmp/nfqws-asus-web -d upload_tmp_dir=/tmp/nfqws-asus-web -d session.save_path=/tmp/nfqws-asus-web/sessions -d doc_root=/opt/share/nfqws-asus-web -d cgi.fix_pathinfo=1
