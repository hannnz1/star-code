<?php
$input = json_decode(stream_get_contents(STDIN), true, 32, JSON_THROW_ON_ERROR);
define('ABSPATH', __DIR__); define('MUSE_ENVIRONMENT', 'staging');
define('MUSE_REFERENCE_JOB', str_repeat('a', 32)); define('MUSE_PROJECT_ID', 'project');
define('MUSE_CONNECTION_ID', 'ref-' . MUSE_REFERENCE_JOB);
function add_filter(...$args) {} function add_action(...$args) {}
class WP_Error { public $code; function __construct($code, $message) {$this->code=$code;} }
$products=array(); $options=array();
function wc_get_product_id_by_sku($sku) {global $products; foreach ($products as $id=>$p) {if($p->get_sku()===$sku)return $id;} return 0;}
function wc_get_product($id) {global $products; return $products[$id] ?? false;}
function update_option($key,$value,...$args) {global $options; $options[$key]=$value;}
function get_option($key) {global $options; return $options[$key] ?? false;}
function get_woocommerce_currency() {return 'USD';}
function wc_format_decimal($value,$places) {return number_format((float)$value,$places,'.','');}
class WC_Product_Simple {
    public $data=array(), $metadata=array();
    function __call($name,$args) {
        if(str_starts_with($name,'set_')) {$this->data[substr($name,4)]=$args[0];return;}
        if(str_starts_with($name,'get_')) {return $this->data[substr($name,4)] ?? null;}
        throw new RuntimeException();
    }
    function get_type() {return 'simple';} function get_price() {return $this->data['regular_price'];}
    function is_virtual() {return $this->data['virtual'];}
    function update_meta_data($k,$v) {$this->metadata[$k]=$v;} function get_meta($k) {return $this->metadata[$k] ?? '';}
    function save() {global $products; $products[12]=$this; return 12;}
}
require $argv[1];
try {
    muse_staging_fixture_create();
    if(isset($input['change'])) { $products[12]->data[$input['change']]=$input['value']; }
    if(!empty($input['duplicate'])) {muse_staging_fixture_create();}
    $result=muse_staging_fixture_read();
    echo json_encode($result instanceof WP_Error ? array('error'=>$result->code) : $result);
} catch(Throwable $error) {echo json_encode(array('error'=>'REJECTED'));}
