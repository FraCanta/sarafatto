<?php
declare(strict_types=1);

header('Content-Type: text/plain; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('X-Content-Type-Options: nosniff');
$probeConfig = require __DIR__ . '/probe-config.php';
if (!is_array($probeConfig) || !preg_match('/\Aionos-http-probe-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{12}\z/', $probeConfig['run_id'] ?? '')) {
    http_response_code(503);
    exit;
}
header('X-SF-Probe-Run-ID: ' . $probeConfig['run_id']);

$release = $_GET['release'] ?? '';
if (!is_string($release) || !in_array($release, ['release-A', 'release-B'], true)) {
    http_response_code(400);
    exit;
}

$path = dirname(__DIR__) . '/releases/' . $release . '/assets/asset.txt';
$releasePath = dirname(__DIR__) . '/releases/' . $release;
$assetsPath = $releasePath . '/assets';
$expectedRoot = realpath($releasePath);
$actualPath = realpath($path);
if ($expectedRoot === false || $actualPath !== $expectedRoot . '/assets/asset.txt'
    || is_link($releasePath) || is_link($assetsPath)
    || !is_file($path) || is_link($path)) {
    http_response_code(404);
    exit;
}

readfile($path);
