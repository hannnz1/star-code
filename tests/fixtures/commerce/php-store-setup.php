<?php
define('ABSPATH', __DIR__);
$input = json_decode(stream_get_contents(STDIN), true, 32, JSON_THROW_ON_ERROR);
$saved = array();
function current_user_can($cap) { global $input; return $cap === 'manage_options' && $input['admin']; }
function check_admin_referer($name) { global $input; if (!$input['nonce']) { throw new RuntimeException('nonce'); } }
function wp_die($message) { throw new RuntimeException('denied'); }
function update_option($name, $value) { global $saved; $saved[$name] = $value; }
function get_option($name, $default = false) { global $input; return $input['options'][$name] ?? $default; }
function wp_safe_redirect($url) {}
function admin_url($path) { return '/wp-admin/' . $path; }
function WC() { return new FixtureWoo(); }
class FixtureWoo { function payment_gateways() { return new FixtureGateways(); } }
// WooCommerce exposes all configured gateways via payment_gateways()->payment_gateways().
class FixtureGateways { function payment_gateways() { global $input; return array((object) array('enabled' => $input['payment'] ? 'yes' : 'no')); } }
class WC_Shipping_Zones { static function get_zones() { return array(array('zone_id' => 7)); }
    static function get_zone($id) { return new FixtureZone(); } }
class FixtureZone { function get_shipping_methods($enabled_only = false) { global $input; return $input['shipping'] ? array((object) array('enabled' => 'yes')) : array(); } }
require $argv[1];
if ($input['mode'] === 'save') {
    $_POST = $input['post'];
    try { muse_connector_save_store_setup(); } catch (RuntimeException $e) { echo json_encode(array('error' => $e->getMessage(), 'saved' => $saved)); exit; }
    echo json_encode(array('saved' => $saved));
} else { echo json_encode(muse_connector_store_setup_state()); }
