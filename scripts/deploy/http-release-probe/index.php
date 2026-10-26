<?php
declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('X-Content-Type-Options: nosniff');

$probeConfig = require __DIR__ . '/probe-config.php';
if (!is_array($probeConfig) || !preg_match('/\Aionos-http-probe-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}\z/', $probeConfig['run_id'] ?? '')) {
    http_response_code(503);
    echo json_encode(['error' => 'probe-config-invalid']);
    exit;
}

$requestId = $_GET['rid'] ?? '';
$holdMs = filter_var($_GET['hold_ms'] ?? '0', FILTER_VALIDATE_INT);
if (!is_string($requestId) || !preg_match('/\A[a-f0-9]{32}\z/', $requestId)
    || $holdMs === false || $holdMs < 0 || $holdMs > 2000) {
    http_response_code(400);
    echo json_encode(['error' => 'invalid-test-input']);
    exit;
}

$runRoot = dirname(__DIR__);
$releasesRoot = $runRoot . '/releases';
$releaseRoot = realpath($releasesRoot . '/current');
$allowedA = realpath($releasesRoot . '/release-A');
$allowedB = realpath($releasesRoot . '/release-B');
if ($releaseRoot === false || !in_array($releaseRoot, [$allowedA, $allowedB], true)
    || is_link($releasesRoot . '/release-A') || is_link($releasesRoot . '/release-B')) {
    http_response_code(503);
    echo json_encode(['error' => 'release-pointer-invalid']);
    exit;
}

// Risolve il puntatore una sola volta: tutte le letture di questa richiesta
// usano il path canonico immutabile della stessa release.
$release = basename($releaseRoot);
$componentPaths = [
    'theme' => $releaseRoot . '/theme/release.php',
    'plugin' => $releaseRoot . '/plugin/release.php',
    'mu_plugin' => $releaseRoot . '/mu-plugin/release.php',
    'asset' => $releaseRoot . '/assets/asset.txt',
];
foreach (['theme', 'plugin', 'mu-plugin', 'assets'] as $component) {
    $directory = $releaseRoot . '/' . $component;
    if (is_link($directory) || !is_dir($directory)) {
        http_response_code(503);
        echo json_encode(['error' => 'release-component-directory-invalid']);
        exit;
    }
}
foreach ($componentPaths as $path) {
    $canonical = realpath($path);
    if ($canonical === false || is_link($path) || !is_file($path)
        || strncmp($canonical, $releaseRoot . DIRECTORY_SEPARATOR,
            strlen($releaseRoot . DIRECTORY_SEPARATOR)) !== 0) {
        http_response_code(503);
        echo json_encode(['error' => 'release-component-path-invalid']);
        exit;
    }
}
$theme = require $releaseRoot . '/theme/release.php';
if ($holdMs > 0) {
    usleep($holdMs * 1000);
}
$plugin = require $releaseRoot . '/plugin/release.php';
$muPlugin = require $releaseRoot . '/mu-plugin/release.php';
$assetPath = $componentPaths['asset'];
$asset = is_file($assetPath) ? trim((string) file_get_contents($assetPath)) : '';

if ($theme !== $release || $plugin !== $release || $muPlugin !== $release || $asset !== 'asset-' . $release) {
    http_response_code(500);
    echo json_encode(['error' => 'fixture-release-content-mismatch', 'request_id' => $requestId]);
    exit;
}

$opcache = function_exists('opcache_get_status') ? @opcache_get_status(false) : false;
$opcacheEnabled = is_array($opcache) && ($opcache['opcache_enabled'] ?? false) === true;
echo json_encode([
    'probe_run_id' => $probeConfig['run_id'],
    'request_id' => $requestId,
    'release' => $release,
    'components' => [
        'theme' => $theme,
        'plugin' => $plugin,
        'mu_plugin' => $muPlugin,
        'asset' => $asset,
    ],
    'asset_url' => '/asset.php?release=' . rawurlencode($release),
    'runtime' => [
        'php_version' => PHP_VERSION,
        'sapi' => PHP_SAPI,
        'open_basedir_set' => ini_get('open_basedir') !== '',
        'opcache_enabled' => $opcacheEnabled,
        'opcache_validate_timestamps' => ini_get('opcache.validate_timestamps'),
        'opcache_revalidate_freq' => ini_get('opcache.revalidate_freq'),
        'realpath_cache_ttl' => ini_get('realpath_cache_ttl'),
    ],
], JSON_UNESCAPED_SLASHES);
