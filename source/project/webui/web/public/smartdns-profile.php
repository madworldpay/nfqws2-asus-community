<?php
/** A closed structured profile. User text can never become SmartDNS directives. */
final class AsusSmartDnsProfileError extends RuntimeException
{
    public function __construct(public readonly string $field) { parent::__construct('invalid_profile'); }
}

final class AsusSmartDnsProfile
{
    private static function fail(string $field): never { throw new AsusSmartDnsProfileError($field); }
    private static function keys(array $value, array $keys, string $field): void
    {
        $actual = array_keys($value); sort($actual); sort($keys);
        if ($actual !== $keys) self::fail($field);
    }
    public static function domain(mixed $value, string $field): string
    {
        if (!is_string($value) || strlen($value) > 254) self::fail($field);
        $name = strtolower(str_ends_with($value, '.') ? substr($value, 0, -1) : $value);
        if ($name === '' || strlen($name) > 253 || self::isIp($name)) self::fail($field);
        foreach (explode('.', $name) as $label) {
            if (!preg_match('/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/D', $label)) self::fail($field);
        }
        return $name;
    }
    private static function isIp(mixed $value): bool
    { return is_string($value) && strlen($value) <= 45 && @inet_pton($value) !== false; }
    private static function ip(mixed $value, string $field): string
    {
        if (!is_string($value) || !self::isIp($value)) self::fail($field);
        return strtolower(inet_ntop(inet_pton($value)));
    }
    private static function ips(mixed $value, string $field, bool $required): array
    {
        if (!is_array($value) || !array_is_list($value) || count($value) > 8 || ($required && !$value)) self::fail($field);
        $out = [];
        foreach ($value as $i => $ip) $out[] = self::ip($ip, "$field.$i");
        return array_values(array_unique($out));
    }
    private static function match(array $value, string $field): array
    {
        self::keys($value, ['name', 'include_subdomains'], $field);
        if (!is_bool($value['include_subdomains'])) self::fail($field.'.include_subdomains');
        return ['name'=>self::domain($value['name'], $field.'.name'), 'include_subdomains'=>$value['include_subdomains']];
    }
    public static function normalize(array $input): array
    {
        self::keys($input, ['schema_version', 'upstreams', 'records'], 'profile');
        if (strlen(json_encode($input, JSON_THROW_ON_ERROR)) > 65536 || $input['schema_version'] !== 1) self::fail('profile');
        if (!is_array($input['upstreams']) || !array_is_list($input['upstreams']) || count($input['upstreams']) < 1 || count($input['upstreams']) > 32) self::fail('upstreams');
        $servers = []; $ids = []; $default = false; $assignments = 0;
        foreach ($input['upstreams'] as $i => $server) {
            $f = 'upstreams.'.$i;
            if (!is_array($server)) self::fail($f);
            self::keys($server, ['id','label','protocol','address','port','tls_name','url','bootstrap','default','domains'], $f);
            if (!is_string($server['id']) || !preg_match('/^[a-z][a-z0-9_-]{0,31}$/D', $server['id']) || isset($ids[$server['id']])) self::fail($f.'.id');
            $ids[$server['id']] = true;
            if (!is_string($server['label']) || !preg_match('//u', $server['label']) || preg_match('/[\x00-\x1f\x7f]/', $server['label']) || preg_match_all('/./us', $server['label']) > 80) self::fail($f.'.label');
            if (!in_array($server['protocol'], ['udp','tcp','dot','doh'], true)) self::fail($f.'.protocol');
            if (!is_int($server['port']) || $server['port'] < 1 || $server['port'] > 65535) self::fail($f.'.port');
            if (!is_bool($server['default'])) self::fail($f.'.default');
            $default = $default || $server['default'];
            $server['bootstrap'] = self::ips($server['bootstrap'], $f.'.bootstrap', false);
            if (is_string($server['address']) && self::isIp($server['address'])) {
                $server['address'] = self::ip($server['address'], $f.'.address');
            } else {
                $server['address'] = self::domain($server['address'], $f.'.address');
                if (!$server['bootstrap']) self::fail($f.'.bootstrap');
            }
            $secure = in_array($server['protocol'], ['dot','doh'], true);
            if ($secure) $server['tls_name'] = self::domain($server['tls_name'], $f.'.tls_name');
            elseif ($server['tls_name'] !== '') self::fail($f.'.tls_name');
            if ($server['protocol'] === 'doh') {
                $url = $server['url'];
                if (!is_string($url) || strlen($url) > 2048 || preg_match('/[^\x21-\x7e]|["\'\\\\#]/', $url)) self::fail($f.'.url');
                $parts = parse_url($url);
                if (!is_array($parts) || ($parts['scheme'] ?? '') !== 'https' || !isset($parts['host']) || isset($parts['user']) || isset($parts['pass']) || isset($parts['fragment'])) self::fail($f.'.url');
                $host = trim($parts['host'], '[]');
                if (!self::isIp($host)) self::domain($host, $f.'.url');
                if (($parts['port'] ?? 443) !== $server['port']) self::fail($f.'.port');
            } elseif ($server['url'] !== '') self::fail($f.'.url');
            if (!is_array($server['domains']) || !array_is_list($server['domains'])) self::fail($f.'.domains');
            $assignments += count($server['domains']);
            if ($assignments > 256) self::fail('upstreams');
            $domains = [];
            foreach ($server['domains'] as $j => $d) {
                if (!is_array($d)) self::fail($f.'.domains.'.$j);
                $d = self::match($d, $f.'.domains.'.$j);
                $domains[($d['include_subdomains'] ? 'suffix:' : 'exact:').$d['name']] = $d;
            }
            ksort($domains); $server['domains'] = array_values($domains);
            // Stable field order is part of the preview hash, independent of JSON key order.
            $servers[] = array_replace(array_fill_keys(['id','label','protocol','address','port','tls_name','url','bootstrap','default','domains'], null), $server);
        }
        if (!$default) self::fail('upstreams.default');
        if (!is_array($input['records']) || !array_is_list($input['records']) || count($input['records']) > 64) self::fail('records');
        $records = []; $seen = [];
        foreach ($input['records'] as $i => $record) {
            $f = 'records.'.$i;
            if (!is_array($record)) self::fail($f);
            self::keys($record, ['name','include_subdomains','addresses','checked_at'], $f);
            $d = self::match(['name'=>$record['name'], 'include_subdomains'=>$record['include_subdomains']], $f);
            $key = ($d['include_subdomains'] ? 'suffix:' : 'exact:').$d['name'];
            if (isset($seen[$key])) self::fail($f.'.name'); $seen[$key] = true;
            $checked = $record['checked_at'];
            if ($checked !== null && (!is_string($checked) || !preg_match('/^\d{4}-\d{2}-\d{2}$/D', $checked) || !checkdate((int)substr($checked,5,2),(int)substr($checked,8,2),(int)substr($checked,0,4)))) self::fail($f.'.checked_at');
            $records[] = $d + ['addresses'=>self::ips($record['addresses'], $f.'.addresses', true), 'checked_at'=>$checked];
        }
        return ['schema_version'=>1, 'upstreams'=>$servers, 'records'=>$records];
    }
    public static function hash(array $profile): string
    {
        return hash('sha256', json_encode(self::normalize($profile), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
    }
    private static function pattern(array $match): string { return ($match['include_subdomains'] ? '' : '-.').$match['name']; }
    public static function render(array $profile, int $port): array
    {
        $profile = self::normalize($profile);
        if ($port < 1024 || $port > 65535) self::fail('listen_port');
        $groups = []; $members = [];
        foreach ($profile['upstreams'] as $server) foreach ($server['domains'] as $d) {
            $key = self::pattern($d);
            if (!isset($groups[$key])) $groups[$key] = ['domain'=>$d['name'], 'include_subdomains'=>$d['include_subdomains'], 'servers'=>[]];
            $groups[$key]['servers'][] = $server['id'];
        }
        ksort($groups);
        foreach ($groups as &$g) {
            sort($g['servers']); $g['group'] = 'community_'.substr(hash('sha256', implode(',', $g['servers'])), 0, 16);
            foreach ($g['servers'] as $id) $members[$id][$g['group']] = true;
        }
        unset($g);
        $lines = ['# Generated by NFQWS2 ASUS Community', 'bind 127.0.0.1:'.$port, 'bind-tcp 127.0.0.1:'.$port,
            'cache-size 0', 'cache-persist no', 'serve-expired no', 'prefetch-domain no', 'speed-check-mode none',
            'response-mode fastest-response', 'dualstack-ip-selection no', 'audit-enable no', 'log-level off',
            'ca-file /opt/etc/ssl/certs/ca-certificates.crt'];
        foreach ($profile['upstreams'] as $s) {
            $directive = ['udp'=>'server', 'tcp'=>'server-tcp', 'dot'=>'server-tls', 'doh'=>'server-https'][$s['protocol']];
            $address = (self::isIp($s['address']) && strlen(inet_pton($s['address'])) === 16) ? '['.$s['address'].']' : $s['address'];
            $line = $directive.' '.($s['protocol'] === 'doh' ? $s['url'] : $address.':'.$s['port']);
            if (in_array($s['protocol'], ['dot','doh'], true)) $line .= ' -host-name '.$s['tls_name'].' -tls-host-verify '.$s['tls_name'];
            foreach (array_keys($members[$s['id']] ?? []) as $group) $line .= ' -group '.$group;
            if (!$s['default']) $line .= ' -exclude-default-group';
            $ips = $s['bootstrap'];
            if (self::isIp($s['address'])) array_unshift($ips, $s['address']);
            // Numeric connection addresses avoid asking the resolver we are configuring
            // to resolve its own upstream. No implicit plaintext bootstrap is added.
            foreach (array_values(array_unique($ips)) as $ip) $lines[] = $line.' -host-ip '.$ip;
        }
        foreach ($groups as $key => $g) $lines[] = 'nameserver /'.$key.'/'.$g['group'];
        $overlaps = [];
        foreach ($profile['records'] as $r) {
            $lines[] = 'address /'.self::pattern($r).'/'.implode(',', $r['addresses']);
            foreach ($groups as $g) {
                if ($r['name'] === $g['domain'] || ($g['include_subdomains'] && str_ends_with($r['name'], '.'.$g['domain'])) || ($r['include_subdomains'] && str_ends_with($g['domain'], '.'.$r['name']))) {
                    $overlaps[] = ['record'=>$r['name'], 'dns_domain'=>$g['domain']];
                }
            }
        }
        return ['config'=>implode("\n", $lines)."\n", 'groups'=>array_values($groups), 'overlaps'=>$overlaps];
    }
}
