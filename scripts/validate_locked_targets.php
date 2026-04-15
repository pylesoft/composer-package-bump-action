<?php

declare(strict_types=1);

if ($argc < 3) {
    fwrite(STDERR, "Usage: php scripts/validate_locked_targets.php <targets-file> <lock-file>\n");
    exit(1);
}

$targetsFile = $argv[1];
$lockFile = $argv[2];

if (! is_file($targetsFile) || filesize($targetsFile) === 0) {
    fwrite(STDOUT, "⚠️ No bumped packages to validate\n");
    exit(0);
}

if (! is_file($lockFile)) {
    fwrite(STDERR, "❌ Missing composer.lock file\n");
    exit(1);
}

$lockPayload = json_decode(file_get_contents($lockFile), true, 512, JSON_THROW_ON_ERROR);
$lockedPackages = [];

foreach (array_merge($lockPayload['packages'] ?? [], $lockPayload['packages-dev'] ?? []) as $package) {
    if (isset($package['name'], $package['version']) && is_string($package['name']) && is_string($package['version'])) {
        $lockedPackages[$package['name']] = $package;
    }
}

$targets = file($targetsFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);

if ($targets === false) {
    fwrite(STDERR, "❌ Could not read bumped package targets\n");
    exit(1);
}

foreach ($targets as $targetLine) {
    [$packageName, $targetVersion] = array_pad(explode("\t", $targetLine, 2), 2, '');

    if ($packageName === '' || $targetVersion === '') {
        fwrite(STDERR, "❌ Invalid bumped package target entry: {$targetLine}\n");
        exit(1);
    }

    $lockedPackage = $lockedPackages[$packageName] ?? null;

    if ($lockedPackage === null) {
        fwrite(STDERR, "❌ Could not determine locked version for {$packageName}\n");
        exit(1);
    }

    $lockedVersion = $lockedPackage['version'];

    if (! versionMatchesTarget($lockedPackage, $targetVersion)) {
        fwrite(STDERR, "❌ {$packageName} locked to {$lockedVersion} but expected {$targetVersion}\n");
        exit(1);
    }

    fwrite(STDOUT, "  ✓ {$packageName} locked to {$lockedVersion} (target: {$targetVersion})\n");
}

function versionMatchesTarget(array $lockedPackage, string $targetVersion): bool
{
    $lockedVersion = $lockedPackage['version'] ?? '';
    $branchAliases = $lockedPackage['extra']['branch-alias'] ?? [];

    if (! is_array($branchAliases)) {
        $branchAliases = [];
    }

    if (str_starts_with($targetVersion, 'dev-')) {
        return $lockedVersion === $targetVersion;
    }

    if (str_ends_with($targetVersion, '-dev')) {
        if ($lockedVersion === $targetVersion) {
            return true;
        }

        return ($branchAliases[$lockedVersion] ?? null) === $targetVersion;
    }

    if (preg_match('/^\d+\.\d+\.x$/', $targetVersion) === 1) {
        $releasePrefix = substr($targetVersion, 0, -1);
        $releaseAlias = "{$targetVersion}-dev";

        return $lockedVersion === $targetVersion
            || $lockedVersion === $releaseAlias
            || $lockedVersion === "dev-{$targetVersion}"
            || ($branchAliases[$lockedVersion] ?? null) === $releaseAlias
            || str_starts_with($lockedVersion, $releasePrefix);
    }

    return $lockedVersion === $targetVersion;
}
