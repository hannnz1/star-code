# Text utilities contract
Implement two existing independent interfaces, preserving signatures and verification files.
text.Slug.of(String): reject null with IllegalArgumentException. Normalize NFKD, discard Unicode combining marks,
lowercase with Locale.ROOT, replace each run outside ASCII a-z/0-9 with one hyphen, strip edge hyphens.
An empty or punctuation-only input returns the empty string.
text.Header.parse(String): reject null, CR/LF anywhere, no colon, or an invalid header name with IllegalArgumentException.
Split at the FIRST colon. Trim both parts; lowercase name with Locale.ROOT. Name must match [a-z][a-z0-9-]*.
Return a one-entry Map<String,String>; value can be empty and can contain additional colons. Preserve value case.
Read tests/GateTest.java for boundary checks. Run powershell.exe -NoProfile -File ./verify.ps1 after integrating both components.
