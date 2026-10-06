<?php
defined('ABSPATH') || exit;

function muse_connector_canonical_sku($sku) {
    muse_connector_plain_text($sku, 100, true);
    // Python str.strip() whitespace set, including its four legacy control separators.
    $sku = preg_replace('/\A[\s\x{001c}-\x{001f}]+|[\s\x{001c}-\x{001f}]+\z/u', '', $sku);
    if ($sku === '') { throw new MUSE_Operation_Conflict('SKU is required.'); }
    return mb_convert_case($sku, MB_CASE_FOLD, 'UTF-8');
}

function muse_connector_sku_state($sku) {
    $canonical = muse_connector_canonical_sku($sku);
    $snapshot = muse_connector_snapshot();
    if (is_wp_error($snapshot)) { throw new RuntimeException('Store context unavailable.'); }
    $id = wc_get_product_id_by_sku($sku);
    foreach ($snapshot['products'] as $product) {
        if ($product['sku'] !== '' && muse_connector_canonical_sku($product['sku']) === $canonical) {
            $id = $product['id']; break;
        }
    }
    $state = (object) array('sku' => $canonical, 'exists' => (bool) $id);
    if ($id) {
        $state->product_id = (int) $id;
        $state->entity_fingerprint = muse_connector_current_fingerprint('product:' . $id);
    }
    return $state;
}

function muse_connector_validate_product_draft($operation, $claims = null) {
    muse_connector_exact_keys($operation->payload, isset($operation->payload->media_bindings) ? array('product', 'media_bindings') : array('product'));
    $product = $operation->payload->product;
    muse_connector_exact_keys($product, array('sku', 'title', 'price', 'currency', 'stock', 'description', 'category', 'source_facts', 'media_refs'));
    $canonical = muse_connector_canonical_sku($product->sku);
    muse_connector_plain_text($product->title, 200, true);
    muse_connector_plain_text($product->description, 20000);
    muse_connector_plain_text($product->category, 160);
    if (!is_string($product->price) || preg_match('/\A[0-9]{1,12}(?:\.[0-9]{1,6})?\z/', $product->price) !== 1 ||
        $product->currency !== get_woocommerce_currency() || !is_int($product->stock) || $product->stock < 0 || $product->stock > 2147483647 ||
        !is_array($product->media_refs) || !($product->source_facts instanceof stdClass)) {
        throw new MUSE_Operation_Conflict('Invalid product facts.');
    }
    $bindings = $operation->payload->media_bindings ?? array();
    if (!is_array($bindings) || count($bindings) > 5 || count($bindings) !== count($product->media_refs) ||
        count(array_unique($product->media_refs, SORT_REGULAR)) !== count($product->media_refs)) {
        throw new MUSE_Operation_Conflict('Invalid product images.');
    }
    $ids = array();
    foreach ($bindings as $position => $binding) {
        muse_connector_exact_keys($binding, array('id', 'media_ref', 'sha256', 'mime_type', 'byte_size', 'width', 'height',
            'muse_project_id', 'status', 'parent_id', 'title', 'alt'));
        $id = muse_connector_positive_id($binding->id);
        $actual = muse_connector_media_record($id);
        if ($product->media_refs[$position] !== $actual->media_ref || $actual->status !== 'inherit' || $actual->parent_id !== 0 ||
            $actual->alt !== '' || $actual->title !== 'MUSE image ' . $actual->sha256 ||
            muse_connector_canonical($binding) !== muse_connector_canonical($actual)) {
            throw new MUSE_Operation_Conflict('Product image version changed.');
        }
        $resource = 'media-sha256:' . $actual->sha256;
        $version = hash('sha256', muse_connector_canonical(muse_connector_media_state($actual->sha256)));
        if (!$claims || !isset($claims->preconditions->{$resource}) || $claims->preconditions->{$resource} !== $version) {
            throw new MUSE_Operation_Conflict('Signed image version is required.');
        }
        $ids[] = $id;
    }
    if (count(array_unique($ids)) !== count($ids)) { throw new MUSE_Operation_Conflict('Duplicate product image.'); }
    foreach (get_object_vars($product->source_facts) as $value) {
        if (!is_string($value)) { throw new MUSE_Operation_Conflict('Invalid fact source.'); }
    }
    muse_connector_validate_preview_category_seed($product, $claims);
    if (muse_connector_prices_differ(wc_format_decimal($product->price, wc_get_price_decimals()), $product->price)) {
        throw new MUSE_Operation_Conflict('Unsupported price precision.');
    }
    if ($operation->resource_key !== 'sku:' . hash('sha256', $canonical) || muse_connector_sku_state($product->sku)->exists) {
        throw new MUSE_Operation_Conflict('SKU conflict.');
    }
}

function muse_connector_validate_preview_category_seed($product, $claims) {
    if (isset($product->source_facts->crew_preview_seed)) {
        if (!$claims || $claims->v !== 8 || $claims->environment !== 'staging' || $claims->purpose !== 'staging-preview' ||
            $product->source_facts->crew_preview_seed !== 'category' || count(get_object_vars($product->source_facts)) !== 1 ||
            $product->sku !== 'CREW-PREVIEW-CAT-' . substr(hash('sha256', $product->category), 0, 20) ||
            $product->title !== 'Crew preview category fixture' || $product->stock !== 0 ||
            muse_connector_prices_differ($product->price, '0.00') || $product->description !== '' || count($product->media_refs) !== 0) {
            throw new InvalidArgumentException('Private preview fixture requires isolated authorization.');
        }
    }
}

function muse_connector_create_product_draft($operation) {
    $facts = $operation->payload->product;
    $product = new WC_Product_Simple();
    $product->set_name($facts->title); $product->set_sku($facts->sku); $product->set_status('draft');
    if (isset($facts->source_facts->crew_preview_seed)) { $product->set_catalog_visibility('hidden'); }
    $product->set_regular_price($facts->price); $product->set_manage_stock(true); $product->set_stock_quantity($facts->stock);
    $product->set_description($facts->description); $product->update_meta_data('_muse_project_id', MUSE_PROJECT_ID);
    $images = $operation->payload->media_bindings ?? array();
    if ($images) {
        $product->set_image_id($images[0]->id);
        $product->set_gallery_image_ids(array_map(static function ($image) { return $image->id; }, array_slice($images, 1)));
    }
    if ($facts->category !== '') {
        $term = term_exists($facts->category, 'product_cat');
        if (!$term) { $term = wp_insert_term($facts->category, 'product_cat'); }
        if (is_wp_error($term)) { throw new RuntimeException('Category unavailable.'); }
        $product->set_category_ids(array((int) (is_array($term) ? $term['term_id'] : $term)));
    }
    $id = $product->save();
    if (!$id) { throw new RuntimeException('Product storage unavailable.'); }
    // WooCommerce rounds on input. Reject instead of silently changing approved financial facts.
    $saved = wc_get_product($id);
    if (!$saved || muse_connector_prices_differ($saved->get_regular_price(), $facts->price)) {
        throw new RuntimeException('Platform price precision mismatch.');
    }
}

function muse_connector_prices_differ($left, $right) {
    // Exact nonnegative decimal comparison without floats or requiring BCMath.
    $normalize = static function ($value) {
        $parts = explode('.', $value, 2);
        $whole = ltrim($parts[0], '0'); $fraction = rtrim($parts[1] ?? '', '0');
        return ($whole === '' ? '0' : $whole) . ($fraction === '' ? '' : '.' . $fraction);
    };
    return $normalize($left) !== $normalize($right);
}

function muse_connector_resource_route($request) {
    $sku = $request->get_param('sku');
    try {
        $slug = $request->get_param('page_slug');
        $media = $request->get_param('media_sha256');
        if ((int) ($sku !== null) + (int) ($slug !== null) + (int) ($media !== null) !== 1) {
            throw new InvalidArgumentException('Exactly one resource required.');
        }
        if ($media !== null) {
            $state = muse_connector_media_state($media);
            return array('resource_key' => 'media-sha256:' . $media, 'state' => $state,
                'fingerprint' => hash('sha256', muse_connector_canonical($state)));
        }
        $state = $sku === null ? muse_connector_page_slug_state($slug) : muse_connector_sku_state($sku);
        $key = $sku === null ? 'page-slug:' . hash('sha256', $state->slug) : 'sku:' . hash('sha256', $state->sku);
        return array('resource_key' => $key,
            'fingerprint' => hash('sha256', muse_connector_canonical($state)), 'state' => $state);
    } catch (Throwable $error) {
        return new WP_Error('muse_input_invalid', 'Invalid resource request.', array('status' => 422));
    }
}
