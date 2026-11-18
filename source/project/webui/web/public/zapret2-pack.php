<?php
/** Read-only, package-local data. Selection returns ordinary portable import documents. */
final class AsusZapret2Pack
{
    private const GROUPS = ['presets', 'http80', 'tcp', 'udp', 'voice'];

    private static function data(string $name): array
    {
        static $cache = [];
        if (!isset($cache[$name])) {
            $raw = file_get_contents(__DIR__.'/zapret2-pack/'.$name.'.json');
            if ($raw === false) throw new RuntimeException('package_resource_unavailable');
            $cache[$name] = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
        }
        return $cache[$name];
    }

    public static function catalog(): array
    {
        $catalog = self::data('catalog');
        foreach (['entries', 'assets'] as $group) {
            foreach ($catalog[$group] as &$row) unset($row['source_url']);
            unset($row);
        }
        return $catalog;
    }

    public static function documents(string $id): array
    {
        $catalog = self::data('catalog');
        foreach (array_merge($catalog['entries'], $catalog['assets']) as $row) {
            if ($row['id'] !== $id) continue;
            $assetsOnly = $row['group'] === 'assets';
            if (($row['unavailable'] ?? []) || ($row['resident'] ?? false)) {
                throw new RuntimeException('package_resource_unavailable');
            }
            $template = null;
            if (!$assetsOnly && in_array($row['group'], self::GROUPS, true)) {
                $template = self::data($row['group'])[$id];
            }
            preg_match('/^.{1,120}/us', $row['title'], $title);
            $ctx = [
                'purpose' => $title[0], 'operator' => 'Unknown',
                'comment' => ($row['attribution'] ?? $catalog['attribution'])."\n"
                    .'Zapret2 Magisk v'.$catalog['version'].".\n"
                    .'DPI Detector: 0 runs. Date, provider, region, mode, TCP, HTTP, TLS 1.2, TLS 1.3, QUIC: unknown.'
                    .(empty($row['adapted']) ? '' : ' ASUS: '.implode(', ', $row['adapted']).' → multisplit (1,midsld).'),
            ];
            $pool = self::data('resources');
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
