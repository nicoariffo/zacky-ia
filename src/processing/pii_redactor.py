"""PII (Personally Identifiable Information) redaction for support tickets."""

import re
from dataclasses import dataclass
from typing import NamedTuple


class RedactionResult(NamedTuple):
    """Result of PII redaction."""

    text: str
    redactions: list[dict[str, str]]
    has_pii: bool


@dataclass
class PIIPattern:
    """Pattern definition for PII detection."""

    name: str
    pattern: re.Pattern[str]
    replacement: str


class PIIRedactor:
    """
    Redacts PII from text using regex patterns.

    Focuses on Chilean formats but also handles international patterns:
    - Email addresses
    - Phone numbers (Chilean +56 format and others)
    - RUT (Chilean national ID)
    - Credit card numbers
    - Chilean addresses patterns
    """

    def __init__(self) -> None:
        self.patterns = self._build_patterns()

    def _build_patterns(self) -> list[PIIPattern]:
        """Build list of PII patterns to detect."""
        return [
            # Email addresses
            PIIPattern(
                name="email",
                pattern=re.compile(
                    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                    re.IGNORECASE,
                ),
                replacement="[EMAIL]",
            ),
            # Chilean phone numbers: +56 9 1234 5678 or 56912345678
            PIIPattern(
                name="phone_cl",
                pattern=re.compile(
                    r"(?:\+?56\s*)?(?:9|2)\s*\d{4}\s*\d{4}\b",
                    re.IGNORECASE,
                ),
                replacement="[TELEFONO]",
            ),
            # International phone (generic)
            PIIPattern(
                name="phone_intl",
                pattern=re.compile(
                    r"\+\d{1,3}\s*\d{6,14}\b",
                ),
                replacement="[TELEFONO]",
            ),
            # Chilean RUT: 12.345.678-9 or 12345678-9 or 123456789
            PIIPattern(
                name="rut",
                pattern=re.compile(
                    r"\b\d{1,2}\.?\d{3}\.?\d{3}[-]?[0-9kK]\b",
                ),
                replacement="[RUT]",
            ),
            # Credit card numbers (basic pattern)
            PIIPattern(
                name="credit_card",
                pattern=re.compile(
                    r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
                ),
                replacement="[TARJETA]",
            ),
            # Order/tracking numbers that might be sensitive
            # (optional - can be customized per client)
            PIIPattern(
                name="order_number",
                pattern=re.compile(
                    r"\b(?:pedido|orden|order)\s*#?\s*(\d{5,})\b",
                    re.IGNORECASE,
                ),
                replacement="[PEDIDO]",
            ),
            # Street addresses (Chilean format)
            PIIPattern(
                name="address",
                pattern=re.compile(
                    r"\b(?:calle|av\.?|avenida|pasaje|psje\.?)\s+[A-Za-zÁáÉéÍíÓóÚúÑñ\s]+\s*\d+",
                    re.IGNORECASE,
                ),
                replacement="[DIRECCION]",
            ),
            # Passport numbers (basic pattern)
            PIIPattern(
                name="passport",
                pattern=re.compile(
                    r"\b[A-Z]{1,2}\d{6,9}\b",
                ),
                replacement="[DOCUMENTO]",
            ),
        ]

    def redact(self, text: str) -> RedactionResult:
        """
        Redact PII from text.

        Args:
            text: Text to redact

        Returns:
            RedactionResult with redacted text, list of redactions made,
            and flag indicating if any PII was found
        """
        if not text:
            return RedactionResult(text="", redactions=[], has_pii=False)

        redacted_text = text
        redactions: list[dict[str, str]] = []

        for pii_pattern in self.patterns:
            matches = list(pii_pattern.pattern.finditer(redacted_text))

            for match in reversed(matches):  # Reverse to maintain positions
                original = match.group()
                redactions.append({
                    "type": pii_pattern.name,
                    "original_length": len(original),
                    "position": match.start(),
                })

                redacted_text = (
                    redacted_text[: match.start()]
                    + pii_pattern.replacement
                    + redacted_text[match.end():]
                )

        has_pii = len(redactions) > 0

        return RedactionResult(
            text=redacted_text,
            redactions=redactions,
            has_pii=has_pii,
        )

    def redact_batch(self, texts: list[str]) -> list[RedactionResult]:
        """Redact PII from a batch of texts."""
        return [self.redact(text) for text in texts]

    def validate_redaction(self, text: str) -> dict[str, list[str]]:
        """
        Validate that text has been properly redacted.

        Returns dict of PII types and any remaining matches found.
        Useful for QA validation.
        """
        remaining: dict[str, list[str]] = {}

        for pii_pattern in self.patterns:
            matches = pii_pattern.pattern.findall(text)
            if matches:
                remaining[pii_pattern.name] = matches

        return remaining


def create_redactor() -> PIIRedactor:
    """Factory function to create a PIIRedactor."""
    return PIIRedactor()
