<?php
defined('ABSPATH') || exit;
function muse_connector_theme_file_manifest() {
    return array('style.css', 'theme.json', 'functions.php', 'assets/storefront.css', 'parts/header.html', 'parts/footer.html',
        'templates/index.html', 'templates/page.html', 'templates/front-page.html', 'templates/archive-product.html',
        'templates/single-product.html', 'templates/page-cart.html', 'templates/page-checkout.html',
        'templates/page-about.html', 'templates/page-contact.html');
}

function muse_connector_theme_file_hashes() {
    $hashes = array(); $root = realpath(get_stylesheet_directory());
    foreach (muse_connector_theme_file_manifest() as $name) {
        $path = $root . '/' . $name; $resolved = realpath($path);
        $hashes[$name] = $root && $resolved && strpos($resolved, $root . DIRECTORY_SEPARATOR) === 0 &&
            !is_link($path) && is_file($path) && filesize($path) <= 512 * 1024 ? hash_file('sha256', $path) : null;
    }
    return (object) $hashes;
}
function muse_connector_capabilities() {
    $theme = wp_get_theme();
    $missing = array();
    if (!defined('WC_VERSION')) { $missing[] = 'woocommerce'; }
    if ($theme->get_stylesheet() !== 'muse-storefront') { $missing[] = 'owned_block_theme'; }
    if (!function_exists('get_block_templates')) { $missing[] = 'block_templates'; }
    return array(
        'wordpress_version' => get_bloginfo('version'),
        'woocommerce_version' => defined('WC_VERSION') ? WC_VERSION : '',
        'theme_id' => $theme->get_stylesheet(),
        'supported_operations' => array('update_owned_page', 'publish_owned_page', 'publish_product', 'create_product_draft',
            'set_storefront_options', 'install_theme_package', 'set_owned_navigation', 'create_owned_page', 'create_owned_media', 'set_owned_shipping', 'set_owned_store_navigation'),
        'missing_requirements' => $missing,
    );
}
function muse_connector_snapshot() {
    if (!function_exists('wc_get_products') || !function_exists('get_block_templates')) {
        return new WP_Error('muse_unsupported', 'Required platform capability unavailable.', array('status' => 422));
    }
    $posts = get_posts(array('post_type' => 'page', 'post_status' => array('publish', 'draft', 'private'),
                            'numberposts' => 201, 'orderby' => 'ID', 'order' => 'ASC'));
    $items = wc_get_products(array('limit' => 201, 'orderby' => 'ID', 'order' => 'ASC',
                                 'status' => array('publish', 'draft', 'private')));
    if (count($posts) > 200 || count($items) > 200) {
        return new WP_Error('muse_scope_limit', 'Store context exceeds the first-version limit.', array('status' => 422));
    }
    $pages = array();
    foreach ($posts as $page) {
        $pages[] = array('id' => $page->ID, 'slug' => $page->post_name, 'title' => $page->post_title,
                         'content' => $page->post_content, 'status' => $page->post_status,
                         'muse_project_id' => (string) get_post_meta($page->ID, '_muse_project_id', true),
                         'template' => (string) get_post_meta($page->ID, '_wp_page_template', true));
    }
    $products = array();
    foreach ($items as $product) {
        $category_ids = $product->get_category_ids(); $categories = array();
        foreach ($category_ids as $category_id) {
            $term = get_term($category_id, 'product_cat', OBJECT, 'raw');
            if (!$term || is_wp_error($term) || strlen($term->name) > 640) {
                return new WP_Error('muse_category_unavailable', 'Category facts unavailable.', array('status' => 422));
            }
            $categories[] = muse_connector_category_state((int) $category_id);
        }
        $products[] = array('id' => $product->get_id(), 'sku' => $product->get_sku(), 'name' => $product->get_name(),
                            'price' => $product->get_price(), 'stock_quantity' => $product->get_stock_quantity(),
                            'regular_price' => $product->get_regular_price(), 'sale_price' => $product->get_sale_price(),
                            'manage_stock' => (bool) $product->get_manage_stock(), 'stock_status' => $product->get_stock_status(),
                            'backorders' => $product->get_backorders(), 'category_ids' => $category_ids, 'categories' => $categories,
                            'catalog_visibility' => $product->get_catalog_visibility(),
                            'image_id' => (int) $product->get_image_id(), 'gallery_image_ids' => $product->get_gallery_image_ids(),
                            'description' => $product->get_description(), 'status' => $product->get_status(),
                            'type' => $product->get_type(), 'muse_project_id' => (string) $product->get_meta('_muse_project_id'));
    }
    // get_block_templates resolves merchant database overrides as well as theme files.
    $templates = array();
    foreach (array('wp_template', 'wp_template_part') as $type) {
        foreach (get_block_templates(array('theme' => get_stylesheet()), $type) as $template) {
            $templates[] = array('id' => $template->id, 'slug' => $template->slug, 'type' => $type,
                                 'source' => $template->source, 'content' => $template->content);
        }
    }
    usort($templates, function ($a, $b) { return strcmp($a['id'], $b['id']); });
    $theme = wp_get_theme();
    return array(
        'settings' => array_merge(muse_connector_store_setup_state(), array('currency' => get_woocommerce_currency(), 'language' => get_bloginfo('language'),
                            'shipping_configuration' => defined('MUSE_PROJECT_ID') ? muse_connector_shipping_configuration() : null,
                            'permalink_structure' => get_option('permalink_structure'), 'blog_public' => (int) get_option('blog_public'),
                            'home_page_id' => (int) get_option('page_on_front'), 'shop_page_id' => (int) get_option('woocommerce_shop_page_id'),
                            'cart_page_id' => (int) get_option('woocommerce_cart_page_id'), 'checkout_page_id' => (int) get_option('woocommerce_checkout_page_id'),
                            'show_on_front' => (string) get_option('show_on_front'),
                            'coming_soon' => get_option('woocommerce_coming_soon', 'no') === 'yes',
                            'store_pages_only' => get_option('woocommerce_store_pages_only', 'no') === 'yes')),
        'pages' => $pages, 'products' => $products,
        'theme_identity' => array('stylesheet' => $theme->get_stylesheet(), 'version' => $theme->get('Version'),
                                  'effective_templates' => $templates,
                                  'global_styles' => array('styles' => (object) wp_get_global_styles(), 'settings' => (object) wp_get_global_settings()),
                                  'files_sha256' => muse_connector_theme_file_hashes(),
                                  'owned_navigation' => muse_connector_navigation_state()),
    );
}
