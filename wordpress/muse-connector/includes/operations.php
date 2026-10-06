<?php
defined('ABSPATH') || exit;

class MUSE_Operation_Conflict extends RuntimeException {}

function muse_connector_execution_scope() {
    foreach (array('MUSE_PROJECT_ID', 'MUSE_CONNECTION_ID', 'MUSE_ENVIRONMENT', 'MUSE_TARGET_URL',
                   'MUSE_EXECUTION_SECRET', 'MUSE_SERVICE_USER_ID') as $key) {
        if (!defined($key)) { throw new InvalidArgumentException('Execution configuration unavailable.'); }
    }
    if (rtrim(home_url(), '/') !== MUSE_TARGET_URL) { throw new InvalidArgumentException('Target mismatch.'); }
    return (object) array('project_id' => MUSE_PROJECT_ID, 'connection_id' => MUSE_CONNECTION_ID,
        'environment' => MUSE_ENVIRONMENT, 'target_url' => MUSE_TARGET_URL);
}

function muse_connector_write_permission() {
    $permission = muse_connector_read_permission();
    if (is_wp_error($permission)) { return $permission; }
    try { muse_connector_execution_scope(); }
    catch (Throwable $error) { return new WP_Error('muse_execution_disabled', 'Execution unavailable.', array('status' => 403)); }
    if (!muse_connector_service_identity() || !current_user_can('muse_execute_owned')) {
        return new WP_Error('muse_execution_denied', 'Dedicated application authentication required.', array('status' => 403));
    }
    return true;
}

function muse_connector_current_fingerprint($resource_key, $operation = null, $claims = null) {
    if (preg_match('/\Amedia-sha256:([a-f0-9]{64})\z/', $resource_key, $media)) {
        return hash('sha256', muse_connector_canonical(muse_connector_media_state($media[1])));
    }
    if ($claims && in_array($claims->v, array(3, 4, 5, 6, 7, 8), true) && isset($claims->identities->{$resource_key})) {
        $identity = $claims->identities->{$resource_key};
        $state = isset($identity->slug) ? muse_connector_page_slug_state($identity->slug) : muse_connector_sku_state($identity->sku);
        return hash('sha256', muse_connector_canonical($state));
    }
    if ($claims && $claims->v === 2 && isset($claims->sku_identities->{$resource_key})) {
        return hash('sha256', muse_connector_canonical(muse_connector_sku_state($claims->sku_identities->{$resource_key})));
    }
    if ($operation && $operation->kind === 'create_owned_page' && $resource_key === $operation->resource_key) {
        return hash('sha256', muse_connector_canonical(muse_connector_page_slug_state($operation->payload->slug)));
    }
    if ($resource_key === 'navigation:muse-storefront') {
        return hash('sha256', muse_connector_canonical((object) muse_connector_navigation_state()));
    }
    if ($resource_key === 'shipping:muse-storefront') { return hash('sha256', muse_connector_canonical((object) muse_connector_shipping_configuration())); }
    if (preg_match('/\Acategory:([1-9][0-9]*)\z/', $resource_key, $category)) {
        return hash('sha256', muse_connector_canonical((object) muse_connector_category_state((int) $category[1])));
    }
    if ($operation && $operation->kind === 'create_product_draft' && $resource_key === $operation->resource_key) {
        return hash('sha256', muse_connector_canonical(muse_connector_sku_state($operation->payload->product->sku)));
    }
    $snapshot = muse_connector_snapshot();
    if (is_wp_error($snapshot)) { throw new RuntimeException('Snapshot unavailable.'); }
    $value = json_decode(wp_json_encode($snapshot), false, 64, JSON_THROW_ON_ERROR);
    if ($resource_key === 'settings') { $resource = $value->settings; }
    elseif ($resource_key === 'theme:muse-storefront') { $resource = $value->theme_identity; }
    elseif (preg_match('/\A(page|product):([1-9][0-9]*)\z/', $resource_key, $parts)) {
        $resource = null;
        foreach ($parts[1] === 'page' ? $value->pages : $value->products as $item) {
            if ((string) $item->id === $parts[2]) { $resource = $item; break; }
        }
        if ($resource === null) { throw new MUSE_Operation_Conflict('Resource unavailable.'); }
    } else { throw new MUSE_Operation_Conflict('Unsupported resource.'); }
    return hash('sha256', muse_connector_canonical($resource));
}

function muse_connector_positive_id($value) {
    if (!is_int($value) || $value <= 0) { throw new MUSE_Operation_Conflict('Invalid resource identity.'); }
    return $value;
}

function muse_connector_owned_post($id, $type) {
    $post = get_post($id);
    $owners = get_post_meta($id, '_muse_project_id', false);
    if (!$post || $post->post_type !== $type || !in_array($post->post_status, array('draft', 'private', 'publish'), true) ||
        !$owners || count(array_unique($owners)) !== 1 || $owners[0] !== MUSE_PROJECT_ID) {
        throw new MUSE_Operation_Conflict('Resource ownership mismatch.');
    }
    return $post;
}

function muse_connector_plain_text($value, $limit, $nonempty = false) {
    if (!is_string($value) || !mb_check_encoding($value, 'UTF-8') || mb_strlen($value, 'UTF-8') > $limit ||
        ($nonempty && $value === '') || strpbrk($value, "<>\0") !== false) {
        throw new MUSE_Operation_Conflict('Invalid merchant text.');
    }
}

function muse_connector_validate_page_operation($operation, $claims) {
    $payload = $operation->payload;
    if ($operation->kind === 'update_owned_page') {
        muse_connector_exact_keys($payload, array('page_id', 'title', 'content'));
        muse_connector_plain_text($payload->title, 160, true);
        muse_connector_plain_text($payload->content, 256 * 1024);
        $id = muse_connector_positive_id($payload->page_id);
        muse_connector_owned_post($id, 'page');
        $resource = 'page:' . $id;
    } elseif ($operation->kind === 'publish_owned_page') {
        muse_connector_exact_keys($payload, array('page_id'));
        $id = muse_connector_positive_id($payload->page_id);
        muse_connector_owned_post($id, 'page'); $resource = 'page:' . $id;
    } elseif ($operation->kind === 'publish_product') {
        muse_connector_exact_keys($payload, array('product_id'));
        $id = muse_connector_positive_id($payload->product_id);
        muse_connector_owned_post($id, 'product');
        $product = wc_get_product($id);
        if (!$product || !$product->is_type('simple')) { throw new MUSE_Operation_Conflict('Unsupported product.'); }
        $resource = 'product:' . $id;
    } elseif ($operation->kind === 'set_storefront_options') {
        $keys = array('home_page_id', 'shop_page_id', 'cart_page_id', 'checkout_page_id');
        muse_connector_exact_keys($payload, $keys); $ids = array();
        foreach ($keys as $key) {
            $id = muse_connector_positive_id($payload->$key);
            $ids[] = $id; muse_connector_owned_post($id, 'page');
            if (!isset($claims->preconditions->{'page:' . $id})) {
                throw new MUSE_Operation_Conflict('Approved page version is required.');
            }
        }
        if (count(array_unique($ids)) !== 4) { throw new MUSE_Operation_Conflict('Pages must be distinct.'); }
        $resource = 'settings';
    } elseif ($operation->kind === 'create_product_draft') {
        muse_connector_validate_product_draft($operation, $claims); return;
    } elseif ($operation->kind === 'install_theme_package') {
        muse_connector_validate_theme_operation($operation); return;
    } elseif ($operation->kind === 'set_owned_navigation') {
        muse_connector_validate_navigation($operation, $claims); return;
    } elseif ($operation->kind === 'set_owned_store_navigation') {
        muse_connector_validate_store_navigation($operation, $claims); return;
    } elseif ($operation->kind === 'set_owned_shipping') {
        muse_connector_validate_shipping_operation($operation, $claims); return;
    } elseif ($operation->kind === 'create_owned_page') {
        muse_connector_validate_page_create($operation); return;
    } elseif ($operation->kind === 'create_owned_media') {
        muse_connector_validate_media_operation($operation); return;
    } else { throw new MUSE_Operation_Conflict('Operation not implemented.'); }
    if ($operation->resource_key !== $resource) { throw new MUSE_Operation_Conflict('Resource mismatch.'); }
}

function muse_connector_apply_page_operation($operation) {
    $payload = $operation->payload;
    if ($operation->kind === 'update_owned_page') {
        $result = wp_update_post(wp_slash(array('ID' => $payload->page_id, 'post_title' => $payload->title,
            'post_content' => $payload->content)), true);
    } elseif ($operation->kind === 'publish_owned_page' || $operation->kind === 'publish_product') {
        $id = $operation->kind === 'publish_owned_page' ? $payload->page_id : $payload->product_id;
        $result = wp_update_post(array('ID' => $id, 'post_status' => 'publish'), true);
    } elseif ($operation->kind === 'create_product_draft') {
        muse_connector_create_product_draft($operation); $result = true;
    } elseif ($operation->kind === 'install_theme_package') {
        muse_connector_install_theme_package($operation); $result = true;
    } elseif (in_array($operation->kind, array('set_owned_navigation', 'set_owned_store_navigation'), true)) {
        muse_connector_set_navigation($operation); $result = true;
    } elseif ($operation->kind === 'set_owned_shipping') {
        muse_connector_set_shipping($operation); $result = true;
    } elseif ($operation->kind === 'create_owned_page') {
        muse_connector_create_owned_page($operation); $result = true;
    } elseif ($operation->kind === 'create_owned_media') {
        muse_connector_create_owned_media($operation); $result = true;
    } else {
        foreach (array('page_on_front' => $payload->home_page_id, 'woocommerce_shop_page_id' => $payload->shop_page_id,
            'woocommerce_cart_page_id' => $payload->cart_page_id, 'woocommerce_checkout_page_id' => $payload->checkout_page_id,
            'show_on_front' => 'page') as $key => $value) { update_option($key, $value); }
        $result = true;
    }
    if (is_wp_error($result) || !$result) { throw new RuntimeException('Platform update unavailable.'); }
}

/** SQL effects and receipt commit together. WP hooks can have nontransactional external effects. */
function muse_connector_operation_route($request) {
    global $wpdb;
    if (strlen($request->get_body()) > 16 * 1024 * 1024) {
        return new WP_Error('muse_input_invalid', 'Request exceeds size limit.', array('status' => 422));
    }
    try {
        $input = json_decode($request->get_body(), false, 64, JSON_THROW_ON_ERROR);
        muse_connector_exact_keys($input, array('operation', 'execution_authorization'));
        $operation = $input->operation;
        if (strlen($request->get_body()) > 8 * 1024 * 1024 && $operation->kind !== 'create_owned_media') {
            throw new InvalidArgumentException('Non-media request exceeds size limit.');
        }
        $claims = muse_connector_verify_operation_authorization($input->execution_authorization, $operation,
            muse_connector_execution_scope(), MUSE_EXECUTION_SECRET, microtime(true));
    } catch (Throwable $error) {
        return new WP_Error('muse_authorization_invalid', 'Invalid execution authorization.', array('status' => 403));
    }
    $table = muse_connector_receipt_table();
    $lock = 'muse:' . hash('sha256', DB_NAME . ':' . $wpdb->prefix);
    if ((string) $wpdb->get_var($wpdb->prepare('SELECT GET_LOCK(%s, 3)', $lock)) !== '1') {
        return new WP_Error('muse_resource_conflict', 'Execution is busy.', array('status' => 409));
    }
    try {
        $existing = muse_connector_get_receipt($operation->operation_id);
        if ($existing) {
            if ($existing['operation_digest'] !== $claims->operation_digest) {
                return new WP_Error('muse_resource_conflict', 'Operation identity conflict.', array('status' => 409));
            }
            return $existing;
        }
        if ($wpdb->get_var($wpdb->prepare("SELECT operation_id FROM `$table` WHERE connection_id=%s AND environment=%s
            AND resource_key=%s AND state='NEEDS_RECONCILIATION' LIMIT 1", MUSE_CONNECTION_ID, MUSE_ENVIRONMENT, $operation->resource_key))) {
            return new WP_Error('muse_resource_conflict', 'Resource requires reconciliation.', array('status' => 409));
        }
        foreach (array($table, $wpdb->posts, $wpdb->postmeta, $wpdb->options, $wpdb->terms, $wpdb->term_taxonomy,
            $wpdb->term_relationships, $wpdb->termmeta, $wpdb->prefix . 'wc_product_meta_lookup') as $name) {
            $engine = $wpdb->get_var($wpdb->prepare('SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s', DB_NAME, $name));
            if (strtolower((string) $engine) !== 'innodb') { throw new RuntimeException('Transactional storage required.'); }
        }
        // Persist the uncertain state before invoking platform code, including crash/exit in a hook.
        if ($wpdb->insert($table, array('connection_id' => MUSE_CONNECTION_ID, 'environment' => MUSE_ENVIRONMENT,
            'project_id' => MUSE_PROJECT_ID, 'operation_id' => $operation->operation_id, 'operation_digest' => $claims->operation_digest,
            'resource_key' => $operation->resource_key, 'state' => 'NEEDS_RECONCILIATION')) === false) {
            throw new RuntimeException('Receipt storage unavailable.');
        }
        muse_connector_db_query('START TRANSACTION');
        // Bound first-version stores (<=200 resources). Lock CMS rows before refreshing cached facts.
        foreach (array($wpdb->posts, $wpdb->postmeta, $wpdb->options, $wpdb->terms, $wpdb->term_taxonomy,
            $wpdb->term_relationships, $wpdb->termmeta, $wpdb->prefix . 'wc_product_meta_lookup') as $name) {
            muse_connector_db_query("SELECT * FROM `$name` FOR UPDATE");
        }
        wp_cache_flush();
        try {
            try { muse_connector_validate_page_operation($operation, $claims); }
            catch (InvalidArgumentException $error) { throw new MUSE_Operation_Conflict('Invalid operation payload.'); }
            foreach (get_object_vars($claims->preconditions) as $resource => $fingerprint) {
                if (!hash_equals($fingerprint, muse_connector_current_fingerprint($resource, $operation, $claims))) {
                    throw new MUSE_Operation_Conflict('Resource version conflict.');
                }
            }
        } catch (MUSE_Operation_Conflict $error) {
            muse_connector_db_query('ROLLBACK');
            if ($wpdb->update($table, array('state' => 'FAILED'), array('connection_id' => MUSE_CONNECTION_ID,
                'environment' => MUSE_ENVIRONMENT, 'operation_id' => $operation->operation_id)) === false) {
                throw new RuntimeException('Receipt unavailable.');
            }
            return muse_connector_get_receipt($operation->operation_id);
        }
        muse_connector_apply_page_operation($operation);
        if ($wpdb->last_error) { throw new RuntimeException('Platform storage unavailable.'); }
        wp_cache_flush();
        $fingerprint = muse_connector_current_fingerprint($operation->resource_key, $operation);
        if ($wpdb->update($table, array('state' => 'SUCCEEDED', 'fingerprint' => $fingerprint),
            array('connection_id' => MUSE_CONNECTION_ID, 'environment' => MUSE_ENVIRONMENT,
                  'operation_id' => $operation->operation_id)) === false) { throw new RuntimeException('Receipt unavailable.'); }
        muse_connector_db_query('COMMIT');
        return muse_connector_get_receipt($operation->operation_id);
    } catch (Throwable $error) {
        $wpdb->query('ROLLBACK'); wp_cache_flush();
        $receipt = muse_connector_get_receipt($operation->operation_id);
        return $receipt ?: new WP_Error('muse_execution_unavailable', 'Execution unavailable.', array('status' => 503));
    } finally {
        $wpdb->get_var($wpdb->prepare('SELECT RELEASE_LOCK(%s)', $lock));
    }
}
