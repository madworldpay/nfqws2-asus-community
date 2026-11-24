<?php
/** Read-only, package-local data. Selection returns ordinary portable import documents. */
final class AsusZapret2Pack
{
    private const GROUPS = ['presets', 'http80', 'tcp', 'udp', 'voice'];

    private static function data(string $name): array
    {
        static $cache = [];
        if (!isset($cache[$name])) {
            $raw = @file_get_contents(__DIR__.'/zapret2-pack/'.$name.'.json');
            if ($raw === false) throw new RuntimeException('package_resource_unavailable');
            $cache[$name] = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
        }
        return $cache[$name];
    }

    /** Append collection data; existing identifiers and resource proofs never change. */
    private static function combinedCatalog(): array
    {
        $catalog = self::data('catalog');
        $extra = self::data('collections');
        $extra['entries'] = array_merge($extra['entries'], self::data('zemidala-index')['entries']);
        $seen = [];
        foreach (array_merge($catalog['entries'], $catalog['assets']) as $row) $seen[$row['id']] = true;
        foreach (['entries', 'assets'] as $group) {
            foreach ($extra[$group] as $row) {
                if (isset($seen[$row['id']])) throw new RuntimeException('package_resource_unavailable');
                $seen[$row['id']] = true;
                $catalog[$group][] = $row;
            }
        }
        return $catalog;
    }

    private static function resourcePool(): array
    {
        $pool = self::data('resources');
        $extra = self::data('collections')['resources'];
        if (array_intersect_key($pool, $extra)) throw new RuntimeException('package_resource_unavailable');
        return $pool + $extra;
    }

    public static function catalog(): array
    {
        $catalog = self::combinedCatalog();
        foreach (['entries', 'assets'] as $group) {
            foreach ($catalog[$group] as &$row) unset($row['source_url'], $row['source_page']);
            unset($row);
        }
        return $catalog;
    }

    public static function containsLua(string $id, string $bytes): bool
    {
        $asset = self::resourcePool()[$id] ?? null;
        return ($asset['kind'] ?? null) === 'lua'
            && ($asset['data_base64'] ?? null) === base64_encode($bytes);
    }

    private static function zemidalaRecord(array $row, ?AsusProfileCatalogTransport $source): array
    {
        if (is_file(__DIR__.'/zapret2-pack/zemidala-offline.json')) {
            try {
                $record = self::data('zemidala-offline')[$row['id']] ?? null;
            } catch (JsonException $error) {
                throw new RuntimeException('resource_unavailable', 0, $error);
            }
            if (!is_array($record)) throw new RuntimeException('resource_unavailable');
            return $record;
        }
        require_once __DIR__.'/profile-catalog-transport.php';
        $path = $row['source_page'];
        $pin = self::data('zemidala-index')['pages'][$path];
        try {
            $page = json_decode(($source ?? new AsusProfileCatalogTransport())->zemidalaPage(
                $path, $pin['bytes'], $pin['sha256']
            ), true, 32, JSON_THROW_ON_ERROR);
        } catch (RuntimeException | JsonException $error) {
            throw new RuntimeException('resource_unavailable', 0, $error);
        }
        $matches = array_values(array_filter($page['items'] ?? [],
            static fn($item) => ($item['id'] ?? null) === $row['source_id']));
        if (count($matches) !== 1) throw new RuntimeException('resource_unavailable');
        return $matches[0];
    }

    private static function zemidalaTemplate(array $row, ?AsusProfileCatalogTransport $source): array
    {
        $record = self::zemidalaRecord($row, $source);
        $steps = $record['steps'] ?? [];
        $protocol = $record['proto'] ?? '';
        if (!is_array($steps) || !$steps || !array_is_list($steps) || !in_array($protocol, ['http', 'tls'], true)) {
            throw new RuntimeException('resource_unavailable');
        }
        foreach ($steps as $step) {
            if (!is_string($step) || !preg_match('/^--lua-desync=[A-Za-z0-9_:+.,<>=!-]+$/D', $step)) {
                throw new RuntimeException('resource_unavailable');
            }
        }
        if (!hash_equals($row['id'], substr(hash('sha256', "zemidala\0".$protocol."\0".implode("\0", $steps)), 0, 24))) {
            throw new RuntimeException('resource_unavailable');
        }
        $scope = $protocol === 'tls'
            ? '--filter-tcp=443 --filter-l7=tls --payload=tls_client_hello'
            : '--filter-tcp=80 --filter-l7=http --payload=http_req';
        $arguments = implode(' ', $steps);
        // This exact stock fixture was verified against the vendor package.
        // A distinct name leaves any user's similarly named resource alone.
        $arguments = preg_replace('/:(blob|pattern|seqovl_pattern)=tls_clienthello(?=:| |$)/',
            ':$1=zemidala_tls_clienthello', $arguments, -1, $stock);
        $config = $scope.' --hostlist=/opt/etc/nfqws2/lists/user.list '.$arguments;
        $resources = [];
        if ($stock) {
            $config = '--blob=zemidala_tls_clienthello:@RESOURCE_1 '.$config;
            $resources[] = '9be6fbcee6bf3f6cd6274d99d8a4bf39';
        }
        return ['config' => 'NFQWS_ARGS_CUSTOM="'.$config.'"'.PHP_EOL, 'resources' => $resources];
    }

    public static function documents(string $id, ?AsusProfileCatalogTransport $source = null): array
    {
        $catalog = self::combinedCatalog();
        foreach (array_merge($catalog['entries'], $catalog['assets']) as $row) {
            if ($row['id'] !== $id) continue;
            $assetsOnly = $row['group'] === 'assets';
            if (($row['unavailable'] ?? []) || ($row['resident'] ?? false)) {
                throw new RuntimeException('package_resource_unavailable');
            }
            $template = null;
            if (!$assetsOnly && in_array($row['group'], self::GROUPS, true)) {
                $template = match ($row['collection'] ?? null) {
                    'zemidala' => self::zemidalaTemplate($row, $source),
                    null => self::data($row['group'])[$id] ?? null,
                    default => self::data('collections')['templates'][$id] ?? null,
                };
                if ($template === null) throw new RuntimeException('package_resource_unavailable');
            }
            preg_match('/^.{1,120}/us', $row['title'], $title);
            $ctx = [
                'purpose' => $title[0], 'operator' => 'Unknown',
                'comment' => ($row['attribution'] ?? $catalog['attribution'])."\n"
                    .'Zapret2 Magisk v'.$catalog['version'].".\n"
                    .'DPI Detector: 0 runs. Date, provider, region, mode, TCP, HTTP, TLS 1.2, TLS 1.3, QUIC: unknown.'
                    .(empty($row['adapted']) ? '' : ' ASUS: '.implode(', ', $row['adapted']).' → multisplit (1,midsld).'),
            ];
            if (($row['collection'] ?? null) === 'zemidala') {
                $ctx['comment'] = "Zemidala / nfqws2-strategies\n"
                    .'DPI Detector: 0 runs. Date, provider, region, mode, TCP, HTTP, TLS 1.2, TLS 1.3, QUIC: unknown.';
            } elseif (isset($row['collection'])) {
                $collection = self::data('collections')['collections'][$row['collection']];
                $ctx['comment'] = $row['attribution']."\n".$collection['title']
                    .' source SHA256 '.$row['sha256'].'.'."\n"
                    .'DPI Detector: 0 runs. Date, provider, region, mode, TCP, HTTP, TLS 1.2, TLS 1.3, QUIC: unknown.'
                    .(empty($row['adapted']) ? '' : "\n".'Adaptation: '.implode(' ', $row['adapted']));
            }
            $pool = self::resourcePool();
            $files = $package = $references = $dependencies = [];
            foreach (($assetsOnly ? $row['parts'] : $template['resources']) as $i => $key) {
                $asset = $pool[$key];
                $alias = 'RESOURCE_'.($i + 1);
                $asset['id'] = $key;
                $asset['aliases'] = [$alias];
                if (isset($asset['data_base64'])) {
                    $asset['source_sha256'] = $asset['sha256'];
                    $files[] = $asset;
                } else {
                    $package[] = $asset;
                }
                if (!$assetsOnly) {
                    $references[] = ['id' => 'dependency_'.($i + 1), 'state' => 'included',
                        'resource_id' => $key, 'aliases' => [$alias]];
                    $dependencies[] = ['id' => $alias, 'kind' => 'file', 'included' => true];
                }
            }
            $docs = [];
            if (!$assetsOnly) {
                $docs[] = ['type' => 'nfqws2_strategy', 'schema_version' => 2, 'mode' => 'config',
                    'versions' => ['core' => 'unknown', 'web' => 'unknown'], 'omitted_options' => 0,
                    'config' => $template['config'], 'dependencies' => $dependencies] + $ctx;
            }
            $docs[] = ['type' => 'nfqws2_resources', 'schema_version' => 2, 'context' => $ctx,
                'files' => $files, 'package_files' => $package, 'audit' => [
                    'scope' => $assetsOnly ? 'files_only' : 'static_explicit_references', 'references' => $references,
                    'unresolved' => [], 'missing_reason' => '', 'complete' => true,
                ]];
            return array_map(static fn(array $doc): string => json_encode($doc, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR), $docs);
        }
        throw new RuntimeException('invalid_request');
    }
}
