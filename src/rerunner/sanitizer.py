"""Automated secret, API key, and PII redactor for safe cassette persistence.

Includes comprehensive scanning for OpenAI, Anthropic, Google, AWS, GitHub, Slack tokens,
plus standard PII sanitization (Emails, Credit Cards, IPv4 addresses, and US Phone numbers).
Safe for JSON payloads and preserves numeric values (e.g. Unix timestamps) and semver version strings.
An optional PII backend can be supplied as ``pii_redactor`` and runs after the built-in patterns.
"""

from __future__ import annotations

from collections.abc import Iterable
import dataclasses
import json
import re
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

if TYPE_CHECKING:
    from sether import Detector

# Regular expressions detecting common API keys and sensitive tokens
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Model Provider Keys
    (re.compile(r"sk-ant-[a-zA-Z0-9_\-]{32,}", re.IGNORECASE), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"sk-proj-[a-zA-Z0-9_\-]{32,}", re.IGNORECASE), "[REDACTED_OPENAI_PROJECT_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{32,}", re.IGNORECASE), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}", re.IGNORECASE), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{16,}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # Cloud & Git Tokens
    (re.compile(r"ghp_[a-zA-Z0-9]{36,}", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[a-zA-Z0-9]{36,}", re.IGNORECASE), "[REDACTED_GITHUB_OAUTH_TOKEN]"),
    (re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE), "[REDACTED_AWS_KEY_ID]"),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}", re.IGNORECASE), "[REDACTED_SLACK_TOKEN]"),
    # PII Scrubbers
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        # US Phone numbers requiring standard separators (+1-xxx-xxx-xxxx, (xxx) xxx-xxxx, xxx-xxx-xxxx)
        re.compile(r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]([0-9]{3})[-. ]([0-9]{4})\b"),
        "[REDACTED_PHONE]",
    ),
    (
        # US Social Security Number (SSN)
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
]

# Sensitive header keys that should always have their values scrubbed
SENSITIVE_HEADERS: set[str] = {
    "authorization",
    "x-api-key",
    "api-key",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-auth-token",
}

# Sensitive query parameter keys in URLs
SENSITIVE_QUERY_PARAMS: set[str] = {
    "key",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "client_secret",
    "auth",
    "secret",
    "password",
    "sig",
    "signature",
}

_CARD_REGEX = re.compile(r"\b(?:\d{4}[- ]){3}\d{4}\b|\b\d{16}\b")
_IP_REGEX = re.compile(
    r"(?<![\w.-])(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(?![\w.-])"
)


def _is_luhn_valid(digits_str: str) -> bool:
    """Validate credit card number using Luhn checksum algorithm."""
    clean_digits = [int(c) for c in digits_str if c.isdigit()]
    if len(clean_digits) != 16:
        return False
    checksum = 0
    reverse_digits = clean_digits[::-1]
    for i, digit in enumerate(reverse_digits):
        if i % 2 == 1:
            doubled = digit * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += digit
    return checksum % 10 == 0


def _is_probable_ip(ip_str: str) -> bool:
    """Distinguish actual IP addresses from version strings like 1.2.3.4."""
    parts = ip_str.split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    if any(n < 0 or n > 255 for n in nums):
        return False
    return (
        nums[0] in (10, 127)
        or (nums[0] == 192 and nums[1] == 168)
        or (nums[0] == 172 and 16 <= nums[1] <= 31)
        or any(n >= 10 for n in nums)
    )


class PiiRedactor(Protocol):
    """Pluggable PII backend applied after the built-in secret and PII patterns."""

    def redact(self, text: str) -> str:
        """Return ``text`` with detected PII replaced by placeholders."""
        ...


def sanitize_string(
    text: str,
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
    pii_redactor: PiiRedactor | None = None,
) -> str:
    """Scan and scrub sensitive API tokens and PII from arbitrary strings."""
    if not text:
        return text
    sanitized = text

    # Redact credit card numbers (delimiters or valid Luhn)
    def _card_replacer(match: re.Match[str]) -> str:
        matched = match.group(0)
        if " " in matched or "-" in matched:
            return "[REDACTED_CREDIT_CARD]"
        if _is_luhn_valid(matched):
            return "[REDACTED_CREDIT_CARD]"
        return matched

    sanitized = _CARD_REGEX.sub(_card_replacer, sanitized)

    # Redact IP addresses without mangling semver strings like 1.2.3.4
    def _ip_replacer(match: re.Match[str]) -> str:
        matched = match.group(0)
        if _is_probable_ip(matched):
            return "[REDACTED_IP_ADDRESS]"
        return matched

    sanitized = _IP_REGEX.sub(_ip_replacer, sanitized)

    # Apply default secret & PII patterns
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    # Apply custom user patterns if supplied
    if custom_patterns:
        for pattern, replacement in custom_patterns:
            sanitized = pattern.sub(replacement, sanitized)

    # Apply the optional PII backend after the built-in patterns
    if pii_redactor is not None:
        sanitized = pii_redactor.redact(sanitized)

    return sanitized


def sanitize_url(
    url: str,
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
    pii_redactor: PiiRedactor | None = None,
) -> str:
    """Sanitize secrets from URL query parameters (e.g. ?key=AIza...) and path components."""
    if not url:
        return url

    parts = urlsplit(url)
    if not parts.query:
        return sanitize_string(url, custom_patterns=custom_patterns, pii_redactor=pii_redactor)

    query_params = parse_qsl(parts.query, keep_blank_values=True)
    sanitized_params: list[tuple[str, str]] = []

    for k, v in query_params:
        k_lower = k.lower().strip()
        if k_lower in SENSITIVE_QUERY_PARAMS:
            sanitized_params.append((k, "[REDACTED]"))
        else:
            sanitized_val = sanitize_string(
                v, custom_patterns=custom_patterns, pii_redactor=pii_redactor
            )
            sanitized_params.append((k, sanitized_val))

    clean_query = urlencode(sanitized_params)
    clean_path = sanitize_string(
        parts.path, custom_patterns=custom_patterns, pii_redactor=pii_redactor
    )

    return urlunsplit((parts.scheme, parts.netloc, clean_path, clean_query, parts.fragment))


def sanitize_headers(
    headers: dict[str, str],
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
    pii_redactor: PiiRedactor | None = None,
) -> dict[str, str]:
    """Scrub sensitive HTTP headers before writing to cassette."""
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        k_lower = key.lower().strip()
        if k_lower in SENSITIVE_HEADERS:
            sanitized[k_lower] = "[REDACTED]"
        else:
            sanitized[k_lower] = sanitize_string(
                value, custom_patterns=custom_patterns, pii_redactor=pii_redactor
            )
    return sanitized


def sanitize_payload(
    data: Any,
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
    pii_redactor: PiiRedactor | None = None,
) -> Any:
    """Recursively sanitize dicts, lists, and strings for safe storage without mutating numbers or booleans."""
    if hasattr(data, "model_dump") and callable(data.model_dump):
        try:
            return sanitize_payload(
                data.model_dump(mode="python"),
                custom_patterns=custom_patterns,
                pii_redactor=pii_redactor,
            )
        except Exception:  # nosec B110
            pass
    if dataclasses.is_dataclass(data) and not isinstance(data, type):
        try:
            return sanitize_payload(
                dataclasses.asdict(data), custom_patterns=custom_patterns, pii_redactor=pii_redactor
            )
        except Exception:  # nosec B110
            pass
    if isinstance(data, str):
        return sanitize_string(data, custom_patterns=custom_patterns, pii_redactor=pii_redactor)
    if isinstance(data, dict):
        cleaned_keys = [
            sanitize_string(str(k), custom_patterns=custom_patterns, pii_redactor=pii_redactor)
            if isinstance(k, str)
            else k
            for k in data
        ]
        # Names of keys that are not redacted are reserved so a suffix never takes one of them
        reserved = {clean_k for k, clean_k in zip(data, cleaned_keys, strict=True) if clean_k == k}
        result: dict[Any, Any] = {}
        for (k, v), clean_k in zip(data.items(), cleaned_keys, strict=True):
            # Keep every record when two keys sanitize to the same placeholder
            if clean_k in result or (clean_k != k and clean_k in reserved):
                suffix = 2
                while f"{clean_k}#{suffix}" in result or f"{clean_k}#{suffix}" in reserved:
                    suffix += 1
                clean_k = f"{clean_k}#{suffix}"
            # If the key is specifically version/semver, do not redact the value as an IP
            if (
                isinstance(k, str)
                and k.lower() in ("version", "semver", "pyversion", "sdk_version")
                and isinstance(v, str)
            ):
                result[clean_k] = v
            else:
                result[clean_k] = sanitize_payload(
                    v, custom_patterns=custom_patterns, pii_redactor=pii_redactor
                )
        return result
    if isinstance(data, list):
        return [
            sanitize_payload(item, custom_patterns=custom_patterns, pii_redactor=pii_redactor)
            for item in data
        ]
    if isinstance(data, tuple):
        return tuple(
            sanitize_payload(item, custom_patterns=custom_patterns, pii_redactor=pii_redactor)
            for item in data
        )
    return data


def sanitize_body(
    body: str,
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
    pii_redactor: PiiRedactor | None = None,
) -> str:
    """Parse JSON bodies to safely redact string values while preserving numbers, booleans, and structure.

    Falls back to string sanitization if the payload is not valid JSON.
    """
    if not body:
        return body

    trimmed = body.strip()
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (
        trimmed.startswith("[") and trimmed.endswith("]")
    ):
        try:
            parsed = json.loads(trimmed)
            sanitized_data = sanitize_payload(
                parsed, custom_patterns=custom_patterns, pii_redactor=pii_redactor
            )
            return json.dumps(sanitized_data, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return sanitize_string(body, custom_patterns=custom_patterns, pii_redactor=pii_redactor)


# How far settling looks back across a chunk boundary: literal characters kept in front of a
# rescan so boundary assertions see their context, and the most a value may run on into the
# next chunk while that chunk still lines up without a rescan
_SETTLE_REACH = 128


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _common_suffix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[-1 - index] == right[-1 - index]:
        index += 1
    return index


def _absorbed_head(chunk: str, clean: str, target: str, start: int, limit: int) -> int:
    """Return how many leading characters of ``chunk`` the value ending the previous chunk
    took, such that the rest of ``clean`` matches ``target`` at ``start``.

    Zero means the chunk matches as it is and -1 that it does not line up within ``limit``.
    Only a head that sanitizing the chunk left unchanged is handed over, so it is raw text,
    and some of the chunk has to remain so that an empty remainder never counts as a match.
    """
    if target.startswith(clean, start):
        return 0
    literal = _common_prefix_length(chunk, clean)
    for head in range(1, min(literal, limit, len(clean) - 1) + 1):
        if target.startswith(clean[head:], start):
            return head
    return -1


def sanitize_chunks(
    chunks: list[str],
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
    pii_redactor: PiiRedactor | None = None,
) -> list[str]:
    """Sanitize streamed chunks so a value split across chunk boundaries is still redacted.

    Each chunk is sanitized on its own first; when joining those results already matches
    sanitizing the joined text they are returned unchanged. Otherwise the chunks are re-cut
    against the jointly sanitized text: a chunk that matches it at the current position is
    kept as is, and a chunk that does not is given only the part of the joint result settled
    by the text up to and including it. A placeholder therefore lands in the chunk where
    enough of the value has arrived for it to be recognised, normally the chunk where it
    completes, earlier fragments become empty chunks, other chunks keep their content, and
    the chunk count stays equal to the input so recorded chunk delays remain aligned.

    Settling rescans only the text since the last point confirmed to line up with the joint
    result, plus a little literal text before it for regex context. A rescan that disagrees
    only inside the raw text at its end confirms everything before that text, and a
    boundary that ends in a redacted value is confirmed by the chunk after it, which may
    hand its first characters to that value. The text scanned therefore normally stays
    within a small multiple of the stream instead of growing with its square.
    """
    cleaned = [
        sanitize_string(chunk, custom_patterns=custom_patterns, pii_redactor=pii_redactor)
        for chunk in chunks
    ]
    joined = "".join(chunks)
    target = sanitize_string(joined, custom_patterns=custom_patterns, pii_redactor=pii_redactor)
    if "".join(cleaned) == target:
        return cleaned

    pieces: list[str] = []
    start = 0
    consumed = 0
    # joined[:aligned] is known to sanitize to target[:aligned_start] and to end in `context`
    # characters that sanitizing left untouched. `pending` is a boundary that also lines up
    # unless the value ending there runs on into the next chunk, which that chunk decides,
    # since a fragment can sanitize to the same placeholder as the longer value it is part of.
    aligned = 0
    aligned_start = 0
    context = 0
    pending: tuple[int, int] | None = None
    for index, (chunk, clean) in enumerate(zip(chunks, cleaned, strict=True)):
        previous = consumed
        consumed += len(chunk)
        continued = pending == (previous, start)
        if index == len(chunks) - 1:
            end = len(target)
        elif (
            absorbed := _absorbed_head(
                chunk, clean, target, start, _SETTLE_REACH if continued else 0
            )
        ) >= 0:
            end = start + len(clean) - absorbed
            if continued:
                aligned, aligned_start, context = previous + absorbed, start, 0
            if aligned == previous + absorbed:
                intact = min(_common_suffix_length(chunk, clean), len(chunk) - absorbed)
                if intact == len(chunk):
                    intact += context
                if intact:
                    aligned, aligned_start, context = consumed, end, min(intact, _SETTLE_REACH)
                    pending = None
                elif chunk:
                    pending = (consumed, end)
            else:
                pending = None
        else:
            window = joined[aligned - context : consumed]
            settled = sanitize_string(
                window, custom_patterns=custom_patterns, pii_redactor=pii_redactor
            )
            base = aligned_start - context
            agreed = _common_prefix_length(settled, target[base : base + len(settled)])
            end = max(start, base + agreed)
            intact = _common_suffix_length(window, settled)
            unsettled = len(settled) - agreed
            pending = None
            if unsettled == 0 and intact == 0:
                pending = (consumed, end)
            elif unsettled <= intact:
                # Any disagreement sits in raw text at the end of the window, where a value
                # runs on into the next chunk, so everything before it lines up exactly
                aligned = consumed - unsettled
                aligned_start = base + agreed
                context = min(intact - unsettled, _SETTLE_REACH)
        pieces.append(target[start:end])
        start = end
    return pieces


def find_sensitive_leaks(
    data: Any,
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
) -> list[str]:
    """Scan arbitrary payloads and return descriptions of any unredacted secrets or PII."""
    leaks: list[str] = []
    text_to_scan: list[str] = []

    def _collect_strings(val: Any) -> None:
        if isinstance(val, str):
            text_to_scan.append(val)
        elif isinstance(val, dict):
            for k, v in val.items():
                k_clean = str(k).lower().strip()
                if k_clean in SENSITIVE_HEADERS:
                    val_str = str(v)
                    if val_str and not val_str.startswith("[REDACTED"):
                        leaks.append(f"Unredacted sensitive header '{k}'")
                _collect_strings(v)
        elif isinstance(val, (list, tuple)):
            for item in val:
                _collect_strings(item)

    _collect_strings(data)
    patterns = SECRET_PATTERNS + (custom_patterns or [])

    for text in text_to_scan:
        for match in _CARD_REGEX.finditer(text):
            matched = match.group(0)
            if (
                " " in matched or "-" in matched or _is_luhn_valid(matched)
            ) and not matched.startswith("[REDACTED"):
                leaks.append("Found unredacted pattern matching REDACTED_CREDIT_CARD")

        for match in _IP_REGEX.finditer(text):
            matched = match.group(0)
            if _is_probable_ip(matched) and not matched.startswith("[REDACTED"):
                leaks.append("Found unredacted pattern matching REDACTED_IP_ADDRESS")

        for pat, replacement in patterns:
            search_match = pat.search(text)
            if search_match:
                matched_val = search_match.group(0)
                if not matched_val.startswith("[REDACTED"):
                    leaks.append(f"Found unredacted pattern matching {replacement.strip('[]')}")

    return list(dict.fromkeys(leaks))


def sanitize_pii(
    text: str,
    entities: list[str] | None = None,
) -> str:
    """Scrub Personally Identifiable Information (PII) from string or JSON text.

    Supports Microsoft Presidio (`presidio-analyzer` & `presidio-anonymizer`) if installed.
    Gracefully falls back to high-speed compiled regex scrubbers (email, phone, credit card, SSN, IP)
    with zero mandatory third-party dependencies.

    Resolves Issue #12.
    """
    if not text:
        return text

    target_entities = entities or [
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "CREDIT_CARD",
        "US_SSN",
        "IP_ADDRESS",
    ]

    # Try Presidio if available
    try:
        from presidio_analyzer import AnalyzerEngine
        from presidio_anonymizer import AnonymizerEngine

        analyzer = AnalyzerEngine()
        anonymizer = AnonymizerEngine()
        results = analyzer.analyze(text=text, entities=target_entities, language="en")
        anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
        return str(anonymized.text)
    except ImportError:
        pass

    # High-speed fallback
    return sanitize_string(text)


_SETHER_ENTITY_PLACEHOLDERS: dict[str, str] = {
    "EMAIL_ADDRESS": "[REDACTED_EMAIL]",
    "PHONE_NUMBER": "[REDACTED_PHONE]",
    "CREDIT_CARD": "[REDACTED_CREDIT_CARD]",
    "US_SSN": "[REDACTED_SSN]",
}


class SetherRedactor:
    """Optional PII backend built on Sether detectors, emitting the built-in placeholders.

    Requires the ``sether`` extra (``pip install "rerunner[sether]"``); the package is imported
    lazily so the default sanitizer never loads it. Entities use the same names as
    ``sanitize_pii``: ``EMAIL_ADDRESS``, ``PHONE_NUMBER``, ``CREDIT_CARD`` and ``US_SSN``.
    ``IP_ADDRESS`` stays on the built-in version-aware regex. ``PHONE_NUMBER`` matches
    international ``+`` numbers only unless ``phone_regions`` lists ISO 3166-1 alpha-2 codes
    whose national formats should also be recognised.
    """

    def __init__(
        self,
        entities: Iterable[str] | None = None,
        phone_regions: Iterable[str] = (),
    ) -> None:
        try:
            import phonenumbers
            import sether
        except ImportError as exc:
            raise ImportError(
                "SetherRedactor requires the optional 'sether' package. "
                'Install it with: pip install "rerunner[sether]"'
            ) from exc

        selected = list(entities) if entities is not None else list(_SETHER_ENTITY_PLACEHOLDERS)
        if not selected or set(selected).difference(_SETHER_ENTITY_PLACEHOLDERS):
            raise ValueError(
                "SetherRedactor entities must be a non-empty subset of "
                f"{sorted(_SETHER_ENTITY_PLACEHOLDERS)}, got {selected}"
            )

        regions = list(phone_regions)
        unknown_regions = sorted(set(regions).difference(phonenumbers.SUPPORTED_REGIONS))
        if unknown_regions:
            raise ValueError(f"Unknown phone regions: {unknown_regions}")

        phone: Detector = (
            sether.create_multi_region_phone_detector(regions) if regions else sether.phone_detector
        )
        available: dict[str, Detector] = {
            "EMAIL_ADDRESS": sether.email_detector,
            "PHONE_NUMBER": phone,
            "CREDIT_CARD": sether.credit_card_detector,
            "US_SSN": sether.ssn_detector,
        }

        self.entities = list(dict.fromkeys(selected))
        self.phone_regions = regions
        self._detectors = [
            (available[entity], _SETHER_ENTITY_PLACEHOLDERS[entity]) for entity in self.entities
        ]

    def redact(self, text: str) -> str:
        """Replace every detected entity with its placeholder, merging overlapping matches."""
        if not text:
            return text
        spans = [
            (match.start, match.end, placeholder)
            for detector, placeholder in self._detectors
            for match in detector.detect(text)
        ]
        if not spans:
            return text
        spans.sort(key=lambda span: (span[0], span[0] - span[1]))
        pieces: list[str] = []
        cursor = 0
        for start, end, placeholder in spans:
            if start < cursor:
                cursor = max(cursor, end)
                continue
            pieces.append(text[cursor:start])
            pieces.append(placeholder)
            cursor = end
        pieces.append(text[cursor:])
        return "".join(pieces)
