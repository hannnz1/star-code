<?php
$input = json_decode(stream_get_contents(STDIN), true, 32, JSON_THROW_ON_ERROR);
require $argv[1] . '/wp-load.php';
if ($input['action'] === 'materialize_header') {
    echo json_encode(array('content' => muse_connector_materialize_header_navigation($input['content'], $input['navigation_id'])));
} elseif ($input['action'] === 'store_setup') {
    $old = array();
    foreach (array('muse_shipping_confirmed', 'muse_payment_confirmed', 'woocommerce_cod_settings') as $key) {
        $old[$key] = get_option($key, null);
    }
    if (isset($input['restore'])) {
        foreach ($input['restore'] as $key => $value) {
            if (!array_key_exists($key, $old)) { throw new RuntimeException('Unknown fixture option'); }
            if ($value === null) { delete_option($key); } else { update_option($key, $value); }
        }
    } else {
        $admin = get_user_by('login', 'fixture_admin'); wp_set_current_user($admin->ID);
        $_POST = array('shipping_confirmed' => $input['confirmed'] ? 'yes' : 'no',
                      'payment_confirmed' => $input['confirmed'] ? 'yes' : 'no');
        $_REQUEST['_wpnonce'] = wp_create_nonce('muse_confirm_store_setup');
        muse_connector_save_store_setup();
        if (!empty($input['disable_payment'])) {
            $settings = get_option('woocommerce_cod_settings', array()); $settings['enabled'] = 'no';
            update_option('woocommerce_cod_settings', $settings);
        }
    }
    echo json_encode(array('old' => $old));
} elseif ($input['action'] === 'create_page') {
    $id = wp_insert_post(array('post_type' => 'page', 'post_status' => 'draft',
        'post_title' => 'Fixture page', 'post_content' => 'Before'), true);
    if (is_wp_error($id)) { throw new RuntimeException($id->get_error_code()); }
    if ($input['owned']) { update_post_meta($id, '_muse_project_id', 'project'); }
    echo json_encode(array('id' => $id));
} elseif ($input['action'] === 'edit_page') {
    $result = wp_update_post(array('ID' => $input['id'], 'post_content' => $input['content']), true);
    if (is_wp_error($result)) { throw new RuntimeException($result->get_error_code()); }
    echo json_encode(array('id' => $result));
} elseif ($input['action'] === 'edit_css') {
    $path = get_theme_file_path('assets/storefront.css');
    $old = file_get_contents($path);
    file_put_contents($path, $input['content'] ?? ($old . "\n/* Merchant edit */\n"));
    echo json_encode(array('old' => $old));
} elseif ($input['action'] === 'product_version_probe') {
    if (empty($input['id'])) {
        $product = new WC_Product_Simple();
        $product->set_name('Fixture version probe'); $product->set_sku($input['sku']); $product->set_status('draft');
        $product->set_regular_price('10.00'); $product->set_manage_stock(true); $product->set_stock_quantity(3);
        $product->update_meta_data('_muse_project_id', 'project');
    } else {
        $product = wc_get_product($input['id']);
        if (!$product) { throw new RuntimeException('Fixture product missing.'); }
        $product->set_regular_price('15.00'); $product->set_sale_price('10.00'); $product->set_price('10.00');
        $product->set_manage_stock(false);
        $term = wp_insert_term('Fixture category ' . $product->get_sku(), 'product_cat');
        if (is_wp_error($term)) { throw new RuntimeException('Fixture category failed.'); }
        $product->set_category_ids(array((int) $term['term_id']));
    }
    echo json_encode(array('id' => $product->save()));
} elseif ($input['action'] === 'rename_category') {
    $result = wp_update_term($input['id'], 'product_cat', array('name' => $input['name']));
    if (is_wp_error($result)) { throw new RuntimeException('Fixture category failed.'); }
    echo json_encode(array('id' => (int) $result['term_id']));
 } elseif ($input['action'] === 'buyer_probe_fixture') {
    $keys = array('blog_public', 'woocommerce_cod_settings', 'woocommerce_bacs_settings',
        'woocommerce_cheque_settings', 'woocommerce_paypal_settings');
    $old = array(); foreach ($keys as $key) { $old[$key] = get_option($key, null); }
    if (isset($input['restore'])) {
        foreach ($input['restore'] as $key => $value) {
            if (!in_array($key, $keys, true)) { throw new RuntimeException('Unknown fixture option'); }
            if ($value === null) { delete_option($key); } else { update_option($key, $value); }
        }
        echo json_encode(array('restored' => true));
    } else {
        update_option('blog_public', 0);
        foreach (WC()->payment_gateways()->payment_gateways() as $id => $gateway) {
            $key = 'woocommerce_' . $id . '_settings';
            if (!in_array($key, $keys, true)) { throw new RuntimeException('Unknown installed gateway'); }
            $settings = get_option($key, array()); $settings['enabled'] = $id === 'cod' ? 'yes' : 'no';
            update_option($key, $settings);
        }
        $product = new WC_Product_Simple(); $product->set_name('Disposable buyer probe');
        $product->set_sku($input['sku']); $product->set_regular_price('12.50'); $product->set_status('publish');
        $product->set_manage_stock(true); $product->set_stock_quantity(3); $product->set_virtual(false);
        $product->update_meta_data('_muse_project_id', 'project');
        echo json_encode(array('id' => $product->save(), 'old' => $old));
    }
} elseif ($input['action'] === 'offline_checkout') {
    update_option('woocommerce_coming_soon', 'no'); update_option('woocommerce_store_pages_only', 'no');
    update_option('woocommerce_cod_settings', array('enabled' => 'yes', 'title' => 'Disposable offline payment',
        'description' => 'No real payment', 'enable_for_virtual' => 'yes', 'enable_for_methods' => array()));
    update_option('woocommerce_default_country', 'US:CA');
    update_option('woocommerce_store_address', '1 Fixture Street'); update_option('woocommerce_store_city', 'Beverly Hills');
    update_option('woocommerce_store_postcode', '90210'); update_option('woocommerce_calc_taxes', 'no');
    update_option('woocommerce_default_customer_address', 'base'); update_option('woocommerce_shipping_cost_requires_address', 'no');
    $zone = WC_Shipping_Zones::get_zone_by('zone_id', 0);
    $methods = $zone->get_shipping_methods();
    $instance = null;
    foreach ($methods as $method) { if ($method->id === 'flat_rate') { $instance = $method->instance_id; break; } }
    if (!$instance) { $instance = $zone->add_shipping_method('flat_rate'); }
    update_option('woocommerce_flat_rate_' . $instance . '_settings', array('enabled' => 'yes', 'title' => 'Fixture shipping', 'cost' => '5', 'tax_status' => 'none'));
    echo json_encode(array('ready' => true));
} else { throw new RuntimeException('Unknown fixture action.'); }
