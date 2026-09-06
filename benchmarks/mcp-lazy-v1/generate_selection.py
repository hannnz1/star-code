"""Fixed synthetic services and questions; no provider calls or private project data."""
import json,hashlib,random
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROWS=[
 ('orders_get_status','Retrieve the fulfillment status of a purchase order','PO-741','FULFILLED','What is the fulfillment status of purchase order PO-741?'),
 ('shipments_get_eta','Retrieve the estimated arrival date for a shipment','SHP-203','2026-09-18','When is shipment SHP-203 expected to arrive?'),
 ('invoices_get_balance','Retrieve the outstanding balance of an invoice','INV-809','USD 137.42','How much remains unpaid on invoice INV-809?'),
 ('tickets_get_owner','Retrieve the assigned support engineer for a support ticket','TKT-615','Morgan Chen','Who is assigned to support ticket TKT-615?'),
 ('builds_get_result','Retrieve the final CI build outcome','BLD-092','FAILED_TESTS','What was the result of CI build BLD-092?'),
 ('deployments_get_region','Retrieve the geographic region of a deployment','DEP-451','eu-west-2','Which region hosts deployment DEP-451?'),
 ('inventory_get_quantity','Retrieve the available inventory quantity for a stock item','SKU-386','27 units','How many units are available for item SKU-386?'),
 ('certificates_get_expiry','Retrieve the expiration date of a TLS certificate','CERT-527','2027-02-11','When does TLS certificate CERT-527 expire?'),
 ('refunds_get_state','Retrieve the processing state of a payment refund','REF-168','PENDING_REVIEW','What is the processing state of refund REF-168?'),
 ('incidents_get_severity','Retrieve the severity level of an operational incident','INC-934','SEV-2','What severity was assigned to operational incident INC-934?')]
def main():
 tools=[];tasks=[]
 def tool(name,description):return {'name':name,'description':description,'inputSchema':{'type':'object','properties':{'entity_id':{'type':'string','description':'Exact entity identifier from the user request'}},'required':['entity_id'],'additionalProperties':False},'annotations':{'readOnlyHint':True}}
 for i,(name,description,entity,result,prompt) in enumerate(ROWS):
  tools.append(tool(name,description))
  tasks.append({'id':f'task-{i+1:02}','tool':name,'entity_id':entity,'expected_result':result,
   'prompt':prompt+' Use the available MCP service to retrieve the answer. Return its exact result. Do not read local files or use shell commands.'})
 for domain in ['customers','subscriptions','warehouses','vendors','payments','users','projects','releases','repositories']:
  for operation in ['get_name','get_owner','get_region','get_state','get_created_date','get_updated_date','get_description','get_tags','get_url','get_external_reference']:
   tools.append(tool(domain+'_'+operation,'Retrieve '+operation.removeprefix('get_').replace('_',' ')+' for '+domain+' records'))
 assert len(tools)==100
 random.Random(20260905).shuffle(tools)
 data=json.dumps({'seed':20260905,'kind':'synthetic MCP services, not public production servers','tools':tools,'tasks':tasks},indent=2).encode()
 path=HERE/'selection-fixture.json'
 if path.exists():assert path.read_bytes()==data
 else:path.write_bytes(data)
 print(json.dumps({'tools':100,'tasks':10,'sha256':hashlib.sha256(data).hexdigest()}))
if __name__=='__main__':main()
