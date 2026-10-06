<?php
defined('ABSPATH') || exit;

function muse_connector_page_slug_state($slug) {
    global $wpdb;
    if (!is_string($slug) || preg_match('/\A[a-z][a-z0-9-]{0,63}\z/', $slug) !== 1) {
        throw new InvalidArgumentException('Invalid page slug.');
    }
    $id = $wpdb->get_var($wpdb->prepare("SELECT ID FROM `$wpdb->posts` WHERE post_type='page' AND post_name=%s LIMIT 1", $slug));
    $state = (object) array('slug' => $slug, 'exists' => (bool) $id);
    if ($id) {
        $state->page_id = (int) $id;
        $state->entity_fingerprint = muse_connector_current_fingerprint('page:' . $id);
    }
    return $state;
}

function muse_connector_validate_page_create($operation) {
    muse_connector_exact_keys($operation->payload, array('slug', 'title', 'content', 'template'));
    $payload = $operation->payload;
    $state = muse_connector_page_slug_state($payload->slug);
    muse_connector_plain_text($payload->title, 160, true); muse_connector_plain_text($payload->content, 256 * 1024);
    if ($state->exists || $operation->resource_key !== 'page-slug:' . hash('sha256', $payload->slug) ||
        !in_array($payload->template, array('page', 'page-cart', 'page-checkout', 'page-about', 'page-contact'), true)) {
        throw new InvalidArgumentException('Page creation scope conflict.');
    }
    if ($payload->template !== 'page' && !isset(wp_get_theme()->get_page_templates()[$payload->template])) {
        throw new InvalidArgumentException('Custom page template is not registered.');
    }
}

function muse_connector_create_owned_page($operation) {
    $payload = $operation->payload;
    $id = wp_insert_post(wp_slash(array('post_type' => 'page', 'post_status' => 'draft', 'post_name' => $payload->slug,
        'post_title' => $payload->title, 'post_content' => $payload->content)), true);
    if (is_wp_error($id) || !$id || get_post($id)->post_name !== $payload->slug) { throw new RuntimeException('Page creation outcome unavailable.'); }
    update_post_meta($id, '_muse_project_id', MUSE_PROJECT_ID);
    update_post_meta($id, '_wp_page_template', $payload->template === 'page' ? 'default' : $payload->template);
}
