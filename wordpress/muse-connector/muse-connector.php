<?php
/**
 * Plugin Name: MUSE Connector
 * Description: Fixed merchant context and explicitly authorized owned-resource operations.
 * Version: 0.3.0
 */
defined('ABSPATH') || exit;
require_once __DIR__ . '/includes/permissions.php';
require_once __DIR__ . '/includes/store-setup.php';
require_once __DIR__ . '/includes/shipping.php';
require_once __DIR__ . '/includes/snapshot.php';
require_once __DIR__ . '/includes/protocol.php';
require_once __DIR__ . '/includes/receipts.php';
require_once __DIR__ . '/includes/operations.php';
require_once __DIR__ . '/includes/products.php';
require_once __DIR__ . '/includes/theme-deploy.php';
require_once __DIR__ . '/includes/navigation.php';
require_once __DIR__ . '/includes/pages.php';
require_once __DIR__ . '/includes/media.php';
add_action('application_password_did_authenticate', function ($user, $item) {
    $GLOBALS['muse_application_password_authenticated'] = true;
}, 10, 2);
add_action('init', 'muse_connector_install_receipts');
add_action('init', 'muse_connector_register_service_role');
add_action('admin_menu', 'muse_connector_store_setup_menu');
add_action('admin_post_muse_confirm_store_setup', 'muse_connector_save_store_setup');
add_filter('woocommerce_package_rates', 'muse_connector_owned_shipping_rates', 100);
add_action('rest_api_init', function () {
    foreach (array('snapshot' => 'muse_connector_snapshot', 'capabilities' => 'muse_connector_capabilities') as $name => $callback) {
        register_rest_route('muse/v1', '/' . $name, array(
            'methods' => 'GET', 'permission_callback' => 'muse_connector_read_permission', 'callback' => $callback,
        ));
    }
    register_rest_route('muse/v1', '/operations', array('methods' => 'POST',
        'permission_callback' => 'muse_connector_write_permission', 'callback' => 'muse_connector_operation_route'));
    register_rest_route('muse/v1', '/receipts/(?P<operation_id>[a-zA-Z0-9_-]{1,100})', array('methods' => 'GET',
        'permission_callback' => 'muse_connector_write_permission', 'callback' => 'muse_connector_receipt_route'));
    register_rest_route('muse/v1', '/resources', array('methods' => 'GET',
        'permission_callback' => 'muse_connector_read_permission', 'callback' => 'muse_connector_resource_route'));
});
