"""Merchant labels bind category names to an exact project product source."""
from pydantic import Field, model_validator
from sqlalchemy import text
from muse.commerce.models import Contract, ImportedProducts
from muse.commerce.errors import CommerceFailure


class CategoryNavigationItem(Contract):
    category: str = Field(min_length=1, max_length=160, pattern=r'^[^<>\x00]+$')
    label: str = Field(min_length=1, max_length=160, pattern=r'^[^<>\x00]+$')


class CategoryNavigation(Contract):
    import_id: str = Field(min_length=1, max_length=200)
    items: list[CategoryNavigationItem] = Field(max_length=10)

    @model_validator(mode='after')
    def distinct(self):
        if len({item.category for item in self.items}) != len(self.items) or any(
            not item.category.strip() or not item.label.strip() for item in self.items):
            raise ValueError('Distinct nonblank category targets and labels required')
        return self


def validate_category_source(conn, project, navigation):
    raw = conn.execute(text("SELECT data FROM commerce_artifacts WHERE id=:id AND project_id=:project AND kind='product_import'"),
        {'id': navigation.import_id, 'project': project.id}).scalar()
    if not raw:
        raise CommerceFailure('RESOURCE_CONFLICT', project_id=project.id)
    batch = ImportedProducts.model_validate_json(raw)
    if batch.project_revision != project.revision or batch.result.errors:
        raise CommerceFailure('RESOURCE_CONFLICT', project_id=project.id)
    names = {product.category for product in batch.result.drafts if product.category}
    if any(item.category not in names for item in navigation.items):
        raise CommerceFailure('INPUT_INVALID', 422, project_id=project.id)
