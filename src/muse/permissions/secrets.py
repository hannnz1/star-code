import re

PATTERNS = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*['\"]?[^\s'\",;]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}"),
]


def contains_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in PATTERNS)


def redact(value: str, secrets: tuple[str, ...] = ()) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    for pattern in PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def stream_prefix(value: str, secrets: tuple[str, ...] = ()) -> tuple[str, str]:
    """Retain a look-behind tail so chunks cannot split a secret across persisted events."""
    cut = max(0, len(value) - max(512, *(len(secret) + 32 for secret in secrets)))
    for secret in secrets:
        if secret:
            start = value.find(secret)
            while start >= 0:
                if start < cut < start + len(secret):
                    cut = start
                start = value.find(secret, start + len(secret))
    for pattern in PATTERNS:
        for match in pattern.finditer(value):
            if match.start() < cut < match.end():
                cut = match.start()
    private = value.find("-----BEGIN ")
    if private >= 0 and "PRIVATE KEY-----" in value[private:] and "-----END " not in value[private:]:
        cut = min(cut, private)
    return redact(value[:cut], secrets), value[cut:]
