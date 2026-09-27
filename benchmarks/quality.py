"""Evidence checks supplement, but never replace, semantic review."""
import hashlib
import re
from decimal import Decimal


def quality_checks(case, target, artifacts, sources, *, final_answer=""):
    if case[0] not in 'RD':
        return {}
    reports=[];valid=True
    for artifact in artifacts:
        if artifact['name'].startswith(('command-', 'tool-output')):
            continue
        path=target/'artifacts'/f"{artifact['version']}-{artifact['name']}"
        if not path.is_file():
            valid=False;continue
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=artifact['sha256']:
            valid=False
        try: content=data.decode('utf-8')
        except UnicodeDecodeError: valid=False;continue
        if not content.strip():valid=False
        reports.append(content)
    checks={'deliverable_bytes_valid':valid and bool(reports)}
    if case[0]!='R':return checks
    content='\n'.join(reports)
    checks['source_bytes_valid']=bool(sources) and all(hashlib.sha256(s['text'].encode()).hexdigest()==s['sha256'] for s in sources)
    checks['citations_in_deliverable']=bool(sources) and all(s['url'] in content for s in sources)
    identities={s['url']:s['title'].casefold().strip() for s in sources}
    links=re.findall(r'\[([^\]]+)\]\((https?://[^)\s]+)\)',content)
    attribution=True
    for label,url in links:
        named=[source for source,title in identities.items() if title and re.search(r'\b'+re.escape(title)+r'\b',label.casefold())]
        if named and url not in named:attribution=False
    checks['citation_labels_match_sources']=attribution
    # Narrow, reproducible arithmetic assertion. Other prose claims still require review.
    combined=content+'\n'+final_answer
    matches=re.finditer(r'\bdouble\w*\b[^\n.!?]{0,100}?\bfrom\s+(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)',combined,re.I)
    consistent=True
    for match in matches:
        prefix=re.split(r'[.!?\n]',combined[:match.start()])[-1][-50:]
        if re.search(r"(?:not|never|doesn't|isn't|won't|cannot)\s+(?:\w+\s+){0,3}$",prefix,re.I):
            continue  # Ambiguous/negated prose remains subject to semantic review.
        a,b=match.groups()
        if Decimal(b)!=2*Decimal(a):consistent=False
    checks['explicit_doubling_consistent']=consistent
    return checks
