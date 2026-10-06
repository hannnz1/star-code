<?php
defined('ABSPATH') || exit;

/** Validate fixed image bytes, never a URL, host filename or overwrite flag. */
function muse_connector_validate_media_operation($operation) {
    muse_connector_exact_keys($operation->payload, array('media_ref', 'image', 'content_base64'));
    $payload = $operation->payload; $image = $payload->image;
    muse_connector_exact_keys($image, array('sha256', 'mime_type', 'byte_size', 'width', 'height'));
    if (!muse_connector_hash($image->sha256) || !muse_connector_hash($payload->media_ref) ||
        $payload->media_ref !== hash('sha256', muse_connector_canonical(array(MUSE_PROJECT_ID, 'image', $image->sha256))) ||
        !in_array($image->mime_type, array('image/png', 'image/jpeg', 'image/webp'), true) ||
        !is_int($image->byte_size) || $image->byte_size <= 0 || $image->byte_size > 10 * 1024 * 1024 ||
        !is_int($image->width) || !is_int($image->height) || $image->width <= 0 || $image->height <= 0 ||
        $image->width > 20000000 || $image->height > 20000000 || $image->width * $image->height > 20000000 ||
        !is_string($payload->content_base64) || strlen($payload->content_base64) > 14 * 1024 * 1024 ||
        $operation->resource_key !== 'media-sha256:' . $image->sha256) {
        throw new InvalidArgumentException('Invalid scoped image.');
    }
    $content = base64_decode($payload->content_base64, true);
    if ($content === false || base64_encode($content) !== $payload->content_base64 || strlen($content) !== $image->byte_size ||
        !hash_equals($image->sha256, hash('sha256', $content))) { throw new InvalidArgumentException('Image bytes differ.'); }
    $size = @getimagesizefromstring($content);
    if (!$size || $size[0] !== $image->width || $size[1] !== $image->height || $size['mime'] !== $image->mime_type) {
        throw new InvalidArgumentException('Image dimensions or format differ.');
    }
    return $content;
}

function muse_connector_media_root($create = false) {
    if (!muse_connector_identity(MUSE_PROJECT_ID) || is_link(WP_CONTENT_DIR)) { throw new RuntimeException('Image scope unavailable.'); }
    $content = realpath(WP_CONTENT_DIR);
    if (!$content || $content !== realpath(ABSPATH . 'wp-content')) { throw new RuntimeException('Fixed content root required.'); }
    $root = $content . DIRECTORY_SEPARATOR . 'uploads';
    if ($create && !file_exists($root) && !mkdir($root, 0755)) { throw new RuntimeException('Image storage unavailable.'); }
    $uploads = wp_upload_dir(null, false);
    if (is_link($root) || !is_dir($root) || realpath($uploads['basedir']) !== realpath($root)) {
        throw new RuntimeException('Fixed uploads root required.');
    }
    return realpath($root);
}

function muse_connector_media_record($id) {
    $post = get_post($id);
    $sha = get_post_meta($id, '_muse_media_sha256', true);
    $ref = get_post_meta($id, '_muse_media_ref', true);
    if (!$post || $post->post_type !== 'attachment' || get_post_meta($id, '_muse_project_id', true) !== MUSE_PROJECT_ID ||
        !muse_connector_hash($sha) || $ref !== hash('sha256', muse_connector_canonical(array(MUSE_PROJECT_ID, 'image', $sha)))) {
        throw new RuntimeException('Owned image unavailable.');
    }
    $formats = array('image/png' => 'png', 'image/jpeg' => 'jpg', 'image/webp' => 'webp');
    if (!isset($formats[$post->post_mime_type])) { throw new RuntimeException('Image format changed.'); }
    $root = muse_connector_media_root();
    $directory = $root . DIRECTORY_SEPARATOR . 'muse-owned' . DIRECTORY_SEPARATOR . MUSE_PROJECT_ID;
    $file = $directory . DIRECTORY_SEPARATOR . $sha . '.' . $formats[$post->post_mime_type];
    if (is_link(dirname($directory)) || is_link($directory) || is_link($file) || !is_file($file) ||
        realpath(get_attached_file($id, true)) !== realpath($file) || filesize($file) > 10 * 1024 * 1024 ||
        !hash_equals($sha, hash_file('sha256', $file))) { throw new RuntimeException('Image file changed.'); }
    $size = @getimagesize($file);
    if (!$size || $size['mime'] !== $post->post_mime_type || $size[0] * $size[1] > 20000000) { throw new RuntimeException('Image facts changed.'); }
    return (object) array('id' => (int) $id, 'media_ref' => $ref, 'sha256' => $sha, 'mime_type' => $post->post_mime_type,
        'byte_size' => filesize($file), 'width' => $size[0], 'height' => $size[1], 'muse_project_id' => MUSE_PROJECT_ID,
        'status' => $post->post_status, 'parent_id' => (int) $post->post_parent, 'title' => $post->post_title,
        'alt' => (string) get_post_meta($id, '_wp_attachment_image_alt', true));
}

function muse_connector_media_state($sha) {
    if (!muse_connector_hash($sha)) { throw new InvalidArgumentException('Invalid image hash.'); }
    $posts = get_posts(array('post_type' => 'attachment', 'post_status' => array('inherit', 'draft', 'publish', 'private', 'trash'),
        'numberposts' => 2, 'meta_query' => array(array('key' => '_muse_project_id', 'value' => MUSE_PROJECT_ID),
        array('key' => '_muse_media_sha256', 'value' => $sha))));
    if (count($posts) > 1) { throw new RuntimeException('Ambiguous owned image.'); }
    $state = (object) array('sha256' => $sha, 'exists' => count($posts) === 1);
    if ($state->exists) { $state->attachment = muse_connector_media_record($posts[0]->ID); }
    return $state;
}

function muse_connector_media_exclusive_write($path, $content, $mode) {
    if (is_link($path) || file_exists($path)) { throw new RuntimeException('Image storage already exists.'); }
    $handle = fopen($path, 'xb');
    if (!$handle) { throw new RuntimeException('Image storage unavailable.'); }
    try {
        if (fwrite($handle, $content) !== strlen($content) || !fflush($handle) || !fsync($handle)) {
            throw new RuntimeException('Image storage outcome unavailable.');
        }
        if (!chmod($path, $mode)) { throw new RuntimeException('Image storage permissions unavailable.'); }
    } finally { fclose($handle); }
}

function muse_connector_create_owned_media($operation) {
    $content = muse_connector_validate_media_operation($operation);
    $image = $operation->payload->image; $sha = $image->sha256;
    if (muse_connector_media_state($sha)->exists) { throw new MUSE_Operation_Conflict('Image already exists.'); }
    $owned = get_posts(array('post_type' => 'attachment', 'post_status' => array('inherit', 'draft', 'publish', 'private', 'trash'),
        'numberposts' => 101, 'meta_key' => '_muse_project_id', 'meta_value' => MUSE_PROJECT_ID));
    $total = $image->byte_size;
    if (count($owned) >= 100) { throw new MUSE_Operation_Conflict('Image count limit reached.'); }
    foreach ($owned as $post) { $total += muse_connector_media_record($post->ID)->byte_size; }
    if ($total > 100 * 1024 * 1024) { throw new MUSE_Operation_Conflict('Image size limit reached.'); }
    $journal = muse_connector_package_storage() . DIRECTORY_SEPARATOR . 'media-' . $operation->operation_id . '.json';
    muse_connector_media_exclusive_write($journal, muse_connector_canonical((object) array('image' => $image,
        'operation_id' => $operation->operation_id, 'media_ref' => $operation->payload->media_ref)), 0600);
    $root = muse_connector_media_root(true);
    foreach (array($root . DIRECTORY_SEPARATOR . 'muse-owned',
                   $root . DIRECTORY_SEPARATOR . 'muse-owned' . DIRECTORY_SEPARATOR . MUSE_PROJECT_ID) as $directory) {
        if (is_link($directory) || (file_exists($directory) && !is_dir($directory)) ||
            (!file_exists($directory) && !mkdir($directory, 0755))) { throw new RuntimeException('Image directory unavailable.'); }
    }
    $extension = array('image/png' => 'png', 'image/jpeg' => 'jpg', 'image/webp' => 'webp')[$image->mime_type];
    $relative = 'muse-owned/' . MUSE_PROJECT_ID . '/' . $sha . '.' . $extension;
    $file = $root . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $relative);
    muse_connector_media_exclusive_write($file, $content, 0644);
    do_action('muse_connector_media_file_written', $sha);
    $id = wp_insert_attachment(wp_slash(array('post_title' => 'MUSE image ' . $sha, 'post_status' => 'inherit',
        'post_mime_type' => $image->mime_type, 'post_content' => '', 'post_parent' => 0)), $file, 0, true);
    if (is_wp_error($id) || !$id) { throw new RuntimeException('Attachment outcome unavailable.'); }
    // Store the fixed relative path explicitly. WP's post meta unslashing may
    // strip Windows backslashes from the absolute filename passed above.
    update_post_meta($id, '_wp_attached_file', $relative);
    update_post_meta($id, '_muse_project_id', MUSE_PROJECT_ID);
    update_post_meta($id, '_muse_media_sha256', $sha);
    update_post_meta($id, '_muse_media_ref', $operation->payload->media_ref);
    update_post_meta($id, '_wp_attachment_image_alt', '');
    wp_update_attachment_metadata($id, array('width' => $image->width, 'height' => $image->height, 'file' => $relative,
        'sizes' => array(), 'image_meta' => array()));
    muse_connector_media_record($id);
}
