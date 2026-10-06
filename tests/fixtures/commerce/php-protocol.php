<?php
define('ABSPATH', __DIR__);
require $argv[1];
$value = json_decode(stream_get_contents(STDIN), false, 64, JSON_THROW_ON_ERROR);
try {
    if ($value->mode === 'canonical') {
        echo json_encode(array('digest' => hash('sha256', muse_connector_canonical($value->data))));
    } elseif ($value->mode === 'category_seed') {
        require dirname($argv[1]) . '/products.php';
        muse_connector_validate_preview_category_seed($value->product,$value->claims);
        echo json_encode(array('accepted'=>true));
    } elseif ($value->mode === 'media') {
        define('MUSE_PROJECT_ID', $value->project_id);
        require dirname($argv[1]) . '/media.php';
        muse_connector_validate_media_operation($value->operation);
        echo json_encode(array('accepted' => true));
    } elseif ($value->mode === 'theme') {
        define('MUSE_PACKAGE_STORAGE', dirname(__DIR__, 3) . '/work/php-protocol-tmp');
        if (!is_dir(MUSE_PACKAGE_STORAGE)) { mkdir(MUSE_PACKAGE_STORAGE, 0700, true); }
        require dirname($argv[1]) . '/snapshot.php';
        require dirname($argv[1]) . '/theme-deploy.php';
        $files = muse_connector_validate_theme_package($value->payload);
        echo json_encode(array('accepted' => true, 'files' => count($files)));
    } elseif (in_array($value->mode, array('verify_dispatch', 'verify_identity_fingerprints'), true)) {
        $claims = muse_connector_verify_operation_authorization($value->token, $value->operation, $value->scope,
            base64_decode($value->secret, true), $value->now);
        if ($value->mode === 'verify_identity_fingerprints') {
            function muse_connector_sku_state($sku) { global $value; return $value->expected_states->$sku; }
            function muse_connector_snapshot() { return (object) array('settings' => (object) array(), 'theme_identity' => (object) array(), 'pages' => array(), 'products' => array()); }
            function is_wp_error($value) { return false; }
            function wp_json_encode($value) { return json_encode($value); }
            require dirname($argv[1]) . '/operations.php';
            foreach (get_object_vars($claims->identities) as $resource => $identity) {
                if (!isset($identity->sku)) { continue; }
                if (muse_connector_current_fingerprint($resource, $value->operation, $claims) !== $claims->preconditions->$resource) {
                    throw new InvalidArgumentException('Identity fingerprint differs.');
                }
            }
        }
        echo json_encode(array('accepted' => true, 'grant_id' => $claims->grant_id));
    } else {
        $claims = muse_connector_verify_execution($value->token, $value->operation, $value->scope,
                                                   base64_decode($value->secret, true), $value->now,
                                                   $value->mode === 'verify_retained' ? 6 : ($value->mode === 'verify_staging' ? 5 : ($value->mode === 'verify_v4' ? 4 : ($value->mode === 'verify_v3' ? 3 : ($value->mode === 'verify_v2' ? 2 : 1)))));
        echo json_encode(array('accepted' => true, 'grant_id' => $claims->grant_id));
    }
} catch (Throwable $error) {
    echo json_encode(array('accepted' => false));
}
