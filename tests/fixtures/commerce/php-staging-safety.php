<?php
define('ABSPATH', __DIR__);
$input = json_decode(stream_get_contents(STDIN), true, 32, JSON_THROW_ON_ERROR);
define('MUSE_ENVIRONMENT', $input['environment']);
define('MUSE_REFERENCE_JOB', $input['job']);
define('DISABLE_WP_CRON', true);
define('WC_VERSION', '11.1.2');
$filters = array();
function add_filter($name, $callback, $priority = 10, $arguments = 1) { global $filters; $filters[$name][] = $callback; }
function add_action($name, $callback) {}
function apply_filters($name, $value, ...$args) { global $filters; foreach ($filters[$name] ?? array() as $callback) { $value = $callback($value, ...$args); } return $value; }
class WP_Error { function __construct($code, $message) {} }
function is_wp_error($value) { return $value instanceof WP_Error; }
function get_option($name) { return 0; }
function get_bloginfo($name) { return '7.1.2'; }
function WC() { return new FixtureWoo(); }
class FixtureWoo { function payment_gateways() { return new FixtureGateways(); } }
class FixtureGateways { function payment_gateways() { global $input; $items = array('cod' => (object) array('enabled' => 'yes')); if (!empty($input['real_gateway'])) { $items['stripe'] = (object) array('enabled' => 'yes'); } return $items; } }
require $argv[1];
if (!function_exists('muse_staging_safety_state')) { echo json_encode(array('enabled' => false)); exit; }
$state = muse_staging_safety_state();
$state['cod_status'] = apply_filters('woocommerce_cod_process_payment_order_status', 'processing', null);
$state['gateways'] = array_keys(apply_filters('woocommerce_available_payment_gateways', WC()->payment_gateways()->payment_gateways()));
echo json_encode($state);
