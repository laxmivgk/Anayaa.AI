import re
from dataclasses import dataclass

DANGER_PATTERNS = [
    re.compile(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", re.I),
    re.compile(r"SELECT\s+.*\s+FROM", re.I),
    re.compile(r"DROP\s+TABLE", re.I),
    re.compile(r"UNION\s+SELECT", re.I),
    re.compile(r"INSERT\s+INTO", re.I),
    re.compile(r"--"),
    re.compile(r"/\*"),
]


@dataclass
class SanitationResult:
    passed: bool
    sanitized: str
    violations: list[str]


def run_security_firewall(input_text: str, max_length: int = 4000) -> SanitationResult:
    violations: list[str] = []
    text = input_text[:max_length]

    for pattern in DANGER_PATTERNS:
        if pattern.search(text):
            violations.append(f"Pattern detected: {pattern.pattern}")

    sanitized = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )

    return SanitationResult(passed=len(violations) == 0, sanitized=sanitized, violations=violations)
