"""Tests for PII redactor."""

import pytest

from src.processing.pii_redactor import PIIRedactor


class TestPIIRedactor:
    """Tests for PIIRedactor."""

    @pytest.fixture
    def redactor(self) -> PIIRedactor:
        return PIIRedactor()

    def test_redact_email(self, redactor: PIIRedactor) -> None:
        """Test email redaction."""
        text = "Contactame a juan.perez@gmail.com por favor"
        result = redactor.redact(text)

        assert "[EMAIL]" in result.text
        assert "juan.perez@gmail.com" not in result.text
        assert result.has_pii is True
        assert any(r["type"] == "email" for r in result.redactions)

    def test_redact_chilean_phone(self, redactor: PIIRedactor) -> None:
        """Test Chilean phone number redaction."""
        texts = [
            "Llamame al +56 9 1234 5678",
            "Mi celular es 912345678",
            "Tel: 56 9 8765 4321",
        ]

        for text in texts:
            result = redactor.redact(text)
            assert "[TELEFONO]" in result.text
            assert result.has_pii is True

    def test_redact_rut(self, redactor: PIIRedactor) -> None:
        """Test Chilean RUT redaction."""
        texts = [
            "Mi RUT es 12.345.678-9",
            "RUT: 12345678-K",
            "Documento: 12345678k",
        ]

        for text in texts:
            result = redactor.redact(text)
            assert "[RUT]" in result.text
            assert result.has_pii is True

    def test_redact_credit_card(self, redactor: PIIRedactor) -> None:
        """Test credit card number redaction."""
        texts = [
            "Mi tarjeta es 4111-1111-1111-1111",
            "Número: 4111 1111 1111 1111",
        ]

        for text in texts:
            result = redactor.redact(text)
            assert "[TARJETA]" in result.text
            assert result.has_pii is True

    def test_redact_order_number(self, redactor: PIIRedactor) -> None:
        """Test order number redaction."""
        text = "Mi pedido #123456 no llegó"
        result = redactor.redact(text)

        assert "[PEDIDO]" in result.text
        assert result.has_pii is True

    def test_redact_address(self, redactor: PIIRedactor) -> None:
        """Test address redaction."""
        texts = [
            "Vivo en Av. Providencia 1234",
            "Dirección: Calle Las Flores 567",
            "Pasaje Los Aromos 89",
        ]

        for text in texts:
            result = redactor.redact(text)
            assert "[DIRECCION]" in result.text
            assert result.has_pii is True

    def test_no_pii_text(self, redactor: PIIRedactor) -> None:
        """Test text without PII."""
        text = "Hola, tengo una consulta sobre los horarios de atención."
        result = redactor.redact(text)

        assert result.text == text
        assert result.has_pii is False
        assert len(result.redactions) == 0

    def test_multiple_pii_types(self, redactor: PIIRedactor) -> None:
        """Test redaction of multiple PII types."""
        text = """
        Hola, soy Juan Pérez.
        Email: juan@example.com
        Tel: +56 9 1234 5678
        RUT: 12.345.678-9
        """

        result = redactor.redact(text)

        assert "[EMAIL]" in result.text
        assert "[TELEFONO]" in result.text
        assert "[RUT]" in result.text
        assert result.has_pii is True
        assert len(result.redactions) >= 3

    def test_redact_batch(self, redactor: PIIRedactor) -> None:
        """Test batch redaction."""
        texts = [
            "Email: test@example.com",
            "Tel: +56 9 1234 5678",
            "Sin PII aquí",
        ]

        results = redactor.redact_batch(texts)

        assert len(results) == 3
        assert results[0].has_pii is True
        assert results[1].has_pii is True
        assert results[2].has_pii is False

    def test_validate_redaction(self, redactor: PIIRedactor) -> None:
        """Test redaction validation."""
        # Clean text should have no remaining PII
        clean_text = "Hola, mi consulta es sobre [EMAIL] y [TELEFONO]"
        remaining = redactor.validate_redaction(clean_text)
        assert len(remaining) == 0

        # Text with PII should be detected
        dirty_text = "Mi email es test@example.com"
        remaining = redactor.validate_redaction(dirty_text)
        assert "email" in remaining

    def test_empty_text(self, redactor: PIIRedactor) -> None:
        """Test handling of empty text."""
        result = redactor.redact("")
        assert result.text == ""
        assert result.has_pii is False

    def test_unicode_handling(self, redactor: PIIRedactor) -> None:
        """Test handling of unicode characters."""
        text = "Dirección: Av. José María Caro 1234, Ñuñoa"
        result = redactor.redact(text)

        # Should still detect the address
        assert "[DIRECCION]" in result.text
