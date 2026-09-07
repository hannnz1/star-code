"""Verify the distributable contains the exact tested production classes/resources."""
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent.parent
def git(*args):
    return subprocess.check_output(["git", "-c", "safe.directory=" + root.as_posix(), *args],
                                   cwd=root, text=True).strip()
if git("diff", "HEAD", "--", "src/main"):
    raise RuntimeError("Production sources differ from committed version")
jar = root / "build/libs/star-code.jar"
counts = dict(tests=0, failures=0, errors=0, skipped=0)
for path in (root / "build/test-results/test").glob("TEST-*.xml"):
    suite = ET.parse(path).getroot()
    for key in counts:
        counts[key] += int(suite.attrib.get(key, 0))
if not counts["tests"] or any(counts[k] for k in ("failures", "errors", "skipped")):
    raise RuntimeError("Full test result is missing or not fully passing")
verified = []
with zipfile.ZipFile(jar) as archive:
    names = archive.namelist()
    for folder, pattern in ((root / "build/classes/java/main", "*.class"),
                            (root / "src/main/resources", "*")):
        for path in sorted(folder.rglob(pattern)):
            if not path.is_file():
                continue
            name = path.relative_to(folder).as_posix()
            if names.count(name) != 1 or archive.read(name) != path.read_bytes():
                raise RuntimeError("Packaged content mismatch: " + name)
            verified.append(name)
if not any(n.endswith("SummaryValidator.class") for n in verified):
    raise RuntimeError("Missing production classes")
record = dict(timestamp=datetime.now(timezone.utc).isoformat(),
              production_commit=git("rev-parse", "HEAD"),
              baseline_commit=git("rev-parse", "benchmark-baseline-v1^{commit}"),
              jar=str(jar), jar_bytes=jar.stat().st_size,
              jar_sha256=hashlib.sha256(jar.read_bytes()).hexdigest(), tests=counts,
              matching_classes=sum(n.endswith(".class") for n in verified),
              matching_resources=sum(not n.endswith(".class") for n in verified),
              status="PASS", evidence="JAR byte equality against locally tested classes and source resources; no model call.")
target = root / "benchmarks/results/current-package-validation.json"
target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8", newline="")
print(json.dumps(record))
