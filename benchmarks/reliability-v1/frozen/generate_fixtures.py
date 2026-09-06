"""Frozen synthetic fixtures. No provider calls, no production edits."""
import json, random, hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SEED=20260905
# category, statement, question, expected typed value, accepted semantic aliases
ROWS=[
('file','Invoice export writes its audit file to reports/invoice-audit.json.','What exact path holds the invoice export audit file?','reports/invoice-audit.json',[]),
('class','The shipment normalization class is PostalRouteNormalizer.','What is the exact shipment normalization class name?','PostalRouteNormalizer',[]),
('api','The refund preview API path is /v2/refunds/preview.','What exact API path serves refund previews?','/v2/refunds/preview',[]),
('number','RetryQueue must wait 730 milliseconds before the first retry.','How many milliseconds must RetryQueue wait before its first retry?',730,[]),
('constraint','Billing reports must use the Europe/Paris timezone.','Which timezone must billing reports use?','Europe/Paris',[]),
('cause','The AuditExport date bug is caused by UTC/local time conversion mismatch.','What caused the AuditExport date bug?','UTC/local time conversion mismatch',['UTC and local timezone mismatch','mismatch between UTC and local time']),
('failed_attempt','For CartCache, increasing the TTL to 900 seconds was attempted and failed.','Did increasing CartCache TTL to 900 seconds solve the problem?',False,[]),
('negative','Do not rename the legacy column customer_ref during AccountMigration.','May AccountMigration rename the legacy customer_ref column?',False,[]),
('pending','The pending InventoryReconcile task is to add a regression test for duplicate SKU events.','What regression test is pending for InventoryReconcile?','duplicate SKU events',['a regression test for duplicate SKU events','test duplicate SKU events']),
('next','The next ReleaseAudit step is to run verify-release.ps1.','What script is the next ReleaseAudit step?','verify-release.ps1',[]),
('file','Shipping thresholds are configured in config/shipping-thresholds.yaml.','What is the shipping thresholds configuration path?','config/shipping-thresholds.yaml',[]),
('method','Tax rounding belongs in method roundTaxHalfEven.','What exact method performs tax rounding?','roundTaxHalfEven',[]),
('api','Customer suspension uses HTTP PATCH on /v3/customers/suspension.','What HTTP method is used on /v3/customers/suspension?','PATCH',[]),
('number','SearchBackfill processes batches of exactly 240 documents.','How many documents are in each SearchBackfill batch?',240,[]),
('constraint','The ReportMailer locale must be fr-CA.','Which locale must ReportMailer use?','fr-CA',[]),
('cause','The LedgerReplay duplication is caused by a missing idempotency key.','What caused LedgerReplay duplication?','missing idempotency key',['a missing idempotency key','absence of an idempotency key']),
('failed_attempt','For SearchRefresh, clearing the index cache was tried and did not fix the stale results.','Did clearing the index cache fix SearchRefresh stale results?',False,[]),
('negative','Do not delete historical rows while fixing SubscriptionExpiry.','May the SubscriptionExpiry fix delete historical rows?',False,[]),
('pending','The pending TokenRefresh task is to test simultaneous refresh requests.','Which request scenario still needs a TokenRefresh test?','simultaneous refresh requests',['concurrent refresh requests']),
('next','For CatalogDiff, inspect CatalogSnapshotReader before editing.','Which class must be inspected next for CatalogDiff?','CatalogSnapshotReader',[]),
('file','Payment deduplication tests belong in src/test/java/payments/PaymentDedupTest.java.','What exact file should contain payment deduplication tests?','src/test/java/payments/PaymentDedupTest.java',[]),
('package','The notification policy package is com.acme.notifications.policy.','What is the exact notification policy package?','com.acme.notifications.policy',[]),
('api','Inventory reservation accepts POST /v1/inventory/reservations.','What exact API path accepts inventory reservations?','/v1/inventory/reservations',[]),
('number','DeliveryEstimator must enforce a maximum of 37 route hops.','What is DeliveryEstimator maximum route-hop count?',37,[]),
('constraint','InvoiceRenderer must keep output encoded as UTF-8.','What encoding must InvoiceRenderer preserve?','UTF-8',[]),
('cause','The PriceImport precision loss is caused by conversion through double.','What caused PriceImport precision loss?','conversion through double',['conversion to double','converting through double','double conversion']),
('failed_attempt','For LeaseCleaner, raising the thread count from 4 to 16 was tried without success.','Did raising LeaseCleaner threads to 16 solve the problem?',False,[]),
('negative','The OrderArchive change must not add external dependencies.','May OrderArchive add external dependencies?',False,[]),
('pending','The pending CsvParser test must cover a quoted field containing a newline.','What field case remains to be tested in CsvParser?','quoted field containing a newline',['a quoted field containing a newline','quoted field with embedded newline']),
('next','For RetryBudget, the next command is ./gradlew test --tests RetryBudgetTest.','What is the exact next RetryBudget command?','./gradlew test --tests RetryBudgetTest',[]),
('file','Fraud score rules live in rules/fraud-score.toml.','Where do fraud score rules live?','rules/fraud-score.toml',[]),
('class','The CSV compatibility adapter is LegacyCsvBridge.','What is the CSV compatibility adapter class?','LegacyCsvBridge',[]),
('api','The health readiness path is /internal/readyz.','What is the exact readiness path?','/internal/readyz',[]),
('number','StreamBuffer must cap payloads at 65536 bytes.','What is StreamBuffer maximum payload size in bytes?',65536,[]),
('constraint','JobScheduler must use the America/Toronto timezone.','Which timezone must JobScheduler use?','America/Toronto',[]),
('cause','The WebhookAck timeout is caused by synchronous DNS lookup on the event loop.','What caused the WebhookAck timeout?','synchronous DNS lookup on the event loop',['blocking DNS lookup on the event loop','synchronous DNS resolution on the event loop']),
('failed_attempt','For MetricFlush, switching to a fixed-rate timer was attempted and failed.','Did switching MetricFlush to a fixed-rate timer fix the issue?',False,[]),
('negative','ProfileRepair must not overwrite user-selected display names.','May ProfileRepair overwrite user-selected display names?',False,[]),
('pending','The pending SessionPurge test covers an expired session with an active upload.','What session scenario remains to be tested in SessionPurge?','expired session with an active upload',['an expired session with an active upload']),
('next','For RouteCache, inspect the route_generation metric next.','Which metric must be inspected next for RouteCache?','route_generation',[]),
('file','Locale fallback data is in resources/locale-fallbacks.json.','What is the locale fallback data path?','resources/locale-fallbacks.json',[]),
('method','The reconciliation entry point is reconcilePendingTransfers.','What is the reconciliation entry-point method?','reconcilePendingTransfers',[]),
('api','The current account summary endpoint is GET /v4/accounts/summary.','What is the exact current account summary path?','/v4/accounts/summary',[]),
('number','AuthThrottle allows at most 11 attempts per minute.','How many attempts per minute does AuthThrottle allow?',11,[]),
('constraint','MoneyFormatter must use HALF_EVEN rounding.','Which rounding mode must MoneyFormatter use?','HALF_EVEN',[]),
('cause','The BlobUpload checksum mismatch is caused by hashing before decompression.','What caused the BlobUpload checksum mismatch?','hashing before decompression',['checksum computed before decompression','computing the hash before decompression']),
('failed_attempt','For SocketDrain, disabling keep-alive was tried and did not prevent dropped messages.','Did disabling keep-alive fix SocketDrain dropped messages?',False,[]),
('negative','SchemaReview must not change the public OrderResult constructor signature.','May SchemaReview change the public OrderResult constructor signature?',False,[]),
('pending','The pending DiscountPolicy test covers a zero-priced basket.','What basket case remains to be tested in DiscountPolicy?','zero-priced basket',['a zero-priced basket','zero priced basket']),
('next','For DeployChecklist, the next file to inspect is deploy/rollback-policy.md.','What is the next file to inspect for DeployChecklist?','deploy/rollback-policy.md',[]),
]
def write(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
 facts=[]
 for i,(cat,statement,q,expected,aliases) in enumerate(ROWS):
  group=round(i*119/49)
  facts.append(dict(id=f'F{i+1:02}',category=cat,statement=statement,question=q,expected=expected,aliases=aliases,group=group,position='early' if group<40 else 'middle' if group<80 else 'late'))
 rng=random.Random(SEED);by_group={f['group']:f for f in facts};history=[]
 components=['transport','serialization','request tracing','worker scheduling','dependency injection','resource cleanup','repository layout','test discovery']
 concerns=['deterministic ordering','empty inputs','timeout propagation','error attribution','stable interfaces','clear diagnostics','concurrent shutdown','repeatable fixtures']
 for group in range(120):
  paras=[]
  while sum(map(len,paras))<2500:
   paras.append(f'Discussion note {group}: review {rng.choice(components)} with attention to {rng.choice(concerns)}. The implementation review compares control flow and test coverage; this note records exploration, not a new requirement. ')
  statement=by_group[group]['statement'] if group in by_group else 'Continue reviewing the coding session notes.'
  history.append(dict(role='USER',content=statement+'\n\n'+'\n'.join(paras)))
  history.append(dict(role='ASSISTANT',content=('I will keep the explicit requirements separate from the exploratory notes. Relevant tests should verify behavior at the public boundary and report reproducible failures. '*3)))
 write(ROOT/'context-retention/facts.json',dict(seed=SEED,version=1,facts=facts))
 write(ROOT/'context-retention/conversation.json',history)
 questions=[dict(id=f['id'],question=f['question'],answer_type='boolean' if isinstance(f['expected'],bool) else 'number' if isinstance(f['expected'],(int,float)) else 'string') for f in facts]
 write(ROOT/'context-retention/questions.json',questions)
 manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'context-retention').glob('*.json')) if p.name != 'fixture-manifest.json'}
 write(ROOT/'context-retention/fixture-manifest.json',manifest)
 print('Frozen 50-fact dataset; conversation characters:',sum(len(m['content']) for m in history))
if __name__=='__main__': main()