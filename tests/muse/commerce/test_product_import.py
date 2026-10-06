import hashlib
import io

import pytest
from PIL import Image

from muse.commerce.models import MediaInput
from muse.commerce.products import parse_products, validate_media

HEADER = 'sku,name,price,currency,stock,category,description,image_names\n'


def csv(*rows):
    return (HEADER + '\n'.join(rows)).encode('utf-8-sig')


def test_five_products_preserve_exact_decimal_and_merchant_facts():
    result = parse_products(csv(*(f' SKU{i} ,Cup {i},19.990000,USD,5,Cups,Handmade,' for i in range(5))), [], 'USD')
    assert not result.errors
    assert len(result.drafts) == 5
    assert str(result.drafts[0].price) == '19.990000'
    assert result.drafts[0].sku == 'SKU0'
    assert result.drafts[0].source_facts['description'] == 'Handmade'


@pytest.mark.parametrize('row,field', [
    (',Cup,10,USD,1,,,', 'sku'), ('SKU,,10,USD,1,,,', 'name'),
    ('SKU,Cup,-1,USD,1,,,', 'price'), ('SKU,Cup,NaN,USD,1,,,', 'price'),
    ('SKU,Cup,1e3,USD,1,,,', 'price'), ('SKU,Cup,10,CNY,1,,,', 'currency'),
    ('SKU,Cup,10,USD,-1,,,', 'stock'), ('SKU,Cup,10,USD,1.0,,,', 'stock'),
    ('SKU,Cup,10,USD,99999999999999,,,', 'stock'),
    ('=NOW(),Cup,10,USD,1,,,', 'sku'), ('SKU,@formula,10,USD,1,,,', 'name'),
    ('SKU,Cup,10,USD,1,,,https://other.example/image.png', 'image_names'),
])
def test_invalid_rows_return_field_errors_and_no_publishable_drafts(row, field):
    result = parse_products(csv(row), [], 'USD')
    assert result.drafts == []
    assert any(issue.field == field and issue.row == 2 for issue in result.errors)


def test_duplicates_and_batch_scope_are_rejected_before_plan_creation():
    result = parse_products(csv(' SKU ,Cup,10,USD,1,,,', 'sku,Cup,10,USD,1,,,'), [], 'USD')
    assert result.drafts == [] and result.errors[0].code == 'DUPLICATE_SKU'
    result = parse_products(csv(*(f'SKU{i},Cup,10,USD,1,,,' for i in range(21))), [], 'USD')
    assert result.drafts == [] and result.errors[0].code == 'BATCH_LIMIT'
    assert parse_products(csv('sku,Cup,10,USD,1,,,'), [], 'USD', existing_skus=[' SKU ']).errors[0].code == 'SKU_CONFLICT'


@pytest.mark.parametrize('data', [b'not,csv', b'\xff', HEADER.encode(), (HEADER + 'SKU,Cup,10,USD,1,,,extra,extra').encode(),
                                     b'sku,name,price,currency,stock,category,description,image_names,image_names\n'])
def test_malformed_input_is_not_silently_repaired(data):
    result = parse_products(data, [], 'USD')
    assert result.errors and result.drafts == []


def image():
    buffer = io.BytesIO()
    Image.new('RGB', (4, 4)).save(buffer, format='PNG')
    return buffer.getvalue()


def test_uploaded_image_is_decoded_mime_checked_and_hash_bound():
    data = image()
    media = validate_media('cup.png', 'image/png', data, 'artifact-1')
    assert media.sha256 == hashlib.sha256(data).hexdigest()
    result = parse_products(csv('SKU,Cup,10,USD,1,,,cup.png'), [media], 'USD')
    assert not result.errors and result.drafts[0].media_refs == ['artifact-1']
    for name, mime, data in [('cup.png', 'image/png', b'<svg/>'), ('../cup.png', 'image/png', image()),
                             ('cup.jpeg', 'image/jpeg', image()), ('cup.png', 'image/png', image()[:20])]:
        with pytest.raises(ValueError):
            validate_media(name, mime, data, 'artifact-1')


def test_duplicate_images_or_more_than_five_do_not_reach_a_plan():
    media = validate_media('cup.png', 'image/png', image(), 'artifact-1')
    second = media.model_copy(update={'name': 'cup2.png', 'artifact_ref': 'artifact-2'})
    assert parse_products(csv('SKU,Cup,10,USD,1,,,cup.png|cup2.png'), [media, second], 'USD').errors
    assert parse_products(csv('SKU,Cup,10,USD,1,,,cup.png|cup.png'), [media], 'USD').errors
    images = [MediaInput(name=f'{i}.png', mime_type='image/png', sha256=str(i)*64,
                        byte_size=5, artifact_ref=f'a{i}') for i in range(6)]
    assert parse_products(csv('SKU,Cup,10,USD,1,,,0.png|1.png|2.png|3.png|4.png|5.png'), images, 'USD').errors
