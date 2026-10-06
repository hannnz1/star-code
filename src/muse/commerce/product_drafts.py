"""Single-product form adapter producing immutable, existing import contracts."""
import csv,io
from pydantic import Field
from muse.commerce.models import Contract, ProductDraft
from muse.commerce.errors import CommerceFailure


class ProductDraftInput(Contract):
    expected_project_revision: int = Field(ge=1,strict=True)
    client_request_id: str = Field(min_length=1,max_length=200)
    source_import_id: str | None = None
    draft: ProductDraft


class ProductDraftRepository:
    def __init__(self,repo):self.repo=repo

    def save(self,project_id,body):
        project=self.repo.get_project(project_id)
        if project.revision!=body.expected_project_revision:raise CommerceFailure('RESOURCE_CONFLICT')
        if body.draft.currency!=project.brief.currency:raise CommerceFailure('INPUT_INVALID',422)
        if body.source_import_id:
            sources=self.repo.list_product_imports(project_id)
            if not any(s.id==body.source_import_id and s.project_revision==project.revision for s in sources):
                raise CommerceFailure('RESOURCE_CONFLICT')
        images=[]
        from muse.commerce.media import MediaRepository
        for identity in body.draft.media_refs:
            record,_=MediaRepository(self.repo).content(project_id,identity)
            images.append(record.image.name)
        output=io.StringIO();writer=csv.writer(output)
        writer.writerow(['sku','name','price','currency','stock','category','description','image_names'])
        d=body.draft
        writer.writerow([d.sku,d.title,str(d.price),d.currency,d.stock,d.category,d.description,'|'.join(images)])
        return self.repo.import_products(project_id,output.getvalue(),body.client_request_id,project.revision,media_ids=d.media_refs)
