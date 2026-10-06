<?php
defined('ABSPATH') || exit;

function muse_connector_package_storage() {
    if (!defined('MUSE_PACKAGE_STORAGE')) { throw new InvalidArgumentException('Package storage unavailable.'); }
    $root = realpath(MUSE_PACKAGE_STORAGE); $web = realpath(ABSPATH);
    if (!$root || !$web || !is_dir($root) || is_link(MUSE_PACKAGE_STORAGE) || !is_writable($root) ||
        $root === $web || strpos($root, $web . DIRECTORY_SEPARATOR) === 0) {
        throw new InvalidArgumentException('Separate package storage required.');
    }
    return $root;
}

/** Trusted host mount alias only; never an archive or Agent-provided path. */
function muse_connector_deploy_theme_target() {
    $public_root = get_theme_root('muse-storefront');
    $root = defined('MUSE_DEPLOY_THEME_ROOT') ? MUSE_DEPLOY_THEME_ROOT : $public_root;
    $theme_root = realpath($root); $target = $theme_root . '/muse-storefront';
    $active = get_stylesheet_directory();
    if (!$theme_root || is_link($root) || is_link($target) || is_link($active) || !is_dir($target)) {
        throw new RuntimeException('Owned theme directory unavailable.');
    }
    if (realpath($target) !== realpath($active)) {
        $left = stat($target); $right = stat($active);
        if (!$left || !$right || $left['ino'] <= 0 || $left['dev'] !== $right['dev'] || $left['ino'] !== $right['ino']) {
            throw new RuntimeException('Owned theme directory unavailable.');
        }
    }
    return $target;
}

function muse_connector_transaction_blocks() {
    return array_map(static function ($name) { return 'woocommerce/' . $name; }, array(
        'filled-cart-block', 'empty-cart-block', 'cart-items-block', 'cart-line-items-block', 'cart-totals-block',
        'cart-order-summary-block', 'cart-order-summary-heading-block', 'cart-order-summary-coupon-form-block',
        'cart-order-summary-subtotal-block', 'cart-order-summary-fee-block', 'cart-order-summary-discount-block',
        'cart-order-summary-shipping-block', 'cart-order-summary-taxes-block', 'cart-express-payment-block',
        'proceed-to-checkout-block', 'cart-accepted-payment-methods-block', 'checkout-fields-block',
        'checkout-express-payment-block', 'checkout-contact-information-block', 'checkout-shipping-method-block',
        'checkout-pickup-options-block', 'checkout-shipping-address-block', 'checkout-billing-address-block',
        'checkout-shipping-methods-block', 'checkout-payment-block', 'checkout-additional-information-block',
        'checkout-order-note-block', 'checkout-terms-block', 'checkout-actions-block', 'checkout-totals-block',
        'checkout-order-summary-block', 'checkout-order-summary-cart-items-block', 'checkout-order-summary-subtotal-block',
        'checkout-order-summary-fee-block', 'checkout-order-summary-discount-block', 'checkout-order-summary-coupon-form-block',
        'checkout-order-summary-shipping-block', 'checkout-order-summary-taxes-block', 'cart', 'checkout'));
}

function muse_connector_validate_block_paths($value) {
    if ($value instanceof stdClass) {
        foreach (get_object_vars($value) as $key => $item) {
            if (in_array(strtolower($key), array('url', 'href', 'src'), true) &&
                (!is_string($item) || strpos($item, '..') !== false ||
                 !preg_match('/\A(?:\/(?:[a-zA-Z0-9_-][a-zA-Z0-9_.\/-]*)?|#[a-zA-Z0-9_-]+)\z/', $item))) {
                throw new InvalidArgumentException('Unsupported block attribute path.');
            }
            muse_connector_validate_block_paths($item);
        }
    } elseif (is_array($value)) {
        foreach ($value as $item) { muse_connector_validate_block_paths($item); }
    }
}

function muse_connector_validate_static_file($name, $content) {
    if ($name === 'functions.php') {
        if (!hash_equals('097d1b4055add64bbe148ca4dc3f483fc5b58b3cd62eb6387ba05e1759ffe8f6', hash('sha256', $content))) {
            throw new InvalidArgumentException('Immutable code differs.');
        }
        return;
    }
    if (preg_match('//u', $content) !== 1 || strpos($content, '<?') !== false || strpos($content, "\0") !== false) {
        throw new InvalidArgumentException('Executable content rejected.');
    }
    if (str_ends_with($name, '.css') && preg_match('/\\\\|@import|url\s*\(|expression\s*\(|behavior\s*:/i', $content)) {
        throw new InvalidArgumentException('External CSS rejected.');
    }
    if ($name === 'theme.json') {
        $settings = json_decode($content, false, 32, JSON_THROW_ON_ERROR);
        muse_connector_validate_block_paths($settings);
        if (!($settings instanceof stdClass) || ($settings->version ?? null) !== 3 ||
            preg_match('/https?:|javascript:|data:|url\s*\(|@import|\\\\/i', $content)) {
            throw new InvalidArgumentException('Unsupported theme settings.');
        }
    }
    if (str_ends_with($name, '.html')) {
        if (preg_match('/<!\s*(?!\-\-)/', $content)) { throw new InvalidArgumentException('HTML declarations rejected.'); }
        $dom = new DOMDocument();
        $previous = libxml_use_internal_errors(true);
        try {
            if (!$dom->loadHTML('<?xml encoding="UTF-8">' . $content, LIBXML_NONET)) { throw new InvalidArgumentException('Invalid HTML.'); }
            foreach ($dom->getElementsByTagName('*') as $element) {
                if (!in_array(strtolower($element->tagName), array('html', 'head', 'body', 'main', 'div', 'header', 'footer',
                    'section', 'figure', 'img', 'p', 'span', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br'), true)) {
                    throw new InvalidArgumentException('Unsupported HTML element.');
                }
                foreach ($element->attributes as $attribute) {
                    if (!in_array(strtolower($attribute->name), array('class', 'id', 'role', 'href', 'aria-label', 'data-block-name', 'src', 'alt'), true) ||
                        (in_array($attribute->name, array('src', 'alt'), true) && strtolower($element->tagName) !== 'img') ||
                        ($attribute->name === 'src' && (!preg_match('/\A\/wp-content\/uploads\/muse-owned\/[a-zA-Z0-9_-]{1,100}\/[a-f0-9]{64}\.(?:png|jpg|webp)\z/', $attribute->value))) ||
                        ($attribute->name === 'data-block-name' && !in_array($attribute->value, muse_connector_transaction_blocks(), true)) ||
                        ($attribute->name === 'href' && !preg_match('/\A(?:\/(?:[a-z0-9-][a-z0-9\/-]*)?|#[a-z0-9-]+)\z/', $attribute->value))) {
                        throw new InvalidArgumentException('Unsupported HTML attribute.');
                    }
                }
            }
        } finally { libxml_clear_errors(); libxml_use_internal_errors($previous); }
        $blocks = array('image', 'group', 'heading', 'paragraph', 'post-title', 'post-content', 'site-title', 'template-part',
            'navigation', 'navigation-link', 'query-pagination', 'query-pagination-previous', 'query-pagination-next',
            'query-pagination-numbers', 'woocommerce/product-collection', 'woocommerce/product-template',
            'woocommerce/product-image', 'woocommerce/product-title', 'woocommerce/product-price', 'woocommerce/product-button',
            'woocommerce/product-summary', 'woocommerce/add-to-cart-form', 'woocommerce/product-details', 'woocommerce/cart', 'woocommerce/checkout');
        $blocks = array_merge($blocks, muse_connector_transaction_blocks());
        preg_match_all('/<!--\s*\/?wp:([^\s>]+)(.*?)-->/s', $content, $matches, PREG_SET_ORDER);
        foreach ($matches as $match) {
            if (!in_array($match[1], $blocks, true)) { throw new InvalidArgumentException('Unsupported block.'); }
            $attributes = rtrim(trim($match[2]), '/');
            if (trim($attributes) !== '') {
                $decoded = json_decode(trim($attributes), false, 32, JSON_THROW_ON_ERROR);
                muse_connector_validate_block_paths($decoded);
                if (!($decoded instanceof stdClass) || preg_match('/https?:|javascript:|data:|<|>/i', muse_connector_canonical($decoded))) {
                    throw new InvalidArgumentException('Unsupported block attributes.');
                }
            }
        }
    }
}

/** Read entries individually; never ZipArchive::extractTo or an archive-provided path. */
function muse_connector_validate_theme_package($payload) {
    muse_connector_exact_keys($payload, array('package', 'archive_base64'));
    $metadata = $payload->package;
    muse_connector_exact_keys($metadata, array('code_revision', 'files_manifest', 'package_sha256', 'immutable_code_sha256', 'content_sha256'));
    if (!is_string($metadata->code_revision) || !preg_match('/\A[a-f0-9]{40}\z/', $metadata->code_revision) ||
        !muse_connector_hash($metadata->package_sha256) || !muse_connector_hash($metadata->content_sha256) ||
        $metadata->immutable_code_sha256 !== '097d1b4055add64bbe148ca4dc3f483fc5b58b3cd62eb6387ba05e1759ffe8f6' ||
        !is_string($payload->archive_base64) || strlen($payload->archive_base64) > 7 * 1024 * 1024 ||
        !is_array($metadata->files_manifest)) { throw new InvalidArgumentException('Invalid package.'); }
    $archive = base64_decode($payload->archive_base64, true);
    if ($archive === false || strlen($archive) > 5 * 1024 * 1024 ||
        !hash_equals($metadata->package_sha256, hash('sha256', $archive))) { throw new InvalidArgumentException('Invalid archive.'); }
    $temporary = tempnam(muse_connector_package_storage(), 'muse-zip-');
    if ($temporary === false) { throw new RuntimeException('Temporary storage unavailable.'); }
    $zip = new ZipArchive(); $opened = false;
    try {
        chmod($temporary, 0600);
        if (file_put_contents($temporary, $archive) !== strlen($archive) || $zip->open($temporary) !== true) {
            throw new InvalidArgumentException('Invalid archive.');
        }
        $opened = true; $allowed = muse_connector_theme_file_manifest(); $files = array(); $size = 0;
        if ($zip->numFiles !== count($allowed)) { throw new InvalidArgumentException('Archive manifest differs.'); }
        for ($index = 0; $index < $zip->numFiles; $index++) {
            $stat = $zip->statIndex($index); $name = substr($stat['name'], strlen('muse-storefront/'));
            $zip->getExternalAttributesIndex($index, $system, $attributes);
            $mode = ($attributes >> 16) & 0170000;
            if ($stat['name'] !== 'muse-storefront/' . $name || !in_array($name, $allowed, true) || isset($files[$name]) ||
                $stat['size'] > 512 * 1024 || !in_array($stat['comp_method'], array(0, 8), true) ||
                ($stat['encryption_method'] ?? 0) !== 0 || ($system === ZipArchive::OPSYS_UNIX && $mode === 0120000)) {
                throw new InvalidArgumentException('Unsupported archive entry.');
            }
            $size += $stat['size']; if ($size > 5 * 1024 * 1024) { throw new InvalidArgumentException('Archive size exceeded.'); }
            $content = $zip->getFromIndex($index);
            if ($content === false || strlen($content) !== $stat['size']) { throw new InvalidArgumentException('Archive content differs.'); }
            muse_connector_validate_static_file($name, $content); $files[$name] = $content;
        }
        ksort($files, SORT_STRING); $manifest = array();
        foreach ($files as $name => $content) {
            $manifest[] = (object) array('path' => $name, 'sha256' => hash('sha256', $content), 'bytes' => strlen($content));
        }
        if (muse_connector_canonical($manifest) !== muse_connector_canonical($metadata->files_manifest)) {
            throw new InvalidArgumentException('File manifest differs.');
        }
        return $files;
    } finally {
        if ($opened) { $zip->close(); }
        if (is_file($temporary)) { unlink($temporary); }
    }
}

function muse_connector_validate_theme_operation($operation) {
    if ($operation->resource_key !== 'theme:muse-storefront' || get_stylesheet() !== 'muse-storefront') {
        throw new InvalidArgumentException('Only the active owned theme is supported.');
    }
    muse_connector_validate_theme_package($operation->payload);
    $slugs = array_map(static function ($path) { return basename($path, '.html'); },
        array_filter(muse_connector_theme_file_manifest(), static function ($path) { return str_ends_with($path, '.html'); }));
    foreach (array('wp_template', 'wp_template_part') as $type) {
        foreach (get_block_templates(array('theme' => 'muse-storefront'), $type) as $template) {
            if (in_array($template->slug, $slugs, true) && $template->source !== 'theme' &&
                !($type === 'wp_template_part' && $template->slug === 'header' && $template->wp_id &&
                    get_post_meta($template->wp_id, '_muse_project_id', true) === MUSE_PROJECT_ID)) {
                throw new InvalidArgumentException('Merchant template override must be merged first.');
            }
        }
    }
}

function muse_connector_write_package_file($path, $content) {
    $handle = fopen($path, 'x+b');
    if (!$handle) { throw new RuntimeException('Package storage unavailable.'); }
    try {
        chmod($path, 0600);
        if (fwrite($handle, $content) !== strlen($content) || !fflush($handle) || !fsync($handle)) {
            throw new RuntimeException('Package storage unavailable.');
        }
    } finally { fclose($handle); }
}

/** Filesystem swaps cannot join the SQL transaction; preserve a private journal and backup. */
function muse_connector_install_theme_package($operation) {
    $files = muse_connector_validate_theme_package($operation->payload);
    $root = muse_connector_package_storage();
    if (count(glob($root . '/op-*', GLOB_ONLYDIR)) >= 100) { throw new RuntimeException('Package retention limit reached.'); }
    $journal = $root . '/op-' . hash('sha256', MUSE_CONNECTION_ID . ':' . MUSE_ENVIRONMENT . ':' . $operation->operation_id);
    if (!mkdir($journal, 0700)) { throw new RuntimeException('Package journal unavailable.'); }
    $stage = $journal . '/staged';
    if (!mkdir($stage, 0700)) { throw new RuntimeException('Package stage unavailable.'); }
    foreach ($files as $name => $content) {
        $directory = dirname($stage . '/' . $name);
        if (!is_dir($directory) && !mkdir($directory, 0700, true)) { throw new RuntimeException('Package stage unavailable.'); }
        muse_connector_write_package_file($stage . '/' . $name, $content);
    }
    $target = muse_connector_deploy_theme_target();
    muse_connector_write_package_file($journal . '/journal.json', muse_connector_canonical((object) array(
        'operation_digest' => hash('sha256', muse_connector_canonical($operation)),
        'expected_fingerprint' => $operation->expected_fingerprint, 'files_manifest' => $operation->payload->package->files_manifest)));
    wp_cache_flush(); wp_clean_themes_cache();
    if (!hash_equals($operation->expected_fingerprint, muse_connector_current_fingerprint('theme:muse-storefront'))) {
        throw new RuntimeException('Theme changed during preparation.');
    }
    if (!rename($target, $journal . '/previous')) { throw new RuntimeException('Theme swap unavailable.'); }
    if (!rename($stage, $target)) {
        if (!file_exists($target)) { rename($journal . '/previous', $target); }
        throw new RuntimeException('Theme swap outcome requires reconciliation.');
    }
    foreach ($files as $name => $content) {
        if (!hash_equals(hash('sha256', $content), hash_file('sha256', $target . '/' . $name))) {
            throw new RuntimeException('Installed file differs.');
        }
        // Deployed public theme files need normal read permissions; package journals stay private.
        chmod($target . '/' . $name, 0644);
    }
    foreach (array($target, $target . '/assets', $target . '/parts', $target . '/templates') as $directory) { chmod($directory, 0755); }
    wp_cache_flush(); wp_clean_themes_cache();
    // The same request already resolved old global styles for its precondition.
    // Reset the resolver's in-process cache before producing the effect receipt.
    if (class_exists('WP_Theme_JSON_Resolver') && method_exists('WP_Theme_JSON_Resolver', 'clean_cached_data')) {
        // Supported locked WordPress retains parsed theme files even after clean_cached_data().
        // This fixed subclass only clears that cache; it cannot read or execute merchant code.
        if (property_exists('WP_Theme_JSON_Resolver', 'theme_json_file_cache')) {
            if (!class_exists('MUSE_Theme_JSON_Cache_Reset', false)) {
                class MUSE_Theme_JSON_Cache_Reset extends WP_Theme_JSON_Resolver {
                    public static function clear_parsed_files() { static::$theme_json_file_cache = array(); }
                }
            }
            MUSE_Theme_JSON_Cache_Reset::clear_parsed_files();
        }
        WP_Theme_JSON_Resolver::clean_cached_data();
    }
    if (function_exists('wp_clean_theme_json_cache')) { wp_clean_theme_json_cache(); }
}
