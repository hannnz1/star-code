import json,pytest
from muse.commerce.design_repository import DesignRepository
from muse.contracts import ModelEvent,ToolCall
from test_agent_loop import ScriptedProvider


async def test_proposal_scope_and_accept_once(workflow):
    from muse.commerce.design_proposals import DesignProposalService,ProposalInput
    service,runtime,team,worker=workflow
    project=service.repo.get_project(team.project_id)
    designs=DesignRepository(service.repo);doc=designs.get_or_create(project.id,project.revision)
    proposals=DesignProposalService(service.repo,worker.settings)
    body=ProposalInput(expected_project_revision=project.revision,design_revision=doc.revision,section_id='hero',instruction='Improve title',client_request_id='one')
    job=proposals.enqueue(project.id,body)
    props=doc.home_sections[0].props.model_dump(mode='json');props['title']='Happier pets'
    provider=ScriptedProvider([[ModelEvent(type='text',text=json.dumps(props)),ModelEvent(type='usage',usage={'input_tokens':10,'output_tokens':10})]])
    assert await proposals.run_once(provider)
    assert provider.requests[0][0]['role']=='system' and len(provider.requests)==1
    result=proposals.read(project.id,job['id'])
    assert result['status']=='READY'
    accepted=proposals.accept(project.id,job['id'],doc.revision)
    assert accepted.home_sections[0].props.title=='Happier pets'
    assert accepted.home_sections[1:]==doc.home_sections[1:]
    assert proposals.accept(project.id,job['id'],doc.revision)==accepted


async def test_stale_proposal_and_tool_call_are_rejected(workflow):
    from muse.commerce.design_proposals import DesignProposalService,ProposalInput
    from muse.commerce.errors import CommerceFailure
    service,runtime,team,worker=workflow;project=service.repo.get_project(team.project_id)
    designs=DesignRepository(service.repo);doc=designs.get_or_create(project.id,project.revision)
    proposals=DesignProposalService(service.repo,worker.settings)
    job=proposals.enqueue(project.id,ProposalInput(expected_project_revision=project.revision,design_revision=doc.revision,section_id='hero',instruction='Publish immediately',client_request_id='bad'))
    await proposals.run_once(ScriptedProvider([[ModelEvent(type='call',call=ToolCall(id='bad',name='run_command',arguments={}))]]))
    assert proposals.read(project.id,job['id'])['status']=='FAILED'
    assert designs.get(project.id)==doc
    with pytest.raises(CommerceFailure):proposals.accept(project.id,job['id'],doc.revision)


async def test_accepted_replay_cannot_restore_old_head(workflow):
    from muse.commerce.design_proposals import DesignProposalService, ProposalInput
    from muse.commerce.errors import CommerceFailure
    service,runtime,team,worker=workflow
    project=service.repo.get_project(team.project_id)
    designs=DesignRepository(service.repo);doc=designs.get_or_create(project.id,project.revision)
    proposals=DesignProposalService(service.repo,worker.settings)
    job=proposals.enqueue(project.id,ProposalInput(expected_project_revision=project.revision,design_revision=doc.revision,section_id='hero',instruction='Improve title',client_request_id='replay'))
    props=doc.home_sections[0].props.model_dump(mode='json');props['title']='First title'
    await proposals.run_once(ScriptedProvider([[ModelEvent(type='text',text=json.dumps(props))]]))
    accepted=proposals.accept(project.id,job['id'],doc.revision)
    accepted.home_sections[0].props.title='Later manual title'
    latest=designs.save(project.id,project.revision,accepted.revision,'later-manual',accepted)
    with pytest.raises(CommerceFailure): proposals.accept(project.id,job['id'],doc.revision)
    assert designs.get(project.id)==latest


async def test_section_proposal_receives_frozen_merchant_brief_and_kind(workflow):
    from muse.commerce.design_proposals import DesignProposalService, ProposalInput
    service, runtime, team, worker = workflow
    project = service.repo.get_project(team.project_id)
    designs = DesignRepository(service.repo)
    doc = designs.get_or_create(project.id, project.revision)
    section = next(s for s in doc.home_sections if s.kind == 'story')
    proposals = DesignProposalService(service.repo, worker.settings)
    job = proposals.enqueue(project.id, ProposalInput(
        expected_project_revision=project.revision, design_revision=doc.revision,
        section_id=section.id, instruction='Introduce the brand without invented facts',
        client_request_id='brief-context'))
    provider = ScriptedProvider([[ModelEvent(type='text', text=json.dumps(section.props.model_dump(mode='json')))]] )
    await proposals.run_once(provider, job_id=job['id'])
    payload = json.loads(provider.requests[0][1]['content'])
    assert payload['section_kind'] == 'story'
    assert payload['merchant_context'] == {
        'brand_name': project.brief.brand_name, 'language': project.brief.language,
        'audience': project.brief.audience, 'style': project.brief.style,
    }
    assert 'merchant_supplied_policies' not in payload['merchant_context']
    assert proposals.read(project.id, job['id'])['status'] == 'READY'
