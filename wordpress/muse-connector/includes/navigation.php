<?php
defined('ABSPATH') || exit;

function muse_connector_category_state($id) {
    muse_connector_positive_id($id);
    $term = get_term($id, 'product_cat', OBJECT, 'raw');
    $url = $term && !is_wp_error($term) ? get_term_link($term) : null;
    if (!$term || is_wp_error($term) || !$url || is_wp_error($url) || !str_starts_with($url, rtrim(home_url(), '/') . '/')) {
        throw new InvalidArgumentException('Category permalink unavailable.');
    }
    return array('id' => $id, 'name' => (string) $term->name, 'slug' => (string) $term->slug, 'url' => $url);
}

function muse_connector_validate_store_navigation($operation, $claims) {
    if (!in_array($claims->v, array(7, 8), true)) { throw new InvalidArgumentException('Store navigation authority required.'); }
    muse_connector_exact_keys($operation->payload, array('items'));
    $items = $operation->payload->items;
    if ($operation->resource_key !== 'navigation:muse-storefront' || !is_array($items) || count($items) < 1 || count($items) > 16 ||
        !isset($claims->preconditions->{'theme:muse-storefront'}) || count(muse_connector_navigation_state()['items']) > 1) {
        throw new InvalidArgumentException('Invalid store navigation.');
    }
    $seen = array(); $category_count = 0;
    foreach ($items as $item) {
        $category = isset($item->category_id);
        muse_connector_exact_keys($item, array($category ? 'category_id' : 'page_id', 'label'));
        $id = muse_connector_positive_id($category ? $item->category_id : $item->page_id);
        muse_connector_plain_text($item->label, 160, true);
        $key = ($category ? 'category:' : 'page:') . $id;
        if (isset($seen[$key]) || !isset($claims->preconditions->{$key})) { throw new InvalidArgumentException('Navigation version required.'); }
        $seen[$key] = true;
        if (!$category) { muse_connector_owned_post($id, 'page'); continue; }
        $category_count++; muse_connector_category_state($id); $bound = false;
        foreach (get_object_vars($claims->preconditions) as $resource => $fingerprint) {
            if (preg_match('/\Aproduct:([1-9][0-9]*)\z/', $resource, $match)) {
                $product = wc_get_product((int) $match[1]);
                if ($product && $product->get_meta('_muse_project_id') === MUSE_PROJECT_ID && in_array($id, $product->get_category_ids(), true)) { $bound = true; }
            }
        }
        if (!$bound) { throw new InvalidArgumentException('Category is outside approved products.'); }
    }
    if ($category_count !== $claims->category_count) { throw new InvalidArgumentException('Category membership differs.'); }
    $header = get_block_template('muse-storefront//header', 'wp_template_part');
    if (!$header || ($header->source !== 'theme' && (!$header->wp_id || get_post_meta($header->wp_id, '_muse_project_id', true) !== MUSE_PROJECT_ID))) {
        throw new InvalidArgumentException('Merchant header must be merged first.');
    }
    muse_connector_materialize_header_navigation(muse_connector_header_source($header), 1);
}

function muse_connector_materialize_header_navigation($content, $navigation_id) {
    muse_connector_positive_id($navigation_id);
    if (!is_string($content) || strlen($content) > 524288) { throw new InvalidArgumentException('Invalid header source.'); }
    muse_connector_validate_static_file('parts/header.html', $content);
    $count = 0;
    $replace = function ($blocks) use (&$replace, &$count, $navigation_id) {
        foreach ($blocks as &$block) {
            if ($block['blockName'] === 'core/navigation') {
                $count++;
                $block['attrs']['ref'] = $navigation_id;
                $block['innerBlocks'] = array(); $block['innerHTML'] = ''; $block['innerContent'] = array();
            } else { $block['innerBlocks'] = $replace($block['innerBlocks']); }
        }
        return $blocks;
    };
    $blocks = $replace(parse_blocks($content));
    if ($count !== 1) { throw new InvalidArgumentException('Exactly one header navigation is required.'); }
    return serialize_blocks($blocks);
}

function muse_connector_header_source($header) {
    if ($header->source === 'theme') {
        $path = get_stylesheet_directory() . '/parts/header.html';
        if (is_link($path) || !is_file($path)) { throw new InvalidArgumentException('Header source unavailable.'); }
        $content = file_get_contents($path);
    } else {
        $post = get_post($header->wp_id);
        $content = $post ? $post->post_content : false;
    }
    if (!is_string($content)) { throw new InvalidArgumentException('Header source unavailable.'); }
    return $content;
}

function muse_connector_navigation_state() {
    if (!defined('MUSE_PROJECT_ID')) { return array('items' => array()); }
    $posts = get_posts(array('post_type' => 'wp_navigation', 'post_status' => array('publish', 'draft', 'private'),
        'numberposts' => 2, 'meta_key' => '_muse_project_id', 'meta_value' => MUSE_PROJECT_ID, 'orderby' => 'ID', 'order' => 'ASC'));
    $items = array();
    foreach ($posts as $post) {
        $items[] = array('id' => $post->ID, 'content' => $post->post_content, 'status' => $post->post_status,
            'muse_project_id' => (string) get_post_meta($post->ID, '_muse_project_id', true));
    }
    return array('items' => $items);
}

function muse_connector_validate_navigation($operation, $claims) {
    muse_connector_exact_keys($operation->payload, array('items'));
    $items = $operation->payload->items;
    if ($operation->resource_key !== 'navigation:muse-storefront' || !is_array($items) || count($items) < 1 || count($items) > 7 ||
        !isset($claims->preconditions->{'theme:muse-storefront'}) || count(muse_connector_navigation_state()['items']) > 1) {
        throw new InvalidArgumentException('Invalid navigation scope.');
    }
    $seen = array();
    foreach ($items as $item) {
        muse_connector_exact_keys($item, array('page_id', 'label'));
        $id = muse_connector_positive_id($item->page_id); muse_connector_plain_text($item->label, 160, true);
        if (isset($seen[$id]) || !isset($claims->preconditions->{'page:' . $id})) { throw new InvalidArgumentException('Page version is required.'); }
        $seen[$id] = true; muse_connector_owned_post($id, 'page');
    }
    $header = get_block_template('muse-storefront//header', 'wp_template_part');
    if (!$header || ($header->source !== 'theme' &&
        (!$header->wp_id || get_post_meta($header->wp_id, '_muse_project_id', true) !== MUSE_PROJECT_ID))) {
        throw new InvalidArgumentException('Merchant header must be merged first.');
    }
    muse_connector_materialize_header_navigation(muse_connector_header_source($header), 1);
}

function muse_connector_set_navigation($operation) {
    $header = get_block_template('muse-storefront//header', 'wp_template_part');
    $source = muse_connector_header_source($header);
    muse_connector_materialize_header_navigation($source, 1);
    $blocks = array();
    foreach ($operation->payload->items as $item) {
        $category = isset($item->category_id); $id = $category ? $item->category_id : $item->page_id;
        $url = $category ? muse_connector_category_state($id)['url'] : get_permalink($id);
        $blocks[] = array('blockName' => 'core/navigation-link', 'attrs' => array('label' => $item->label, 'type' => $category ? 'product_cat' : 'page',
            'id' => $id, 'kind' => $category ? 'taxonomy' : 'post-type', 'url' => $url),
            'innerBlocks' => array(), 'innerHTML' => '', 'innerContent' => array());
    }
    $existing = muse_connector_navigation_state()['items'];
    $id = wp_insert_post(wp_slash(array('ID' => $existing ? $existing[0]['id'] : 0, 'post_type' => 'wp_navigation',
        'post_status' => 'publish', 'post_title' => 'MUSE Store Navigation', 'post_content' => serialize_blocks($blocks))), true);
    if (is_wp_error($id) || !$id) { throw new RuntimeException('Navigation storage unavailable.'); }
    update_post_meta($id, '_muse_project_id', MUSE_PROJECT_ID);
    $content = muse_connector_materialize_header_navigation($source, $id);
    $header_id = wp_insert_post(wp_slash(array('ID' => $header->wp_id ?: 0, 'post_type' => 'wp_template_part', 'post_name' => 'header',
        'post_status' => 'publish', 'post_title' => 'MUSE Store Header', 'post_content' => $content)), true);
    if (is_wp_error($header_id) || !$header_id) { throw new RuntimeException('Header storage unavailable.'); }
    update_post_meta($header_id, '_muse_project_id', MUSE_PROJECT_ID);
    if (is_wp_error(wp_set_object_terms($header_id, 'muse-storefront', 'wp_theme')) ||
        is_wp_error(wp_set_object_terms($header_id, 'header', 'wp_template_part_area'))) {
        throw new RuntimeException('Header scope unavailable.');
    }
}
