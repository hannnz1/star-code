<?php
/** Trusted CLI, new empty reference database only. Never a REST/Agent tool. */
function muse_reference_move_default_pages() {
    // Only called immediately after installing a previously empty database.
    // Preserve generated pages as drafts instead of overwriting or deleting.
    $pages = array();
    foreach (array('shop', 'cart', 'checkout') as $kind) {
        $id = wc_get_page_id($kind); $page = $id > 0 ? get_post($id) : null;
        if (!$page || $page->post_type !== 'page' || $page->post_name !== $kind) {
            throw new RuntimeException();
        }
        $pages[$kind] = $id;
    }
    foreach ($pages as $kind => $id) {
        $result = wp_update_post(array('ID' => $id, 'post_name' => 'muse-reference-default-' . $kind,
            'post_status' => 'draft'), true);
        if (is_wp_error($result) || $result !== $id) { throw new RuntimeException(); }
    }
}
ini_set('display_errors', '0');
ini_set('log_errors', '0');
try {
    $raw = stream_get_contents(STDIN, 65537);
    if (strlen($raw) > 65536) { throw new RuntimeException(); }
    $input = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    $keys = array('job_id', 'project_id', 'connection_id', 'port', 'wordpress_version', 'woocommerce_version',
        'currency', 'language', 'admin_password', 'service_password', 'execution_secret');
    $actual = is_array($input) ? array_keys($input) : array(); sort($keys); sort($actual);
    if ($actual !== $keys || !is_int($input['port']) || $input['port'] < 1024 || $input['port'] > 65535) { throw new RuntimeException(); }
    foreach (array('job_id' => '/^[a-f0-9]{32}$/D', 'project_id' => '/^[a-zA-Z0-9_-]{1,100}$/D',
        'connection_id' => '/^[a-zA-Z0-9_-]{1,100}$/D', 'wordpress_version' => '/^\d+\.\d+(?:\.\d+)?$/D',
        'woocommerce_version' => '/^\d+\.\d+(?:\.\d+)?$/D', 'currency' => '/^[A-Z]{3}$/D',
        'language' => '/^[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{2,8})*$/D') as $key => $pattern) {
        if (!is_string($input[$key]) || !preg_match($pattern, $input[$key])) { throw new RuntimeException(); }
    }
    foreach (array('admin_password', 'service_password', 'execution_secret') as $key) {
        if (!is_string($input[$key]) || strlen($input[$key]) < 32 || strlen($input[$key]) > 256 ||
            !preg_match('/^[a-zA-Z0-9_-]+$/D', $input[$key])) { throw new RuntimeException(); }
    }
    $root = realpath($argv[1] ?? '');
    if (!$root || is_link($argv[1]) || !is_file($root . '/wp-load.php')) { throw new RuntimeException(); }
    define('WP_INSTALLING', true);
    define('MUSE_ENVIRONMENT', 'staging'); define('MUSE_REFERENCE_JOB', $input['job_id']);
    define('MUSE_PROJECT_ID', $input['project_id']); define('MUSE_CONNECTION_ID', $input['connection_id']);
    define('MUSE_TARGET_URL', 'http://127.0.0.1:' . $input['port']);
    define('MUSE_EXECUTION_SECRET', $input['execution_secret']);
    // Private sibling volume subpath: same filesystem for atomic theme swaps,
    // outside the Apache document root. Production storage is separate.
    define('MUSE_PACKAGE_STORAGE', '/var/muse-volume/packages');
    define('MUSE_DEPLOY_THEME_ROOT', '/var/muse-volume/site/wp-content/themes');
    // Buffer CMS diagnostics: even failure output must not contain credentials.
    ob_start();
    require $root . '/wp-load.php';
    if (is_blog_installed()) { throw new RuntimeException(); }
    require_once ABSPATH . 'wp-admin/includes/upgrade.php';
    require_once ABSPATH . 'wp-admin/includes/plugin.php';
    if (get_bloginfo('version') !== $input['wordpress_version']) { throw new RuntimeException(); }
    $installed = wp_install('MUSE disposable preview', 'muse_reference_admin', 'nobody@example.invalid',
        0, '', $input['admin_password'], 'en_US');
    if (!is_array($installed) || empty($installed['user_id'])) { throw new RuntimeException(); }
    wp_set_current_user((int) $installed['user_id']);
    foreach (array('woocommerce/woocommerce.php', 'muse-connector/muse-connector.php') as $plugin) {
        $result = activate_plugin($plugin, '', false, true);
        if (is_wp_error($result)) { throw new RuntimeException(); }
    }
    if (!defined('WC_VERSION') || WC_VERSION !== $input['woocommerce_version']) { throw new RuntimeException(); }
    WC_Install::install();
    muse_reference_move_default_pages();
    muse_connector_register_service_role();
    $service = wp_insert_user(array('user_login' => 'muse_reference_service', 'user_pass' => $input['service_password'],
        'user_email' => 'service@example.invalid', 'role' => 'muse_connector_service'));
    if (is_wp_error($service) || !is_int($service)) { throw new RuntimeException(); }
    define('MUSE_SERVICE_USER_ID', $service);
    $application = WP_Application_Passwords::create_new_application_password($service, array('name' => 'MUSE reference job ' . $input['job_id']));
    if (is_wp_error($application)) { throw new RuntimeException(); }
    foreach (array('home' => MUSE_TARGET_URL, 'siteurl' => MUSE_TARGET_URL, 'blog_public' => 0,
        'permalink_structure' => '/%postname%/',
        'WPLANG' => str_replace('-', '_', $input['language']), 'woocommerce_currency' => $input['currency'],
        'woocommerce_default_country' => 'US:CA', 'woocommerce_store_address' => '1 Fixture Street',
        'woocommerce_store_city' => 'Beverly Hills', 'woocommerce_store_postcode' => '90210',
        'woocommerce_calc_taxes' => 'no', 'woocommerce_default_customer_address' => 'base',
        'woocommerce_shipping_cost_requires_address' => 'no', 'woocommerce_coming_soon' => 'no',
        'woocommerce_store_pages_only' => 'no', 'muse_shipping_confirmed' => 'yes', 'muse_payment_confirmed' => 'yes') as $key => $value) {
        update_option($key, $value);
    }
    foreach (WC()->payment_gateways()->payment_gateways() as $id => $gateway) {
        $settings = get_option('woocommerce_' . $id . '_settings', array());
        $settings['enabled'] = $id === 'cod' ? 'yes' : 'no';
        if ($id === 'cod') { $settings['enable_for_virtual'] = 'yes'; $settings['enable_for_methods'] = array(); }
        update_option('woocommerce_' . $id . '_settings', $settings);
    }
    $zone = WC_Shipping_Zones::get_zone_by('zone_id', 0);
    $instance = $zone->add_shipping_method('flat_rate');
    if (!$instance) { throw new RuntimeException(); }
    update_option('woocommerce_flat_rate_' . $instance . '_settings', array('enabled' => 'yes',
        'title' => 'Disposable test shipping', 'cost' => '5', 'tax_status' => 'none'));
    switch_theme('muse-storefront');
    // The connector uses /wp-json routes. An empty permalink structure makes
    // WordPress canonicalize these as page URLs instead of REST requests.
    // Apache's fixed image supplies .htaccess; regenerate database rules only.
    flush_rewrite_rules(false);
    if (!function_exists('muse_staging_fixture_create')) { throw new RuntimeException(); }
    muse_staging_fixture_create();
    $config = "<?php\n";
    foreach (array('MUSE_ENVIRONMENT', 'MUSE_REFERENCE_JOB', 'MUSE_PROJECT_ID', 'MUSE_CONNECTION_ID',
        'MUSE_TARGET_URL', 'MUSE_EXECUTION_SECRET', 'MUSE_PACKAGE_STORAGE', 'MUSE_DEPLOY_THEME_ROOT', 'MUSE_SERVICE_USER_ID') as $name) {
        $config .= 'if (!defined(' . var_export($name, true) . ')) { define(' . var_export($name, true) . ', ' . var_export(constant($name), true) . "); }\n";
    }
    // Must load before the safety MU plugin on every subsequent request.
    $path = WP_CONTENT_DIR . '/mu-plugins/000-muse-reference-config.php';
    $file = fopen($path, 'x');
    if (!$file || fwrite($file, $config) !== strlen($config)) { throw new RuntimeException(); }
    fclose($file); chmod($path, 0600);
    while (ob_get_level()) { ob_end_clean(); }
    // Only the trusted runner consumes this private stdout; never log it.
    echo json_encode(array('service_user_id' => $service, 'username' => 'muse_reference_service',
        'application_password' => $application[0], 'job_id' => $input['job_id']), JSON_THROW_ON_ERROR);
} catch (Throwable $error) {
    while (ob_get_level()) { ob_end_clean(); }
    fwrite(STDERR, "REFERENCE_BOOTSTRAP_REJECTED\n"); exit(2);
}
