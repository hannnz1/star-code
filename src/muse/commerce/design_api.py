from muse.commerce.design_models import DesignInitialize, DesignSave, StoreDesignDocument
from muse.commerce.design_repository import DesignRepository


def install_design_routes(router, repo):
    service = DesignRepository(repo)

    @router.get('/projects/{project_id}/design', response_model=StoreDesignDocument | None)
    def read_design(project_id: str):
        return service.get(project_id)

    @router.post('/projects/{project_id}/design', response_model=StoreDesignDocument)
    def initialize_design(project_id: str, body: DesignInitialize):
        return service.get_or_create(project_id,body.expected_project_revision)

    @router.patch('/projects/{project_id}/design', response_model=StoreDesignDocument)
    def save_design(project_id: str, body: DesignSave):
        return service.save(project_id,body.expected_project_revision,body.expected_revision,body.client_request_id,body.document)

    @router.get('/projects/{project_id}/design-media/{media_id}')
    def design_media(project_id: str, media_id: str):
        import base64, io
        from PIL import Image
        from muse.commerce.media import MediaRepository
        record, content = MediaRepository(repo).content(project_id,media_id)
        with Image.open(io.BytesIO(content)) as source:
            source.thumbnail((800,800))
            buffer=io.BytesIO();source.convert('RGB').save(buffer,format='JPEG',quality=85)
        return {'data_url':'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')}

    from muse.commerce.product_drafts import ProductDraftInput, ProductDraftRepository
    from muse.commerce.models import ImportedProducts

    @router.post('/projects/{project_id}/product-draft',response_model=ImportedProducts,status_code=201)
    def product_draft(project_id: str,body:ProductDraftInput):
        return ProductDraftRepository(repo).save(project_id,body)

    from fastapi import Request
    from muse.commerce.design_proposals import DesignProposalService,ProposalInput,ProposalControl

    def proposals(request):
        return DesignProposalService(repo,request.app.state.settings)

    @router.post('/projects/{project_id}/design-proposals')
    def create_design_proposal(project_id: str,body:ProposalInput,request:Request):
        return proposals(request).enqueue(project_id,body)

    @router.get('/projects/{project_id}/design-proposals/{proposal_id}')
    def read_design_proposal(project_id: str,proposal_id:str,request:Request):
        return proposals(request).read(project_id,proposal_id)

    @router.post('/projects/{project_id}/design-proposals/{proposal_id}/accept',response_model=StoreDesignDocument)
    def accept_design_proposal(project_id:str,proposal_id:str,body:ProposalControl,request:Request):
        return proposals(request).accept(project_id,proposal_id,body.expected_design_revision)

    @router.post('/projects/{project_id}/design-proposals/{proposal_id}/reject')
    def reject_design_proposal(project_id:str,proposal_id:str,request:Request):
        return proposals(request).reject(project_id,proposal_id)

    from muse.commerce.store_readiness import StoreReadinessService,StoreReadinessReport,ShippingQuote,quote_shipping

    @router.get('/projects/{project_id}/readiness',response_model=StoreReadinessReport)
    def store_readiness(project_id:str):
        return StoreReadinessService(repo).evaluate(project_id)

    @router.post('/projects/{project_id}/shipping-quote')
    def shipping_quote(project_id:str,body:ShippingQuote):
        project=repo.get_project(project_id)
        return {'amount':str(quote_shipping(body)),'currency':project.brief.currency,'estimate_only':True,'configured_on_platform':False}
