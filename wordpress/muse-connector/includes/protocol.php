<?php
defined('ABSPATH') || exit;

/** Preserve JSON object/list shape and the exact Python canonical UTF-8 wire format. */
function muse_connector_canonical($value) {
    if ($value instanceof stdClass) {
        $members = get_object_vars($value);
        ksort($members, SORT_STRING);
        $parts = array();
        foreach ($members as $key => $member) {
            $parts[] = muse_connector_canonical((string) $key) . ':' . muse_connector_canonical($member);
        }
        return '{' . implode(',', $parts) . '}';
    }
    if (is_array($value)) {
        if (!array_is_list($value)) {
            return muse_connector_canonical((object) $value);
        }
        return '[' . implode(',', array_map('muse_connector_canonical', $value)) . ']';
    }
    return json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES |
        JSON_UNESCAPED_LINE_TERMINATORS | JSON_PRESERVE_ZERO_FRACTION | JSON_THROW_ON_ERROR);
}

function muse_connector_exact_keys($object, $keys) {
    if (!($object instanceof stdClass)) { throw new InvalidArgumentException('Invalid object.'); }
    $actual = array_keys(get_object_vars($object));
    sort($actual, SORT_STRING); sort($keys, SORT_STRING);
    if ($actual !== $keys) { throw new InvalidArgumentException('Invalid fields.'); }
}

function muse_connector_hash($value) {
    return is_string($value) && preg_match('/\A[a-f0-9]{64}\z/', $value) === 1;
}

function muse_connector_identity($value) {
    return is_string($value) && preg_match('/\A[a-zA-Z0-9_-]{1,100}\z/', $value) === 1;
}

/** No HTTP or WordPress globals: a separately configured server scope is mandatory. */
function muse_connector_verify_execution($token, $operation, $scope, $secret, $now, $expected_version = 1) {
    $limit = in_array($expected_version, array(4, 5, 6, 7, 8), true) ? 65536 : (in_array($expected_version, array(2, 3), true) ? 32768 : 8192);
    if (!is_string($secret) || strlen($secret) < 32 || !is_string($token) || strlen($token) > $limit ||
        preg_match('/\A([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]{43})\z/', $token, $parts) !== 1) {
        throw new InvalidArgumentException('Invalid authorization.');
    }
    $body = base64_decode(strtr($parts[1], '-_', '+/'), true);
    if ($body === false) { throw new InvalidArgumentException('Invalid authorization.'); }
    $signature = rtrim(strtr(base64_encode(hash_hmac('sha256', $body, $secret, true)), '+/', '-_'), '=');
    if (!hash_equals($signature, $parts[2])) { throw new InvalidArgumentException('Invalid authorization.'); }
    $claims = json_decode($body, false, 32, JSON_THROW_ON_ERROR);
    $keys = array('v', 'grant_id', 'project_id', 'connection_id', 'target_url',
        'environment', 'audience', 'changeset_digest', 'verification_hash', 'preconditions',
        'operation_digest', 'issued_at', 'expires_at');
    if ($expected_version === 2) { $keys = array_merge($keys, array('step_index', 'step_key', 'sku_identities')); }
    if ($expected_version === 3) { $keys = array_merge($keys, array('step_index', 'step_key', 'identities')); }
    if (in_array($expected_version, array(4, 5, 6, 7, 8), true)) { $keys = array_merge($keys, array('step_index', 'step_key', 'identities', 'workflow', 'image_count', 'product_count')); }
    if (in_array($expected_version, array(7, 8), true)) { $keys = array_merge($keys, array('shipping_enabled', 'category_count')); }
    if (in_array($expected_version, array(5, 8), true)) { $keys[] = 'purpose'; }
    muse_connector_exact_keys($claims, $keys);
    muse_connector_exact_keys($scope, array('project_id', 'connection_id', 'environment', 'target_url'));
    $audiences = array(1 => 'muse-wp-operation-v1', 2 => 'muse-wp-product-step-v2', 3 => 'muse-wp-site-step-v3', 4 => 'muse-wp-merchant-step-v4', 5 => 'muse-wp-staging-preview-v5', 6 => 'muse-wp-retained-merchant-step-v6', 7 => 'muse-wp-store-step-v7', 8 => 'muse-wp-store-preview-v8');
    if (!isset($audiences[$expected_version]) || $claims->v !== $expected_version ||
        $claims->audience !== $audiences[$expected_version] ||
        !in_array($claims->environment, array('staging', 'live', 'live-test'), true)) {
        throw new InvalidArgumentException('Invalid scope.');
    }
    if (in_array($expected_version, array(5, 8), true) && ($claims->environment !== 'staging' || $scope->environment !== 'staging' || $claims->purpose !== 'staging-preview')) {
        throw new InvalidArgumentException('Invalid preview scope.');
    }
    foreach (array('grant_id', 'project_id', 'connection_id') as $name) {
        if (!muse_connector_identity($claims->$name)) { throw new InvalidArgumentException('Invalid identity.'); }
    }
    foreach (array('project_id', 'connection_id', 'environment', 'target_url') as $name) {
        if (!is_string($claims->$name) || $claims->$name !== $scope->$name) {
            throw new InvalidArgumentException('Invalid scope.');
        }
    }
    foreach (array('changeset_digest', 'verification_hash', 'operation_digest') as $name) {
        if (!muse_connector_hash($claims->$name)) { throw new InvalidArgumentException('Invalid hash.'); }
    }
    foreach (array('issued_at', 'expires_at') as $name) {
        if ((!is_int($claims->$name) && !is_float($claims->$name)) || !is_finite((float) $claims->$name)) {
            throw new InvalidArgumentException('Invalid time.');
        }
    }
    if ((!is_int($now) && !is_float($now)) || !is_finite((float) $now) || $claims->issued_at > $now ||
        $claims->expires_at <= $now || $claims->expires_at <= $claims->issued_at ||
        $claims->expires_at - $claims->issued_at > 1800) {
        throw new InvalidArgumentException('Expired authorization.');
    }
    if (!($claims->preconditions instanceof stdClass) || count(get_object_vars($claims->preconditions)) > 256) {
        throw new InvalidArgumentException('Invalid preconditions.');
    }
    foreach (get_object_vars($claims->preconditions) as $key => $value) {
        if (!is_string($key) || strlen($key) > 200 || !muse_connector_hash($value)) {
            throw new InvalidArgumentException('Invalid preconditions.');
        }
    }
    muse_connector_exact_keys($operation, array('operation_id', 'kind', 'resource_key', 'expected_fingerprint', 'payload'));
    if (!muse_connector_identity($operation->operation_id) || !muse_connector_hash($operation->expected_fingerprint) ||
        !is_string($operation->resource_key) || !isset($claims->preconditions->{$operation->resource_key}) ||
        $claims->preconditions->{$operation->resource_key} !== $operation->expected_fingerprint ||
        !in_array($operation->kind, array('install_theme_package', 'update_owned_page', 'set_owned_navigation',
            'create_product_draft', 'publish_product', 'publish_owned_page', 'set_storefront_options', 'create_owned_page', 'create_owned_media', 'set_owned_shipping', 'set_owned_store_navigation'), true) ||
        !($operation->payload instanceof stdClass) ||
        !hash_equals($claims->operation_digest, hash('sha256', muse_connector_canonical($operation)))) {
        throw new InvalidArgumentException('Invalid operation.');
    }
    if (in_array($operation->kind, array('set_owned_shipping', 'set_owned_store_navigation'), true) && !in_array($expected_version, array(7, 8), true)) {
        throw new InvalidArgumentException('Separate store configuration audience required.');
    }
    if ($expected_version === 2) {
        if (!is_int($claims->step_index) || $claims->step_index < 0 || $claims->step_index >= 40 ||
            !is_string($claims->step_key) || !($claims->sku_identities instanceof stdClass) ||
            !isset($claims->preconditions->settings, $claims->preconditions->{'theme:muse-storefront'})) {
            throw new InvalidArgumentException('Invalid release step.');
        }
        $create = $claims->step_index % 2 === 0;
        $key = ($create ? 'create-product-' : 'publish-product-') . (intdiv($claims->step_index, 2) + 1);
        if ($claims->step_key !== $key || $operation->kind !== ($create ? 'create_product_draft' : 'publish_product') ||
            $operation->operation_id !== 'release-' . $claims->changeset_digest . '-' . $claims->step_index) {
            throw new InvalidArgumentException('Invalid release member.');
        }
        $identities = get_object_vars($claims->sku_identities); $remaining = array();
        foreach (get_object_vars($claims->preconditions) as $resource => $fingerprint) {
            if ($resource === 'settings' || $resource === 'theme:muse-storefront' || preg_match('/\Aproduct:[1-9][0-9]*\z/', $resource)) { continue; }
            if (preg_match('/\Asku:[a-f0-9]{64}\z/', $resource) !== 1 || !isset($identities[$resource]) ||
                !is_string($identities[$resource]) || strlen($identities[$resource]) > 640 || $identities[$resource] === '' ||
                $resource !== 'sku:' . hash('sha256', $identities[$resource]) ||
                $fingerprint !== hash('sha256', muse_connector_canonical((object) array('sku' => $identities[$resource], 'exists' => false)))) {
                throw new InvalidArgumentException('Invalid release SKU proof.');
            }
            $remaining[] = $resource;
        }
        $actual = array_keys($identities); sort($actual); sort($remaining);
        if ($actual !== $remaining || ($create && !isset($identities[$operation->resource_key]))) {
            throw new InvalidArgumentException('Invalid release identities.');
        }
    }
    if ($expected_version === 3) { muse_connector_validate_site_claims($claims, $operation); }
    if (in_array($expected_version, array(4, 5, 6, 7, 8), true)) { muse_connector_validate_merchant_claims($claims, $operation); }
    return $claims;
}

function muse_connector_validate_site_claims($claims, $operation, $max_products = 20) {
    if (!is_int($claims->step_index) || $claims->step_index < 0 || $claims->step_index >= 15 + 2 * $max_products ||
        !is_string($claims->step_key) || !($claims->identities instanceof stdClass) ||
        !isset($claims->preconditions->settings, $claims->preconditions->{'theme:muse-storefront'},
               $claims->preconditions->{'navigation:muse-storefront'})) {
        throw new InvalidArgumentException('Invalid website step.');
    }
    $index = $claims->step_index;
    if ($index === 0) { $kind = 'install_theme_package'; $key = 'install-theme'; }
    elseif ($index < 13) {
        $page = array('home', 'shop', 'cart', 'checkout', 'about', 'contact')[intdiv($index - 1, 2)];
        $create = $index % 2 === 1;
        $kind = $create ? 'create_owned_page' : 'publish_owned_page';
        $key = ($create ? 'create-page-' : 'publish-page-') . $page;
    } elseif ($index === 13) { $kind = 'set_storefront_options'; $key = 'set-storefront'; }
    elseif ($index === 14) { $kind = 'set_owned_navigation'; $key = 'set-navigation'; }
    else {
        $create = ($index - 15) % 2 === 0;
        $kind = $create ? 'create_product_draft' : 'publish_product';
        $key = ($create ? 'create-product-' : 'publish-product-') . (intdiv($index - 15, 2) + 1);
    }
    if ($claims->step_key !== $key || $operation->kind !== $kind ||
        $operation->operation_id !== 'site-' . $claims->changeset_digest . '-' . $index) {
        throw new InvalidArgumentException('Invalid website member.');
    }
    $remaining = array(); $identities = get_object_vars($claims->identities);
    foreach (get_object_vars($claims->preconditions) as $resource => $fingerprint) {
        if (in_array($resource, array('settings', 'theme:muse-storefront', 'navigation:muse-storefront'), true) ||
            preg_match('/\A(?:page|product):[1-9][0-9]*\z/', $resource)) { continue; }
        if (preg_match('/\A(page-slug|sku):[a-f0-9]{64}\z/', $resource, $parts) !== 1 || !isset($identities[$resource])) {
            throw new InvalidArgumentException('Invalid website resource.');
        }
        $name = $parts[1] === 'sku' ? 'sku' : 'slug';
        $identity = $identities[$resource]; muse_connector_exact_keys($identity, array($name));
        if (!is_string($identity->$name) || $identity->$name === '' || strlen($identity->$name) > ($name === 'slug' ? 64 : 640) ||
            ($name === 'slug' && preg_match('/\A[a-z][a-z0-9-]{0,63}\z/', $identity->$name) !== 1) ||
            $resource !== $parts[1] . ':' . hash('sha256', $identity->$name) ||
            $fingerprint !== hash('sha256', muse_connector_canonical((object) array($name => $identity->$name, 'exists' => false)))) {
            throw new InvalidArgumentException('Invalid website identity.');
        }
        $remaining[] = $resource;
    }
    $actual = array_keys($identities); sort($actual); sort($remaining);
    if ($actual !== $remaining || (in_array($kind, array('create_owned_page', 'create_product_draft'), true) &&
        !isset($identities[$operation->resource_key]))) { throw new InvalidArgumentException('Invalid website identity scope.'); }
}

/** Closed image prefix followed by the fixed website or launch graph. */
function muse_connector_validate_merchant_claims($claims, $operation) {
    $retained = $claims->v === 6;
    $store = in_array($claims->v, array(7, 8), true);
    if ($store && ($claims->workflow !== 'build_site' || !is_bool($claims->shipping_enabled) ||
        !is_int($claims->category_count) || $claims->category_count < 0 || $claims->category_count > 10 ||
        ($claims->shipping_enabled && !isset($claims->preconditions->{'shipping:muse-storefront'})))) {
        throw new InvalidArgumentException('Invalid store configuration declaration.');
    }
    if (!in_array($claims->workflow, array('build_site', 'launch_products'), true) ||
        !is_int($claims->image_count) || $claims->image_count < 0 || $claims->image_count > 100 ||
        !is_int($claims->product_count) || $claims->product_count < 0 || $claims->product_count > ($claims->v === 8 ? 30 : 20) ||
        ($claims->workflow === 'launch_products' && $claims->product_count === 0) ||
        ($retained && $claims->workflow !== 'launch_products') ||
        !is_int($claims->step_index) || $claims->step_index < 0 || !($claims->identities instanceof stdClass) ||
        !is_string($claims->step_key) || !isset($claims->preconditions->settings,
            $claims->preconditions->{'theme:muse-storefront'}, $claims->preconditions->{'navigation:muse-storefront'})) {
        throw new InvalidArgumentException('Invalid merchant graph.');
    }
    $total = $claims->image_count + ($claims->workflow === 'build_site' ? 15 : ($retained ? 0 : 1)) + 2 * $claims->product_count + ($store && $claims->shipping_enabled ? 1 : 0);
    if ($claims->step_index >= $total || $operation->operation_id !== 'merchant-' . $claims->changeset_digest . '-' . $claims->step_index) {
        throw new InvalidArgumentException('Invalid merchant member.');
    }
    // Reuse unchanged v3 rules only for checking non-media members. These
    // clones do not create an authorization or change the actual signed bytes.
    $site = clone $claims; $site->preconditions = clone $claims->preconditions; $site->identities = clone $claims->identities;
    if ($store) {
        $categories = 0;
        foreach (get_object_vars($site->preconditions) as $resource => $fingerprint) {
            if ($resource === 'shipping:muse-storefront') {
                if (!$claims->shipping_enabled) { throw new InvalidArgumentException('Unsigned shipping resource.'); }
                unset($site->preconditions->{$resource});
            } elseif (preg_match('/\Acategory:[1-9][0-9]*\z/', $resource)) {
                $categories++; unset($site->preconditions->{$resource});
            }
        }
        if ($categories > $claims->category_count) { throw new InvalidArgumentException('Extra category dependencies.'); }
    }
    $count = 0; $remaining = 0;
    foreach (get_object_vars($claims->preconditions) as $resource => $fingerprint) {
        if (!str_starts_with($resource, 'media-sha256:')) { continue; }
        if (preg_match('/\Amedia-sha256:([a-f0-9]{64})\z/', $resource, $parts) !== 1) {
            throw new InvalidArgumentException('Invalid merchant image resource.');
        }
        $count++;
        if (isset($claims->identities->{$resource})) {
            $identity = $claims->identities->{$resource}; muse_connector_exact_keys($identity, array('sha256'));
            if ($identity->sha256 !== $parts[1] || $fingerprint !== hash('sha256', muse_connector_canonical(
                (object) array('sha256' => $parts[1], 'exists' => false)))) {
                throw new InvalidArgumentException('Invalid merchant image absence.');
            }
            $remaining++; unset($site->identities->{$resource});
        }
        unset($site->preconditions->{$resource});
    }
    if ($count !== $claims->image_count || $remaining !== $claims->image_count - min($claims->image_count, $claims->step_index)) {
        throw new InvalidArgumentException('Invalid merchant image position.');
    }
    $pages = 0; $products = 0;
    foreach (get_object_vars($site->preconditions) as $resource => $fingerprint) {
        if (preg_match('/\A(?:page-slug:[a-f0-9]{64}|page:[1-9][0-9]*)\z/', $resource)) { $pages++; }
        if (preg_match('/\A(?:sku:[a-f0-9]{64}|product:[1-9][0-9]*)\z/', $resource)) { $products++; }
    }
    if ($pages !== ($claims->workflow === 'build_site' ? 6 : 0) || $products !== $claims->product_count) {
        throw new InvalidArgumentException('Invalid merchant resource count.');
    }
    if ($claims->step_index < $claims->image_count) {
        if ($operation->kind !== 'create_owned_media' || $claims->step_key !== 'create-image-' . ($claims->step_index + 1) ||
            !isset($claims->identities->{$operation->resource_key})) { throw new InvalidArgumentException('Invalid image member.'); }
        $site->step_index = 0; $site->step_key = 'install-theme';
        $probe = clone $operation; $probe->kind = 'install_theme_package'; $probe->operation_id = 'site-' . $claims->changeset_digest . '-0';
        muse_connector_validate_site_claims($site, $probe, $claims->v === 8 ? 30 : 20);
    } else {
        $index = $claims->step_index - $claims->image_count;
        if ($store) {
            $products_end = 14 + 2 * $claims->product_count;
            if ($index >= $products_end) {
                $shipping = $claims->shipping_enabled && $index === $products_end;
                if ($operation->kind !== ($shipping ? 'set_owned_shipping' : 'set_owned_store_navigation') ||
                    $claims->step_key !== ($shipping ? 'set-shipping' : 'set-store-navigation') ||
                    count(get_object_vars($site->identities)) !== 0 ||
                    (!$shipping && $categories !== $claims->category_count)) {
                    throw new InvalidArgumentException('Invalid store configuration member.');
                }
                $site->step_index = 0; $site->step_key = 'install-theme';
                $probe = clone $operation; $probe->kind = 'install_theme_package';
                $probe->operation_id = 'site-' . $claims->changeset_digest . '-0';
                muse_connector_validate_site_claims($site, $probe, $claims->v === 8 ? 30 : 20); return;
            }
            $site->step_index = $index >= 14 ? $index + 1 : $index;
            $probe = clone $operation; $probe->operation_id = 'site-' . $claims->changeset_digest . '-' . $site->step_index;
            muse_connector_validate_site_claims($site, $probe, $claims->v === 8 ? 30 : 20); return;
        }
        $site->step_index = $retained ? $index + 15 : ($claims->workflow === 'launch_products' && $index > 0 ? $index + 14 : $index);
        $probe = clone $operation; $probe->operation_id = 'site-' . $claims->changeset_digest . '-' . $site->step_index;
        muse_connector_validate_site_claims($site, $probe, $claims->v === 8 ? 30 : 20);
    }
}

/** Dispatch only between separately validated audiences; no v1 key relaxation. */
function muse_connector_verify_operation_authorization($token, $operation, $scope, $secret, $now) {
    $version = 1;
    if (is_string($token) && strlen($token) <= 65536) {
        $parts = explode('.', $token);
        if (count($parts) === 2) {
            $body = base64_decode(strtr($parts[0], '-_', '+/'), true);
            if ($body !== false) {
                $hint = json_decode($body);
                if ($hint instanceof stdClass && isset($hint->v) && in_array($hint->v, array(2, 3, 4, 5, 6, 7, 8), true)) { $version = $hint->v; }
            }
        }
    }
    return muse_connector_verify_execution($token, $operation, $scope, $secret, $now, $version);
}
