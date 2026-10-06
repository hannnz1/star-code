<?php
defined('ABSPATH') || exit;

function muse_connector_receipt_table() {
    global $wpdb;
    return $wpdb->prefix . 'muse_operation_receipts';
}

function muse_connector_install_receipts() {
    global $wpdb;
    if (get_option('muse_connector_schema_version') === '1') { return; }
    $table = muse_connector_receipt_table();
    $result = $wpdb->query("CREATE TABLE IF NOT EXISTS `$table` (
        connection_id varchar(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        environment varchar(12) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        operation_id varchar(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        project_id varchar(100) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        operation_digest char(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        resource_key varchar(200) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        state varchar(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        fingerprint char(64) CHARACTER SET ascii COLLATE ascii_bin NULL,
        PRIMARY KEY (connection_id, environment, operation_id),
        KEY unresolved_resource (connection_id, environment, resource_key, state)
    ) ENGINE=InnoDB");
    if ($result !== false) { update_option('muse_connector_schema_version', '1', false); }
}

function muse_connector_get_receipt($operation_id) {
    global $wpdb;
    $table = muse_connector_receipt_table();
    return $wpdb->get_row($wpdb->prepare("SELECT project_id,connection_id,environment,operation_id,
        operation_digest,resource_key,state,fingerprint FROM `$table`
        WHERE connection_id=%s AND environment=%s AND project_id=%s AND operation_id=%s",
        MUSE_CONNECTION_ID, MUSE_ENVIRONMENT, MUSE_PROJECT_ID, $operation_id), ARRAY_A);
}

function muse_connector_receipt_route($request) {
    $receipt = muse_connector_get_receipt($request['operation_id']);
    if (!$receipt) { return new WP_Error('muse_not_found', 'Receipt unavailable.', array('status' => 404)); }
    return $receipt;
}

function muse_connector_db_query($query) {
    global $wpdb;
    $result = $wpdb->query($query);
    if ($result === false) { throw new RuntimeException('Database operation unavailable.'); }
    return $result;
}
