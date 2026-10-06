<?php
/** Exact fixed-file readback. Never reads credentials/configuration files. */
ini_set('display_errors', '0'); ini_set('log_errors', '0');
try {
    $raw = stream_get_contents(STDIN, 2097153);
    if (strlen($raw) > 2097152) { throw new RuntimeException(); }
    $manifest = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    $root = realpath($argv[1] ?? '');
    if (!$root || !is_array($manifest) || !array_is_list($manifest) || count($manifest) < 1 || count($manifest) > 10030) { throw new RuntimeException(); }
    $seen = array(); $result = array(); $total = 0;
    foreach ($manifest as $file) {
        if (!is_array($file) || count($file) !== 3 || !isset($file['path'], $file['sha256'], $file['byte_size']) ||
            !is_string($file['path']) || !is_string($file['sha256']) || !preg_match('/^[a-f0-9]{64}$/D', $file['sha256']) ||
            !is_int($file['byte_size']) || $file['byte_size'] < 0 || $file['byte_size'] > 16777216 ||
            !preg_match('#^wp-content/(?:plugins/(?:woocommerce|muse-connector)/[a-zA-Z0-9_.,@\-/]+|themes/muse-storefront/[a-zA-Z0-9_.\-/]+|mu-plugins/muse-staging-safety\.php)$#D', $file['path'])) { throw new RuntimeException(); }
        $parts = explode('/', $file['path']); $candidate = $root;
        foreach ($parts as $part) {
            if ($part === '' || $part === '.' || $part === '..') { throw new RuntimeException(); }
            $candidate .= DIRECTORY_SEPARATOR . $part;
            if (is_link($candidate)) { throw new RuntimeException(); }
        }
        $canonical = strtolower($file['path']);
        if (isset($seen[$canonical]) || !is_file($candidate)) { throw new RuntimeException(); }
        $seen[$canonical] = true; $size = filesize($candidate); $total += $size;
        if ($size !== $file['byte_size'] || $total > 134217728 || hash_file('sha256', $candidate) !== $file['sha256']) { throw new RuntimeException(); }
        $result[] = $file;
    }
    echo json_encode($result, JSON_THROW_ON_ERROR);
} catch (Throwable $error) { fwrite(STDERR, "REFERENCE_ASSET_READBACK_REJECTED\n"); exit(2); }
