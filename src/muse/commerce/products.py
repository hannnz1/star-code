"""Strict merchant input parsing. A rejected batch cannot become a publish plan."""
import csv
import hashlib
import io
import re
import warnings
from decimal import Decimal

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from muse.commerce.models import (
    ImportIssue,
    MediaInput,
    ProductDraft,
    ProductImportResult,
)

COLUMNS = ['sku', 'name', 'price', 'currency', 'stock', 'category', 'description', 'image_names']
MAX_CSV_BYTES = 1024 * 1024


def issue(row, field, code, message):
    return ImportIssue(row=row, field=field, code=code, message=message)


def validate_media(name: str, mime_type: str, data: bytes, artifact_ref: str) -> MediaInput:
    formats = {'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/webp': 'WEBP'}
    if (not name.strip() or len(name) > 200 or '/' in name or '\\' in name or name in {'.', '..'}
            or mime_type not in formats or not 0 < len(data) <= 10 * 1024 * 1024
            or not re.fullmatch(r'[a-zA-Z0-9_-]{1,200}', artifact_ref)):
        raise ValueError('Invalid uploaded image')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as picture:
                if picture.format != formats[mime_type] or picture.width * picture.height > 20_000_000:
                    raise ValueError()
                if getattr(picture, 'n_frames', 1) != 1:
                    raise ValueError()
                picture.verify()
            # Decode as well as verify headers; truncated images are not accepted.
            with Image.open(io.BytesIO(data)) as picture:
                picture.load()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Invalid uploaded image') from None
    return MediaInput(name=name.strip(), mime_type=mime_type, sha256=hashlib.sha256(data).hexdigest(),
                      byte_size=len(data), artifact_ref=artifact_ref)


def parse_products(csv_bytes: bytes, images: list[MediaInput], currency: str, *, existing_skus=()) -> ProductImportResult:
    if len(csv_bytes) > MAX_CSV_BYTES or not re.fullmatch(r'[A-Z]{3}', currency):
        return ProductImportResult(errors=[issue(0, 'csv', 'INPUT_INVALID', 'Invalid CSV size or project currency.')])
    try:
        reader = csv.reader(io.StringIO(csv_bytes.decode('utf-8-sig'), newline=''), strict=True)
        header = next(reader)
        if header != COLUMNS:
            raise ValueError()
        rows = list(reader)
    except (UnicodeError, csv.Error, ValueError, StopIteration):
        return ProductImportResult(errors=[issue(1, 'csv', 'INPUT_INVALID', 'Use the required UTF-8 CSV columns.')])
    if not 1 <= len(rows) <= 20:
        return ProductImportResult(errors=[issue(0, 'csv', 'BATCH_LIMIT', 'Supply between 1 and 20 products.')])
    media_by_name, hashes = {}, set()
    for media in images:
        key = media.name.casefold()
        if key in media_by_name or media.sha256 in hashes:
            return ProductImportResult(errors=[issue(0, 'image_names', 'DUPLICATE_IMAGE', 'Each uploaded image must be unique.')])
        media_by_name[key] = media
        hashes.add(media.sha256)
    drafts, errors, skus = [], [], set()
    existing = {sku.strip().casefold() for sku in existing_skus}
    for row_number, row in enumerate(rows, 2):
        if len(row) != len(COLUMNS):
            errors.append(issue(row_number, 'csv', 'INPUT_INVALID', 'Incorrect number of columns.'))
            continue
        values = {key: cell.strip() for key, cell in zip(COLUMNS, row, strict=True)}
        row_errors = []
        for key, cell in values.items():
            if cell.startswith(('=', '+', '-', '@')) or row[COLUMNS.index(key)].startswith(('\t', '\r')):
                row_errors.append(issue(row_number, key, 'FORMULA_REJECTED', 'Spreadsheet formulas are not supported.'))
        if not values['sku']:
            row_errors.append(issue(row_number, 'sku', 'INPUT_INVALID', 'SKU is required.'))
        elif values['sku'].casefold() in skus:
            row_errors.append(issue(row_number, 'sku', 'DUPLICATE_SKU', 'SKU is duplicated in this batch.'))
        elif values['sku'].casefold() in existing:
            row_errors.append(issue(row_number, 'sku', 'SKU_CONFLICT', 'SKU already exists in the store snapshot.'))
        skus.add(values['sku'].casefold())
        if not values['name']:
            row_errors.append(issue(row_number, 'name', 'INPUT_INVALID', 'Product name is required.'))
        if not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,6})?', values['price']):
            row_errors.append(issue(row_number, 'price', 'INPUT_INVALID', 'Use a nonnegative decimal price.'))
        if values['currency'] != currency:
            row_errors.append(issue(row_number, 'currency', 'INPUT_INVALID', 'Currency must match the project.'))
        if not re.fullmatch(r'[0-9]{1,10}', values['stock']) or int(values['stock']) > 2_147_483_647:
            row_errors.append(issue(row_number, 'stock', 'INPUT_INVALID', 'Use a nonnegative integer stock quantity.'))
        names = [name.strip().casefold() for name in values['image_names'].split('|')] if values['image_names'] else []
        if len(names) > 5 or len(set(names)) != len(names) or any(name not in media_by_name for name in names):
            row_errors.append(issue(row_number, 'image_names', 'INPUT_INVALID', 'Use at most five distinct validated uploaded images.'))
        if not row_errors:
            try:
                drafts.append(ProductDraft(sku=values['sku'], title=values['name'], price=Decimal(values['price']),
                    currency=currency, stock=int(values['stock']), category=values['category'],
                    description=values['description'], source_facts={key: values[key] for key in COLUMNS if key != 'image_names'},
                    media_refs=[media_by_name[name].artifact_ref for name in names]))
            except ValidationError as error:
                aliases = {'title': 'name'}
                row_errors.extend(issue(row_number, aliases.get(str(e['loc'][0]), str(e['loc'][0])),
                                        'INPUT_INVALID', 'Field exceeds the supported input limits.') for e in error.errors())
        errors.extend(row_errors)
    return ProductImportResult(drafts=[] if errors else drafts, errors=errors)


def review_product_content(source: ProductDraft, candidate: ProductDraft) -> list[ImportIssue]:
    # Semantic truth cannot be proven by matching a model's self-reported citations.
    # Rewritten claims remain held until the merchant explicitly confirms a new source.
    fields = ('sku', 'title', 'price', 'currency', 'stock', 'description', 'category', 'media_refs', 'source_facts')
    return [issue(0, field, 'FACTS_INCOMPLETE', 'Changed product content requires merchant confirmation of its source facts.')
            for field in fields if getattr(source, field) != getattr(candidate, field)]
