<?php
defined('ABSPATH') || exit;

/** Fixed country-level rules only. No carrier, tax, fulfilment or external-zone writes. */
function muse_connector_validate_shipping_rules($rules) {
    muse_connector_exact_keys($rules, array('currency', 'zones'));
    if ($rules->currency !== get_woocommerce_currency() || wc_get_price_decimals() !== 2 || !is_array($rules->zones) || count($rules->zones) < 1 || count($rules->zones) > 10) {
        throw new InvalidArgumentException('Shipping currency or region limit differs.');
    }
    $countries = WC()->countries->get_countries(); $seen = array(); $keys = array();
    foreach ($rules->zones as $zone) {
        muse_connector_exact_keys($zone, array('key', 'name', 'countries', 'rate', 'free_from'));
        if (!is_string($zone->key) || preg_match('/\A[a-z][a-z0-9-]{0,39}\z/', $zone->key) !== 1 || isset($keys[$zone->key])) {
            throw new InvalidArgumentException('Invalid shipping region identity.');
        }
        $keys[$zone->key] = true; muse_connector_plain_text($zone->name, 100, true);
        if (trim($zone->name) === '' || !is_array($zone->countries) || count($zone->countries) < 1 || count($zone->countries) > 20) {
            throw new InvalidArgumentException('Invalid shipping region.');
        }
        $sorted = $zone->countries; sort($sorted, SORT_STRING);
        if ($sorted !== $zone->countries) { throw new InvalidArgumentException('Canonical country order required.'); }
        foreach ($zone->countries as $country) {
            if (!is_string($country) || !isset($countries[$country]) || isset($seen[$country])) { throw new InvalidArgumentException('Invalid or overlapping shipping country.'); }
            $seen[$country] = true;
        }
        foreach (array($zone->rate, $zone->free_from) as $i => $amount) {
            if ($i === 1 && $amount === null) { continue; }
            if (!is_string($amount) || preg_match('/\A[0-9]{1,8}\.[0-9]{2}\z/', $amount) !== 1) { throw new InvalidArgumentException('Exact shipping decimal required.'); }
        }
    }
}

function muse_connector_shipping_owner() {
    $owner = get_option('muse_owned_shipping', array('project_id' => MUSE_PROJECT_ID, 'zones' => array()));
    if (!is_array($owner) || array_keys($owner) !== array('project_id', 'zones') || $owner['project_id'] !== MUSE_PROJECT_ID || !is_array($owner['zones']) || count($owner['zones']) > 10) {
        throw new InvalidArgumentException('Shipping ownership is unavailable.');
    }
    return $owner;
}

function muse_connector_shipping_zone_state($id) {
    $zone = WC_Shipping_Zones::get_zone($id);
    if (!$zone || $zone->get_id() !== $id) { throw new InvalidArgumentException('Shipping zone missing.'); }
    $locations = array(); $methods = array();
    foreach ($zone->get_zone_locations() as $location) { $locations[] = array('type' => $location->type, 'code' => $location->code); }
    usort($locations, static function ($a, $b) { return strcmp($a['type'] . ':' . $a['code'], $b['type'] . ':' . $b['code']); });
    foreach ($zone->get_shipping_methods(false) as $method) {
        $instance = (int) $method->instance_id;
        $methods[] = array('instance_id' => $instance, 'method_id' => $method->id, 'enabled' => $method->enabled === 'yes',
            'settings' => (object) get_option('woocommerce_' . $method->id . '_' . $instance . '_settings', array()));
    }
    usort($methods, static function ($a, $b) { return $a['instance_id'] <=> $b['instance_id']; });
    return array('id' => $id, 'name' => $zone->get_zone_name(), 'locations' => $locations, 'order' => $zone->get_zone_order(), 'methods' => $methods);
}

function muse_connector_shipping_configuration() {
    $owner = muse_connector_shipping_owner(); $owned = array(); $rules = array(); $external = array(); $ids = array(0);
    foreach (WC_Shipping_Zones::get_zones() as $zone) { $ids[] = (int) $zone['zone_id']; }
    if (count($ids) > 101) { throw new InvalidArgumentException('Shipping context exceeds limit.'); }
    foreach ($owner['zones'] as $binding) {
        if (!is_array($binding) || array_keys($binding) !== array('key', 'id', 'methods') || !is_int($binding['id']) || $binding['id'] <= 0 || !in_array($binding['id'], $ids, true)) {
            throw new InvalidArgumentException('Owned shipping zone disappeared.');
        }
        $state = muse_connector_shipping_zone_state($binding['id']); $countries = array();
        foreach ($state['locations'] as $location) {
            if ($location['type'] !== 'country') { throw new InvalidArgumentException('Owned country scope changed.'); }
            $countries[] = $location['code'];
        }
        sort($countries, SORT_STRING); $actual_ids = array_column($state['methods'], 'instance_id'); $expected_ids = $binding['methods'];
        sort($actual_ids); sort($expected_ids);
        if ($actual_ids !== $expected_ids) { throw new InvalidArgumentException('Shipping method ownership changed.'); }
        usort($state['methods'], static function ($a, $b) { return strcmp($a['method_id'], $b['method_id']); });
        $flat = null; $free = null;
        foreach ($state['methods'] as $method) {
            if ($method['method_id'] === 'flat_rate' && $flat === null) { $flat = $method; }
            elseif ($method['method_id'] === 'free_shipping' && $free === null) { $free = $method; }
            else { throw new InvalidArgumentException('Unexpected owned shipping method.'); }
        }
        if (!$flat || !$flat['enabled'] || ($free && !$free['enabled'])) { throw new InvalidArgumentException('Owned shipping method disabled.'); }
        $owned[] = array('key' => $binding['key'], 'id' => $state['id'], 'name' => $state['name'], 'countries' => $countries, 'methods' => $state['methods']);
        $rules[] = (object) array('key' => $binding['key'], 'name' => $state['name'], 'countries' => $countries,
            'rate' => $flat['settings']->cost ?? '', 'free_from' => $free ? ($free['settings']->min_amount ?? '') : null);
    }
    $owned_ids = array_column($owned, 'id');
    foreach ($ids as $id) { if (!in_array($id, $owned_ids, true)) { $external[] = muse_connector_shipping_zone_state($id); } }
    usort($external, static function ($a, $b) { return $a['id'] <=> $b['id']; });
    $rule_set = $rules ? (object) array('currency' => get_woocommerce_currency(), 'zones' => $rules) : null;
    if ($rule_set) { muse_connector_validate_shipping_rules($rule_set); }
    return array('project_id' => MUSE_PROJECT_ID, 'rules' => $rule_set, 'zones' => $owned,
        'external_digest' => hash('sha256', muse_connector_canonical($external)));
}

function muse_connector_validate_shipping_operation($operation, $claims) {
    if (!in_array($claims->v, array(7, 8), true) || $operation->resource_key !== 'shipping:muse-storefront') { throw new InvalidArgumentException('Shipping authority required.'); }
    muse_connector_exact_keys($operation->payload, array('rules'));
    muse_connector_validate_shipping_rules($operation->payload->rules);
    $owner = muse_connector_shipping_owner(); muse_connector_shipping_configuration();
    $owned_ids = array_column($owner['zones'], 'id'); $requested = array();
    foreach ($operation->payload->rules->zones as $zone) { $requested = array_merge($requested, $zone->countries); }
    foreach (WC_Shipping_Zones::get_zones() as $record) {
        if (in_array((int) $record['zone_id'], $owned_ids, true)) { continue; }
        $zone = WC_Shipping_Zones::get_zone((int) $record['zone_id']);
        foreach ($zone->get_zone_locations() as $location) {
            // Complex merchant regions are left untouched and require platform-side review.
            if ($location->type !== 'country' || in_array($location->code, $requested, true)) {
                throw new InvalidArgumentException('Merchant shipping region conflicts with the requested scope.');
            }
        }
    }
}

function muse_connector_set_shipping($operation) {
    $owner = muse_connector_shipping_owner(); $old = array(); $next = array();
    foreach ($owner['zones'] as $binding) { $old[$binding['key']] = $binding; }
    foreach ($operation->payload->rules->zones as $index => $source) {
        $zone = isset($old[$source->key]) ? WC_Shipping_Zones::get_zone($old[$source->key]['id']) : new WC_Shipping_Zone();
        $zone->set_zone_name($source->name); $zone->set_zone_order(1000 + $index); $zone->clear_locations();
        foreach ($source->countries as $country) { $zone->add_location($country, 'country'); }
        if (!$zone->save()) { throw new RuntimeException('Shipping zone storage unavailable.'); }
        $existing = array(); foreach ($zone->get_shipping_methods(false) as $method) { $existing[$method->id] = (int) $method->instance_id; }
        $settings = array('flat_rate' => array('title' => 'Shipping', 'tax_status' => 'none', 'cost' => $source->rate, 'type' => 'class', 'no_class_cost' => ''));
        if ($source->free_from !== null) { $settings['free_shipping'] = array('title' => 'Free shipping', 'requires' => 'min_amount', 'min_amount' => $source->free_from, 'ignore_discounts' => 'yes'); }
        $instances = array();
        foreach ($settings as $kind => $values) {
            $id = $existing[$kind] ?? $zone->add_shipping_method($kind);
            if (!$id) { throw new RuntimeException('Shipping method storage unavailable.'); }
            update_option('woocommerce_' . $kind . '_' . $id . '_settings', $values);
            $instances[] = (int) $id;
        }
        foreach ($existing as $kind => $id) {
            if (!isset($settings[$kind])) { $zone->delete_shipping_method($id); delete_option('woocommerce_' . $kind . '_' . $id . '_settings'); }
        }
        $next[] = array('key' => $source->key, 'id' => (int) $zone->get_id(), 'methods' => $instances);
        unset($old[$source->key]);
    }
    foreach ($old as $binding) {
        $zone = WC_Shipping_Zones::get_zone($binding['id']);
        foreach ($zone->get_shipping_methods(false) as $method) { delete_option('woocommerce_' . $method->id . '_' . $method->instance_id . '_settings'); }
        if (!$zone->delete(true)) { throw new RuntimeException('Owned shipping zone removal failed.'); }
    }
    update_option('muse_owned_shipping', array('project_id' => MUSE_PROJECT_ID, 'zones' => $next));
    update_option('muse_shipping_confirmed', 'yes');
    WC_Cache_Helper::get_transient_version('shipping', true);
}

/** When the approved free method qualifies, hide only the paired owned flat rate. */
function muse_connector_owned_shipping_rates($rates) {
    if (!defined('MUSE_PROJECT_ID')) { return $rates; }
    $owner = get_option('muse_owned_shipping', null);
    if (!is_array($owner) || ($owner['project_id'] ?? null) !== MUSE_PROJECT_ID) { return $rates; }
    foreach ($owner['zones'] as $zone) {
        $free = false;
        foreach ($rates as $rate) { if ($rate->get_method_id() === 'free_shipping' && in_array($rate->get_instance_id(), $zone['methods'], true)) { $free = true; } }
        if ($free) { foreach ($rates as $key => $rate) { if ($rate->get_method_id() === 'flat_rate' && in_array($rate->get_instance_id(), $zone['methods'], true)) { unset($rates[$key]); } } }
    }
    return $rates;
}
