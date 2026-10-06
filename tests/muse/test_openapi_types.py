import pytest
from muse.openapi_types import render_types,ts_type


def test_split_input_output_alias_and_nested_reference():
    schema={'components':{'schemas':{'Draft-Input':{'type':'object','properties':{'price':{'type':'string'}}},'Draft-Output':{'type':'object','properties':{'input':{'$ref':'#/components/schemas/Draft-Input'}}}}}}
    result=render_types(schema)
    assert 'export type Draft_Output' in result
    assert 'input"?: Draft_Input' in result
    assert 'export type Draft = Draft_Output;' in result
    assert ts_type({'$ref':'#/components/schemas/2-name'})=='_2_name'


def test_normalized_schema_name_collision_fails_closed():
    with pytest.raises(ValueError):render_types({'components':{'schemas':{'A-B':{},'A_B':{}}}})
