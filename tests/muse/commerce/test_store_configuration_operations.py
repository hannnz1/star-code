import pytest
from muse.commerce.models import ChangeOperation
from muse.commerce_connector.operations import validate_operation
from muse.commerce.errors import CommerceFailure
from tests.muse.commerce.test_shipping_rules import rules


def test_shipping_operation_has_closed_rules_and_resource():
    op = ChangeOperation(operation_id='shipping', kind='set_owned_shipping', resource_key='shipping:muse-storefront',
                         expected_fingerprint='a'*64, payload={'rules':rules()})
    assert validate_operation(op).payload == {'rules':rules()}
    for payload in [{'rules':rules(), 'admin':True}, {'rules':rules(zones=[])}]:
        with pytest.raises(CommerceFailure):
            validate_operation(op.model_copy(update={'payload':payload}))


def test_store_navigation_separates_page_and_category_targets():
    op = ChangeOperation(operation_id='navigation', kind='set_owned_store_navigation', resource_key='navigation:muse-storefront',
                         expected_fingerprint='a'*64, payload={'items':[{'page_id':2,'label':'Home'}, {'category_id':2,'label':'Dogs'}]})
    assert validate_operation(op).payload == op.payload
    for items in [[{'category_id':2,'label':'Dogs','url':'https://evil.test'}],
                  [{'page_id':2,'category_id':3,'label':'Mixed'}],
                  [{'category_id':2,'label':'One'},{'category_id':2,'label':'Two'}]]:
        with pytest.raises(CommerceFailure):
            validate_operation(op.model_copy(update={'payload':{'items':items}}))
