<?php
defined('ABSPATH') || exit;
/** This role deliberately has no native CMS or WooCommerce write capabilities. */
function muse_connector_register_service_role() {
    $caps = array('read' => true, 'muse_read_context' => true, 'muse_execute_owned' => true);
    if (!get_role('muse_connector_service')) {
        add_role('muse_connector_service', 'MUSE Connector Service', $caps);
    }
}

function muse_connector_service_identity() {
    if (!defined('MUSE_SERVICE_USER_ID') || get_current_user_id() !== MUSE_SERVICE_USER_ID ||
        empty($GLOBALS['muse_application_password_authenticated'])) { return false; }
    $user = wp_get_current_user();
    foreach ($user->allcaps as $cap => $enabled) {
        if ($enabled && !in_array($cap, array('read', 'muse_read_context', 'muse_execute_owned', 'muse_connector_service'), true)) {
            return false;
        }
    }
    return current_user_can('muse_read_context');
}

function muse_connector_read_permission() {
    if (!is_user_logged_in()) {
        return new WP_Error('muse_auth_required', 'Authentication required.', array('status' => 401));
    }
    if (muse_connector_service_identity()) { return true; }
    // Existing human administrators can inspect context, but can never act as
    // the configured application service with broad native write permissions.
    if ((defined('MUSE_SERVICE_USER_ID') && get_current_user_id() === MUSE_SERVICE_USER_ID) ||
        !current_user_can('manage_options') || !current_user_can('manage_woocommerce')) {
        return new WP_Error('muse_permission_denied', 'Store context permission required.', array('status' => 403));
    }
    return true;
}
