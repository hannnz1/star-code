import unittest
from muse.openapi_types import ts_type
class SchemaTests(unittest.TestCase):
    def test_one_of_preserves_both_branches(self):
        self.assertEqual(ts_type({'oneOf':[{'type':'string'},{'type':'number'}]}),'string | number')
    def test_union_is_grouped_inside_intersection(self):
        output=ts_type({'allOf':[{'anyOf':[{'type':'string'},{'type':'number'}]},{'type':'boolean'}]}).replace(' ','')
        self.assertIn('(string|number)',output)
        self.assertTrue(output.endswith('&boolean') or output.endswith('&(boolean)'))
    def test_array_nullable_union(self):
        self.assertEqual(ts_type({'type':'array','items':{'anyOf':[{'type':'string'},{'type':'null'}]}}),'(string | null)[]')
if __name__=='__main__':unittest.main()
