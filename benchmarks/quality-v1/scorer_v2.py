"""Post-generation punctuation bugfix, kept separate from frozen v1 rules.
No model/production changes. Does not validate general semantic interpretation.
"""
import importlib.util,re
from pathlib import Path
spec=importlib.util.spec_from_file_location('frozen_screen_v2_instance',Path(__file__).with_name('scorer.py'))
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)
def literal(value,source):
 # Allow a sentence-final period but reject .suffix, numeric decimals and prefixes.
 return bool(re.search(r'(?<![\w/-])'+re.escape(str(value))+r'(?![\w/-]|\.[\w])',source))
engine.literal=literal
evaluate=engine.evaluate
EXACT_CATEGORIES=engine.EXACT_CATEGORIES
