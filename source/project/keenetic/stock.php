<?php
declare(strict_types=1);

/** Read the installed KeeneticOS firmware and the Entware packages used by the panel. */
final class NfqwsKeeneticStock
{
    private const CORE = 'nfqws2-keenetic';
    private const WEB = 'nfqws-keenetic-web';

    public static function boardRecord(array $lines): array
    {
        $fields = [];
        foreach ($lines as $line) {
            if (!preg_match('/^\s*(hw_id|arch|release):[ \t]*([A-Za-z0-9._+-]{1,64})\s*$/D', $line, $m)) continue;
            $fields[$m[1]] = array_key_exists($m[1], $fields) ? null : $m[2];
        }
        $model = $fields['hw_id'] ?? '';
        return [
            'model' => preg_match('/^(?:KN|NC)-[0-9]{4}$/D', $model) ? $model : null,
            'machine' => $fields['arch'] ?? null,
            'firmware' => $fields['release'] ?? null,
        ];
    }

    public static function board(): array
    {
        $board = NfqwsPlatform::run(['/bin/ndmc', '-c', 'show version'], 5);
        return self::boardRecord($board['status'] === 0 ? $board['output'] : []);
    }

    public static function brand(?string $model): string
    {
        if (preg_match('/^KN-[0-9]{4}$/D', $model ?? '')) return 'Keenetic';
        if (preg_match('/^NC-[0-9]{4}$/D', $model ?? '')) return 'Netcraze';
        return 'Keenetic / Netcraze';
    }

    public static function inspect(): array
    {
        $fields = self::board();
        $service = NfqwsPlatform::serviceStatus('keenetic-entware');
        return $fields + [
            'core' => NfqwsEntwarePackage::installed(self::CORE),
            'web' => NfqwsEntwarePackage::installed(self::WEB),
            'service_running' => $service['status'] === 0 ? $service['service'] : null,
        ];
    }
}
