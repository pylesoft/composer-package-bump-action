<?php

declare(strict_types=1);

if ($argc < 4) {
    fwrite(STDERR, "Usage: php scripts/report_full_rebuild_churn.php <before-lock> <after-lock> <bumped-packages-file>\n");
    exit(1);
}

$beforeLockFile = $argv[1];
$afterLockFile = $argv[2];
$bumpedPackagesFile = $argv[3];

if (! is_file($beforeLockFile) || ! is_file($afterLockFile)) {
    fwrite(STDOUT, "  ℹ️ No lock snapshot available to compare broader churn\n");
    exit(0);
}

$beforePackages = loadPackageFingerprints($beforeLockFile);
$afterPackages = loadPackageFingerprints($afterLockFile);
$bumpedPackages = loadBumpedPackages($bumpedPackagesFile);
$packageNames = array_unique(array_merge(array_keys($beforePackages), array_keys($afterPackages)));
sort($packageNames);

$changes = [];

foreach ($packageNames as $packageName) {
    if (isset($bumpedPackages[$packageName])) {
        continue;
    }

    $beforeFingerprint = $beforePackages[$packageName] ?? null;
    $afterFingerprint = $afterPackages[$packageName] ?? null;

    if ($beforeFingerprint === $afterFingerprint) {
        continue;
    }

    $changes[] = [
        'name' => $packageName,
        'before' => $beforeFingerprint,
        'after' => $afterFingerprint,
    ];
}

if ($changes === []) {
    fwrite(STDOUT, "  ℹ️ No additional lock changes outside bumped packages during full rebuild\n");
    exit(0);
}

fwrite(STDOUT, "  ℹ️ Additional lock changes from full rebuild:\n");

foreach ($changes as $change) {
    $beforeDescription = describeFingerprint($change['before'] ?? null);
    $afterDescription = describeFingerprint($change['after'] ?? null);
    fwrite(STDOUT, "    - {$change['name']}: {$beforeDescription} -> {$afterDescription}\n");
}

function loadPackageFingerprints(string $lockFile): array
{
    $lockPayload = json_decode(file_get_contents($lockFile), true, 512, JSON_THROW_ON_ERROR);
    $packages = [];

    foreach (array_merge($lockPayload['packages'] ?? [], $lockPayload['packages-dev'] ?? []) as $package) {
        if (isset($package['name'], $package['version']) && is_string($package['name']) && is_string($package['version'])) {
            $packages[$package['name']] = [
                'version' => $package['version'],
                'source_reference' => extractReference($package['source'] ?? null),
                'dist_reference' => extractReference($package['dist'] ?? null),
            ];
        }
    }

    return $packages;
}

function extractReference(mixed $value): ?string
{
    if (! is_array($value)) {
        return null;
    }

    $reference = $value['reference'] ?? null;

    return is_string($reference) ? $reference : null;
}

function describeFingerprint(?array $fingerprint): string
{
    if ($fingerprint === null) {
        return '(not locked)';
    }

    $version = $fingerprint['version'] ?? '(unknown version)';
    $references = [];

    if (isset($fingerprint['source_reference']) && is_string($fingerprint['source_reference'])) {
        $references[] = "source: {$fingerprint['source_reference']}";
    }

    if (isset($fingerprint['dist_reference']) && is_string($fingerprint['dist_reference'])) {
        $references[] = "dist: {$fingerprint['dist_reference']}";
    }

    if ($references === []) {
        return $version;
    }

    return sprintf('%s [%s]', $version, implode(', ', $references));
}

function loadBumpedPackages(string $packagesFile): array
{
    if (! is_file($packagesFile) || filesize($packagesFile) === 0) {
        return [];
    }

    $packages = [];
    $lines = file($packagesFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);

    if ($lines === false) {
        return [];
    }

    foreach ($lines as $line) {
        $packages[$line] = true;
    }

    return $packages;
}
