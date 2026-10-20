---
name: Bug report
about: Create a report to help us improve
title: "[BUG] "
labels: ''
assignees: ''

---

**Опишите проблему**
Подробно опишите что делали и что не работает.

**Модель маршрутизатора**
Укажите полную модель роутера и прошивку

**Провайдер**
Укажите вашего провайдера и тип подключения (ppp/ethernet/...)

**Выполните команды и приложите их вывод**
`opkg info nfqws-keenetic-web`
```
<ВСТАВИТЬ СЮДА>
```

`/opt/etc/init.d/S80lighttpd restart`
```
<ВСТАВИТЬ СЮДА>
```

`cat /opt/etc/lighttpd/conf.d/80-nfqws.conf`
```
<ВСТАВИТЬ СЮДА>
```

`ps | grep lighttpd`
```
<ВСТАВИТЬ СЮДА>
```
