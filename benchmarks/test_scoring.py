import unittest
from report import score
class SemanticScoringTest(unittest.TestCase):
 def fact(self,value):return {'expected':value,'aliases':[]}
 def evaluate(self,value,evidence,expected,source=None,owner='RetryQueue'):
  return score(self.fact(expected),{'value':value,'evidence':evidence},evidence if source is None else source,[owner])[0]
 def test_correct_number(self):self.assertTrue(self.evaluate(730,'RetryQueue waits 730 milliseconds.',730))
 def test_number_with_extra_digit(self):self.assertFalse(self.evaluate(730,'RetryQueue waits 1730 milliseconds.',730))
 def test_number_string_not_number(self):self.assertFalse(self.evaluate('730','RetryQueue waits 730 milliseconds.',730))
 def test_correct_value_wrong_owner(self):self.assertFalse(self.evaluate(730,'LeaseCleaner waits 730 milliseconds.',730))
 def test_fabricated_evidence(self):self.assertFalse(self.evaluate(730,'RetryQueue waits 730 milliseconds.',730,'RetryQueue waits 500 milliseconds.'))
 def test_reversed_polarity(self):self.assertFalse(self.evaluate(False,'RetryQueue may delete records.',False))
 def test_negative_constraint(self):self.assertTrue(self.evaluate(False,'RetryQueue must not delete records.',False))
 def test_negation_answer_reversal(self):self.assertFalse(self.evaluate(True,'RetryQueue must not delete records.',False))
 def test_failed_attempt(self):self.assertTrue(self.evaluate(False,'RetryQueue cache clearing was tried without success.',False))
 def test_case_sensitive_identifier(self):self.assertFalse(self.evaluate('retryqueue','RetryQueue class is RetryQueue.','RetryQueue'))
 def test_missing(self):self.assertFalse(self.evaluate(None,'RetryQueue waits 730 milliseconds.',730))
 def test_keyword_only(self):self.assertFalse(self.evaluate(730,'730',730,'RetryQueue waits 730 milliseconds.'))
 def test_negated_numeric_evidence(self):self.assertFalse(self.evaluate(730,'RetryQueue must not wait 730 milliseconds.',730))
 def test_different_owner_in_same_quote(self):self.assertFalse(self.evaluate(730,'RetryQueue waits 500 milliseconds, while LeaseCleaner waits 730 milliseconds.',730))
 def test_disconnected_negation(self):self.assertFalse(self.evaluate(False,'RetryQueue may delete records. LeaseCleaner must not delete records.',False))
if __name__=='__main__':unittest.main()