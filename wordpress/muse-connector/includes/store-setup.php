<?php
defined('ABSPATH') || exit;

/** Human acknowledgement plus current configuration, never a checkout verification. */
function muse_connector_store_setup_state() {
    $shipping = false; $payment = false;
    if (class_exists('WC_Shipping_Zones')) {
        $ids = array(0);
        foreach (WC_Shipping_Zones::get_zones() as $zone) { $ids[] = (int) $zone['zone_id']; }
        foreach ($ids as $id) {
            $zone = WC_Shipping_Zones::get_zone($id);
            if ($zone && count($zone->get_shipping_methods(true)) > 0) { $shipping = true; break; }
        }
    }
    if (function_exists('WC') && WC()->payment_gateways()) {
        foreach (WC()->payment_gateways()->payment_gateways() as $gateway) {
            if ($gateway->enabled === 'yes') { $payment = true; break; }
        }
    }
    return array('shipping_confirmed' => $shipping && get_option('muse_shipping_confirmed', 'no') === 'yes',
                 'payment_confirmed' => $payment && get_option('muse_payment_confirmed', 'no') === 'yes');
}

function muse_connector_save_store_setup() {
    if (!current_user_can('manage_options')) { wp_die('Store administrator required.'); }
    check_admin_referer('muse_confirm_store_setup');
    foreach (array('shipping', 'payment') as $kind) {
        $value = $_POST[$kind . '_confirmed'] ?? null;
        update_option('muse_' . $kind . '_confirmed', is_string($value) && $value === 'yes' ? 'yes' : 'no');
    }
    wp_safe_redirect(admin_url('admin.php?page=muse-connector&saved=1'));
}

function muse_connector_store_setup_menu() {
    add_options_page('MUSE 店铺准备', 'MUSE 店铺准备', 'manage_options', 'muse-connector', 'muse_connector_store_setup_page');
}

function muse_connector_store_setup_page() {
    if (!current_user_can('manage_options')) { wp_die('Store administrator required.'); }
    $state = muse_connector_store_setup_state();
    echo '<div class="wrap"><h1>MUSE 店铺准备</h1><p>请先在 WooCommerce 配置运输和付款，再由商家确认。此确认不代表购买流程验证通过，也不是发布批准。</p>';
    echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
    echo '<input type="hidden" name="action" value="muse_confirm_store_setup">';
    wp_nonce_field('muse_confirm_store_setup');
    foreach (array('shipping' => '我已配置并检查运输地区、方式与费用', 'payment' => '我已配置并检查付款方式') as $kind => $label) {
        echo '<p><label><input type="checkbox" name="' . esc_attr($kind . '_confirmed') . '" value="yes" ';
        checked(get_option('muse_' . $kind . '_confirmed', 'no'), 'yes');
        echo '> ' . esc_html($label) . '</label> — 当前准备状态：' . ($state[$kind . '_confirmed'] ? '已确认且有启用方式' : '尚未就绪') . '</p>';
    }
    submit_button('保存商家确认');
    echo '</form></div>';
}
