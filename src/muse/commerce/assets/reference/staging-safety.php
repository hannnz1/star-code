<?php
/** Fixed MUSE staging guard. Never install on a merchant live site. */
defined('ABSPATH') || exit;
if (defined('MUSE_ENVIRONMENT') && MUSE_ENVIRONMENT === 'staging' &&
    defined('MUSE_REFERENCE_JOB') && preg_match('/^[a-f0-9]{32}$/D', MUSE_REFERENCE_JOB)) {

function muse_staging_mail_block($result, $attributes) { return true; }
function muse_staging_http_block($result, $arguments, $url) {
    return new WP_Error('muse_staging_network_disabled', 'External service requests are disabled in this staging job.');
}
function muse_staging_gateways($gateways) { return isset($gateways['cod']) ? array('cod' => $gateways['cod']) : array(); }
function muse_staging_robots($robots) { return array('noindex' => true, 'nofollow' => true); }
function muse_staging_application_passwords($available) { return true; }
function muse_staging_cod_status($status, $order) { return 'on-hold'; }
add_filter('pre_wp_mail', 'muse_staging_mail_block', PHP_INT_MAX, 2);
add_filter('pre_http_request', 'muse_staging_http_block', PHP_INT_MAX, 3);
add_filter('woocommerce_available_payment_gateways', 'muse_staging_gateways', PHP_INT_MAX);
add_filter('wp_robots', 'muse_staging_robots', PHP_INT_MAX);
add_filter('wp_is_application_passwords_available', 'muse_staging_application_passwords', PHP_INT_MAX);
add_filter('woocommerce_cod_process_payment_order_status', 'muse_staging_cod_status', PHP_INT_MAX, 2);

function muse_staging_safety_state() {
    $gateways = WC()->payment_gateways()->payment_gateways(); $enabled = array();
    foreach ($gateways as $id => $gateway) { if ($gateway->enabled === 'yes') { $enabled[] = $id; } }
    sort($enabled);
    $mail = apply_filters('pre_wp_mail', null, array());
    $http = apply_filters('pre_http_request', false, array(), 'https://example.invalid');
    return array('job_id' => MUSE_REFERENCE_JOB, 'environment' => MUSE_ENVIRONMENT,
        'email_disabled' => $mail === true, 'external_requests_disabled' => is_wp_error($http),
        'indexing_disabled' => (int) get_option('blog_public') === 0,
        'cron_disabled' => defined('DISABLE_WP_CRON') && DISABLE_WP_CRON,
        'offline_gateway_only' => $enabled === array('cod'),
        'wordpress_version' => get_bloginfo('version'), 'woocommerce_version' => WC_VERSION);
}
function muse_staging_probe_item($order) {
    $items = array_values($order->get_items('line_item'));
    if (count($items) !== 1 || (float) $items[0]->get_quantity() !== 1.0 || (int) $items[0]->get_variation_id() !== 0) {
        throw new RuntimeException('MUSE_PROBE_REJECTED');
    }
    $product = $items[0]->get_product();
    if (!$product) { throw new RuntimeException('MUSE_PROBE_REJECTED'); }
    return array('product_id' => (int) $items[0]->get_product_id(), 'sku' => $product->get_sku());
}
function muse_staging_probe_tag($order, $request) {
    $payload = $request->get_header('x-muse-probe');
    if ($payload === '') { return; } // Ordinary staging checkouts are not probe evidence.
    $signature = $request->get_header('x-muse-probe-signature');
    if (!is_string($payload) || strlen($payload) > 4096 || !is_string($signature) ||
        !preg_match('/^[a-f0-9]{64}$/D', $signature) || !defined('MUSE_EXECUTION_SECRET') ||
        !hash_equals(hash_hmac('sha256', $payload, MUSE_EXECUTION_SECRET), $signature)) {
        throw new RuntimeException('MUSE_PROBE_REJECTED');
    }
    $bytes = base64_decode($payload, true);
    $source = $bytes === false ? null : json_decode($bytes, true);
    $keys = is_array($source) ? array_keys($source) : array(); sort($keys);
    $expected = array('job_id', 'probe_id', 'source_digest', 'staging_intent_digest', 'product_id', 'sku'); sort($expected);
    if ($keys !== $expected || $source['job_id'] !== MUSE_REFERENCE_JOB ||
        !is_int($source['product_id']) || $source['product_id'] <= 0 || !is_string($source['sku']) ||
        strlen($source['sku']) < 1 || strlen($source['sku']) > 400 || $order->get_payment_method() !== 'cod') {
        throw new RuntimeException('MUSE_PROBE_REJECTED');
    }
    foreach (array('probe_id', 'source_digest', 'staging_intent_digest') as $key) {
        if (!is_string($source[$key]) || !preg_match('/^[a-f0-9]{64}$/D', $source[$key])) {
            throw new RuntimeException('MUSE_PROBE_REJECTED');
        }
    }
    $item = muse_staging_probe_item($order);
    if ($item['product_id'] !== $source['product_id'] || $item['sku'] !== $source['sku']) {
        throw new RuntimeException('MUSE_PROBE_REJECTED');
    }
    $prior = wc_get_orders(array('limit' => 2, 'meta_key' => '_muse_probe_id', 'meta_value' => $source['probe_id']));
    foreach ($prior as $existing) {
        if ($existing->get_id() !== $order->get_id()) { throw new RuntimeException('MUSE_PROBE_REJECTED'); }
    }
    foreach ($source as $key => $value) { $order->update_meta_data('_muse_' . $key, $value); }
    $order->update_meta_data('_muse_probe_signature', $signature);
    $order->update_meta_data('_muse_probe_payload', $payload);
}
/** Only an authenticated synthetic order on this owned disposable job is exempt.
 * Merchant and ordinary staging orders keep WooCommerce stock semantics.
 */
function muse_staging_probe_reduce_stock($allowed, $order) {
    if (!is_object($order) || !method_exists($order, 'get_meta') || !defined('MUSE_EXECUTION_SECRET')) { return $allowed; }
    $payload = $order->get_meta('_muse_probe_payload');
    $signature = $order->get_meta('_muse_probe_signature');
    if (!is_string($payload) || strlen($payload) > 4096 || !is_string($signature) ||
        !preg_match('/^[a-f0-9]{64}$/D', $signature) ||
        !hash_equals(hash_hmac('sha256', $payload, MUSE_EXECUTION_SECRET), $signature)) { return $allowed; }
    $bytes = base64_decode($payload, true);
    $source = $bytes === false ? null : json_decode($bytes, true);
    if (!is_array($source) || ($source['job_id'] ?? '') !== MUSE_REFERENCE_JOB ||
        $order->get_payment_method() !== 'cod') { return $allowed; }
    foreach (array('job_id', 'probe_id', 'source_digest', 'staging_intent_digest', 'product_id', 'sku') as $key) {
        if (!array_key_exists($key, $source) || (string) $order->get_meta('_muse_' . $key) !== (string) $source[$key]) { return $allowed; }
    }
    try { $item = muse_staging_probe_item($order); }
    catch (Throwable $error) { return $allowed; }
    if ($item['product_id'] !== $source['product_id'] || $item['sku'] !== $source['sku']) { return $allowed; }
    return false;
}
add_filter('woocommerce_can_reduce_order_stock', 'muse_staging_probe_reduce_stock', PHP_INT_MAX, 2);
add_action('woocommerce_store_api_checkout_update_order_from_request', 'muse_staging_probe_tag', PHP_INT_MAX, 2);
function muse_staging_probe_read($request) {
    $identity = $request->get_param('probe_id');
    if (!is_string($identity) || !preg_match('/^[a-f0-9]{64}$/D', $identity)) {
        return new WP_Error('muse_probe_invalid', 'Probe input invalid.');
    }
    $orders = wc_get_orders(array('limit' => 2, 'meta_key' => '_muse_probe_id', 'meta_value' => $identity));
    if (!$orders) { return array('state' => 'absent', 'probe_id' => $identity); }
    if (count($orders) !== 1) { return new WP_Error('muse_probe_conflict', 'Probe result conflict.'); }
    $order = $orders[0];
    if ($order->get_meta('_muse_job_id') !== MUSE_REFERENCE_JOB || $order->get_meta('_muse_probe_id') !== $identity ||
        $order->get_status() !== 'on-hold' || $order->get_payment_method() !== 'cod') {
        return new WP_Error('muse_probe_conflict', 'Probe result conflict.');
    }
    try { $item = muse_staging_probe_item($order); }
    catch (Throwable $error) { return new WP_Error('muse_probe_conflict', 'Probe result conflict.'); }
    if ($item['product_id'] !== (int) $order->get_meta('_muse_product_id') || $item['sku'] !== $order->get_meta('_muse_sku')) {
        return new WP_Error('muse_probe_conflict', 'Probe result conflict.');
    }
    // Deliberately excludes customer fields, session/order keys and addresses.
    return array_merge(array('state' => 'found', 'probe_id' => $identity, 'job_id' => MUSE_REFERENCE_JOB,
        'order_id' => $order->get_id(), 'status' => 'on-hold', 'payment_method' => 'cod', 'quantity' => 1,
        'currency' => $order->get_currency(),
        'item_subtotal' => (string) array_values($order->get_items('line_item'))[0]->get_subtotal(),
        'shipping_total' => (string) $order->get_shipping_total(), 'tax_total' => (string) $order->get_total_tax(),
        'order_total' => (string) $order->get_total(),
        'source_digest' => $order->get_meta('_muse_source_digest'),
        'staging_intent_digest' => $order->get_meta('_muse_staging_intent_digest')), $item);
}
/** Bootstrap-only creation; never expose a product creation REST command. */
function muse_staging_fixture_create() {
    $sku = 'MUSE-PROBE-' . MUSE_REFERENCE_JOB;
    if (!defined('MUSE_PROJECT_ID') || !defined('MUSE_CONNECTION_ID') ||
        MUSE_CONNECTION_ID !== 'ref-' . MUSE_REFERENCE_JOB || wc_get_product_id_by_sku($sku)) { throw new RuntimeException(); }
    $product = new WC_Product_Simple();
    $product->set_name('MUSE disposable purchase probe');
    $product->set_sku($sku); $product->set_regular_price('12.50');
    $product->set_manage_stock(true); $product->set_stock_quantity(3);
    $product->set_status('publish'); $product->set_catalog_visibility('hidden');
    $product->set_virtual(false); $product->set_tax_status('none');
    $product->update_meta_data('_muse_fixture_job', MUSE_REFERENCE_JOB);
    $product->update_meta_data('_muse_fixture_project', MUSE_PROJECT_ID);
    $id = $product->save();
    if (!is_int($id) || $id < 1) { throw new RuntimeException(); }
    update_option('muse_disposable_product_id', $id, false);
    return $id;
}
function muse_staging_fixture_read() {
    $id = get_option('muse_disposable_product_id');
    if (!defined('MUSE_PROJECT_ID') || !defined('MUSE_CONNECTION_ID') ||
        MUSE_CONNECTION_ID !== 'ref-' . MUSE_REFERENCE_JOB || !is_numeric($id) || (int) $id < 1) {
        return new WP_Error('muse_fixture_invalid', 'Disposable product unavailable.');
    }
    $product = wc_get_product((int) $id);
    if (!$product || $product->get_type() !== 'simple' || $product->get_sku() !== 'MUSE-PROBE-' . MUSE_REFERENCE_JOB ||
        $product->get_meta('_muse_fixture_job') !== MUSE_REFERENCE_JOB ||
        $product->get_meta('_muse_fixture_project') !== MUSE_PROJECT_ID ||
        $product->get_name() !== 'MUSE disposable purchase probe' || $product->get_status() !== 'publish' ||
        $product->get_catalog_visibility() !== 'hidden' || !$product->get_manage_stock() ||
        $product->get_stock_quantity() !== 3 || $product->is_virtual() || $product->get_tax_status() !== 'none' ||
        wc_format_decimal($product->get_price(), 2) !== '12.50') {
        return new WP_Error('muse_fixture_invalid', 'Disposable product unavailable.');
    }
    return array('job_id' => MUSE_REFERENCE_JOB, 'project_id' => MUSE_PROJECT_ID,
        'connection_id' => MUSE_CONNECTION_ID, 'product_id' => (int) $id, 'sku' => $product->get_sku(),
        'title' => $product->get_name(), 'price' => '12.50', 'currency' => get_woocommerce_currency(),
        'stock_quantity' => 3, 'status' => 'publish', 'catalog_visibility' => 'hidden', 'fixture_only' => true);
}
add_action('rest_api_init', function () {
    register_rest_route('muse-staging/v1', '/disposable-product', array('methods' => 'GET',
        'permission_callback' => 'muse_connector_read_permission', 'callback' => 'muse_staging_fixture_read'));
    register_rest_route('muse-staging/v1', '/safety', array('methods' => 'GET',
        'permission_callback' => 'muse_connector_read_permission', 'callback' => 'muse_staging_safety_state'));
    register_rest_route('muse-staging/v1', '/probe-order', array('methods' => 'GET',
        'permission_callback' => 'muse_connector_read_permission', 'callback' => 'muse_staging_probe_read'));
});
}
