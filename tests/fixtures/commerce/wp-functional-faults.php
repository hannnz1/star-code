<?php
/** Disposable test station only. Never ship this file in the Connector Plugin. */
defined('ABSPATH') || exit;
add_filter('pre_wp_mail', static function () { return true; });
add_action('muse_connector_media_file_written', function () {
    if (($_SERVER['HTTP_X_MUSE_TEST_FAULT'] ?? '') === 'exit-after-media') { exit; }
});
add_action('wp_after_insert_post', function ($id, $post) {
    if (($_SERVER['HTTP_X_MUSE_TEST_FAULT'] ?? '') === 'exit-after-page' && $post->post_type === 'page') {
        exit;
    }
}, 10, 2);
add_filter('query', function ($query) {
    if (($_SERVER['HTTP_X_MUSE_TEST_FAULT'] ?? '') === 'receipt-storage-failure' &&
        str_contains($query, 'muse_operation_receipts') && str_starts_with($query, 'UPDATE') && str_contains($query, 'SUCCEEDED')) {
        return 'MUSE deliberate disposable SQL fault';
    }
    return $query;
});
