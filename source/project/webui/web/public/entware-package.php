<?php
declare(strict_types=1);

/** Read the installed package stanza returned by Entware opkg. */
final class NfqwsEntwarePackage
{
    public static function parseInstalled(array $lines, string $name): ?array
    {
        $record = [];
        $installed = null;
        foreach ([...$lines, ''] as $line) {
            if (trim($line) === '') {
                if (($record['Package'] ?? '') === $name
                    && preg_match('/^(?:install|hold) \S+ installed$/D', $record['Status'] ?? '')) {
                    if ($installed !== null
                        || !preg_match('/^[0-9a-zA-Z][0-9a-zA-Z.:_+~-]{0,95}$/D', $record['Version'] ?? '')
                        || !preg_match('/^[0-9a-zA-Z][0-9a-zA-Z._+-]{0,63}$/D', $record['Architecture'] ?? '')) {
                        return null;
                    }
                    $installed = ['version' => $record['Version'], 'architecture' => $record['Architecture']];
                }
                $record = [];
                continue;
            }
            if (preg_match('/^(Package|Version|Status|Architecture):[ \t]+(.+)$/D', $line, $m)) {
                if (isset($record[$m[1]])) return null;
                $record[$m[1]] = trim($m[2]);
            }
        }
        return $installed;
    }

    public static function installed(string $name): ?array
    {
        $result = NfqwsPlatform::run(['/opt/bin/opkg', 'status', $name], 5);
        return $result['status'] === 0 ? self::parseInstalled($result['output'], $name) : null;
    }
}
