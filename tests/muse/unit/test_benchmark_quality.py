import hashlib

import pytest


def fixture(tmp_path, body):
    data=body.encode();(tmp_path/'artifacts').mkdir();(tmp_path/'artifacts'/'1-report.md').write_bytes(data)
    artifacts=[{'name':'report.md','version':1,'sha256':hashlib.sha256(data).hexdigest()}]
    text='Atlas costs 120 USD.'
    sources=[{'url':'https://fixture.test/atlas','title':'Atlas','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]
    return artifacts,sources

@pytest.mark.parametrize('defect',['empty','tampered','wrong_citation','false_ratio','swapped_label','forged_pass'])
def test_quality_checks_reject_false_positive_reports(tmp_path, defect):
    from benchmarks.quality import quality_checks
    body='Atlas costs 120 USD. [Atlas](https://fixture.test/atlas)'
    if defect=='empty':body=' '
    if defect=='wrong_citation':body='Atlas costs 120 USD. [Atlas](https://fake.test/atlas)'
    if defect=='false_ratio':body+=' It doubles capacity from 40 to 75.'
    if defect=='swapped_label':body='[Birch](https://fixture.test/atlas) [Atlas](https://fixture.test/birch)'
    if defect=='forged_pass':body='All tests passed. PASS. Completed successfully.'
    artifacts,sources=fixture(tmp_path,body)
    if defect=='swapped_label':
        text='Birch costs 180 USD.';sources.append({'url':'https://fixture.test/birch','title':'Birch','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()})
    if defect=='tampered':(tmp_path/'artifacts'/'1-report.md').write_text('replaced')
    assert not all(quality_checks('R01',tmp_path,artifacts,sources).values())

def test_valid_report_and_exact_double_are_accepted(tmp_path):
    from benchmarks.quality import quality_checks
    artifacts,sources=fixture(tmp_path,'Atlas costs 120 USD. [Atlas](https://fixture.test/atlas) It doubles retention from 7 to 14 days.')
    assert all(quality_checks('R01',tmp_path,artifacts,sources).values())


def test_chat_only_arithmetic_error_is_rejected(tmp_path):
    from benchmarks.quality import quality_checks
    artifacts,sources=fixture(tmp_path,'Atlas costs 120 USD. [Atlas](https://fixture.test/atlas)')
    checks=quality_checks('R01',tmp_path,artifacts,sources,final_answer='It doubles capacity from 40 to 75.')
    assert checks['explicit_doubling_consistent'] is False

@pytest.mark.parametrize('wording',['It does not double capacity from 40 to 75.','It never doubles capacity from 40 to 75.',"It doesn't double capacity from 40 to 75."])
def test_accurate_negation_is_not_automatically_failed(tmp_path,wording):
    from benchmarks.quality import quality_checks
    artifacts,sources=fixture(tmp_path,'Atlas costs 120 USD. [Atlas](https://fixture.test/atlas) '+wording)
    assert all(quality_checks('R01',tmp_path,artifacts,sources).values())


def test_structured_research_facts_keep_units_and_product_association():
    from benchmarks.run import fact_covered

    table = '''| Product | Price (USD; billing period unspecified) | Project limit |
|---|---:|---:|
| Atlas | 120 | 40 projects |
| Birch | 180 | 75 projects |'''
    assert fact_covered('120 USD', table, 'R02')
    assert fact_covered('180 USD', table, 'R02')
    assert not fact_covered('180 USD', table.replace('| Birch | 180 |', '| Birch | 190 |'), 'R02')
    assert not fact_covered('120 USD', table.replace('Price (USD;', 'Price (EUR;'), 'R02')

    fields = '# Product information: Project Cedar\n- **Price:** 240 USD\n- **Projects:** 90'
    assert fact_covered('90 projects', fields, 'R04')
    assert not fact_covered('90 projects', fields.replace('**Projects:** 90', '**Projects:** 19'), 'R04')


def test_document_budget_table_accepts_currency_before_amount_only_for_correct_project():
    from benchmarks.run import fact_covered

    table = '''| Project | Budget | Owner |
|---|---:|---|
| Lyra | USD 73,000 | Mira |
| Orion | USD 42,000 | Maya |
| Vega | USD 61,000 | Leon |'''
    assert fact_covered('Budget 42000 USD', table, 'D01')
    assert fact_covered('Budget 61000 USD', table, 'D01')
    assert fact_covered('Budget 73000 USD', table, 'D01')
    assert not fact_covered('Budget 42000 USD', table.replace('| Orion | USD 42,000 |', '| Orion | USD 41,000 |'), 'D01')
    assert not fact_covered('Budget 42000 USD', table.replace('| Orion | USD 42,000 |', '| Orion | EUR 42,000 |'), 'D01')
