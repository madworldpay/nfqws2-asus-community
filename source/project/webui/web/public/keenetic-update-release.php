<?php
declare(strict_types=1);
require_once __DIR__.'/update-manifest.php';

/** Select one companion IPK from the release's signed Keenetic checksum list. */
final class NfqwsKeeneticUpdateRelease
{
    private const VERSION = '1\.3\.3\+b([1-9][0-9]{0,8})-([1-9][0-9]{0,8})';
    private const ARCHITECTURES = ['aarch64-3.10', 'mips-3.4', 'mipsel-3.4'];

    public static function candidate(
        string $sums,
        string $signature,
        string $publicKey,
        string $arch,
        string $installed
    ): ?array {
        if (!in_array($arch, self::ARCHITECTURES, true)) {
            throw new RuntimeException('unsupported_abi');
        }
        if (!preg_match('/^'.self::VERSION.'$/D', $installed, $previous)) {
            throw new RuntimeException('unsupported_version');
        }
        if ($sums === '' || strlen($sums) > 1024) {
            throw new RuntimeException('invalid_manifest');
        }
        AsusPackageManifest::verifySignature($sums, base64_encode($signature), $publicKey);

        $packages = [];
        $version = null;
        $target = null;
        foreach (explode("\n", rtrim($sums, "\n")) as $line) {
            $pattern = '~^([a-f0-9]{64})  (nfqws2-keenetic-community_('.self::VERSION.')_([a-z0-9.-]+)\.ipk)$~D';
            if (!preg_match($pattern, $line, $match)
                || !in_array($match[6], self::ARCHITECTURES, true)
                || isset($packages[$match[6]])
                || ($version !== null && $version !== $match[3])) {
                throw new RuntimeException('invalid_manifest');
            }
            $version = $match[3];
            $target = [(int)$match[4], (int)$match[5]];
            $packages[$match[6]] = [
                'family' => $match[6],
                'filename' => $match[2],
                'sha256' => $match[1],
            ];
        }
        if (count($packages) !== count(self::ARCHITECTURES)) {
            throw new RuntimeException('invalid_manifest');
        }
        if ($target <= [(int)$previous[1], (int)$previous[2]]) return null;
        return [
            'revision' => hash('sha256', $sums),
            'package_version' => $version,
            'build' => $target[0],
            'package' => $packages[$arch],
        ];
    }
}
