<?php
$input = json_decode(stream_get_contents(STDIN), true, 32, JSON_THROW_ON_ERROR);
define('ABSPATH', __DIR__); define('MUSE_ENVIRONMENT', 'staging'); define('MUSE_REFERENCE_JOB', str_repeat('a', 32));
define('MUSE_EXECUTION_SECRET', 'unit-private-probe-signing-secret-0000');
function add_filter(...$args) {} function add_action(...$args) {}
class WP_Error { public $code; function __construct($code, $message = '') {$this->code = $code;} }
function wc_get_orders($args) { global $order; return empty($order->metadata['_muse_probe_id']) ? array() : array($order); }
class ProbeProduct { function get_sku() { global $input; return $input['sku'] ?? 'CUP'; } }
class ProbeItem { function get_subtotal() {return '12.50';} function get_product_id() {return 12;} function get_variation_id() {return 0;} function get_quantity() {global $input; return $input['quantity'] ?? 1;} function get_product() {return new ProbeProduct();} }
class ProbeOrder {
    public $metadata = array();
    function get_currency() {return 'USD';} function get_shipping_total() {return '5.00';}
    function get_total_tax() {return '0.00';} function get_total() {return '17.50';}
    function get_id() {return 25;} function get_status() {return 'on-hold';} function get_payment_method() {return 'cod';}
    function get_items($kind = '') {return array(new ProbeItem());}
    function update_meta_data($key, $value) {$this->metadata[$key] = $value;} function get_meta($key) {return $this->metadata[$key] ?? '';}
}
class ProbeRequest {
    function get_header($key) {global $input; return $input[$key] ?? '';}
    function get_param($key) {global $input; return $input[$key] ?? '';}
}
$order = new ProbeOrder();
require $argv[1];
if (!function_exists('muse_staging_probe_tag')) {echo json_encode(array('missing' => true)); exit;}
try {muse_staging_probe_tag($order, new ProbeRequest()); $result = muse_staging_probe_read(new ProbeRequest()); if (is_array($result)) { $result['stock_reduction'] = muse_staging_probe_reduce_stock(true, $order); $result['ordinary_stock_reduction'] = muse_staging_probe_reduce_stock(true, new ProbeOrder()); $order->metadata['_muse_probe_signature'] = str_repeat('0', 64); $result['forged_stock_reduction'] = muse_staging_probe_reduce_stock(true, $order); }
    echo json_encode($result instanceof WP_Error ? array('error' => $result->code) : $result);
} catch (Throwable $error) {echo json_encode(array('error' => 'REJECTED'));}
