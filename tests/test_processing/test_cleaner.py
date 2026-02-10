"""Tests for text cleaner."""

import pytest

from src.processing.cleaner import Channel, TextCleaner


class TestTextCleaner:
    """Tests for TextCleaner."""

    @pytest.fixture
    def cleaner(self) -> TextCleaner:
        return TextCleaner()

    def test_clean_html_removes_tags(self, cleaner: TextCleaner) -> None:
        """Test HTML tag removal."""
        text = "<p>Hello <b>world</b>!</p>"
        result = cleaner.clean_html(text)
        assert "<p>" not in result
        assert "<b>" not in result
        assert "Hello" in result
        assert "world" in result

    def test_clean_html_decodes_entities(self, cleaner: TextCleaner) -> None:
        """Test HTML entity decoding."""
        text = "Caf&eacute; &amp; T&eacute;"
        result = cleaner.clean_html(text)
        assert "Café" in result
        assert "&" in result

    def test_remove_urls(self, cleaner: TextCleaner) -> None:
        """Test URL removal."""
        text = "Visita https://example.com/path?param=value para más info"
        result = cleaner.remove_urls(text)
        assert "https://example.com" not in result
        assert "[URL]" in result
        assert "para más info" in result

    def test_remove_email_signatures_spanish(self, cleaner: TextCleaner) -> None:
        """Test removal of Spanish email signatures."""
        text = """Hola, necesito ayuda con mi pedido.

Saludos,
Juan Pérez
Gerente de Ventas
Tel: +56 9 1234 5678"""

        result = cleaner.remove_email_signatures(text)
        assert "necesito ayuda" in result
        assert "Gerente de Ventas" not in result

    def test_remove_email_signatures_sent_from(self, cleaner: TextCleaner) -> None:
        """Test removal of 'Sent from' signatures."""
        text = """Por favor revisen mi caso.

Enviado desde mi iPhone"""

        result = cleaner.remove_email_signatures(text)
        assert "revisen mi caso" in result
        assert "iPhone" not in result

    def test_remove_quoted_replies(self, cleaner: TextCleaner) -> None:
        """Test removal of quoted email replies."""
        text = """Gracias por la respuesta.

El 15 de enero de 2024 escribió:
> Mensaje anterior
> con múltiples líneas"""

        result = cleaner.remove_quoted_replies(text)
        assert "Gracias por la respuesta" in result
        assert "Mensaje anterior" not in result

    def test_is_auto_response_spanish(self, cleaner: TextCleaner) -> None:
        """Test detection of Spanish auto-responses."""
        auto_text = "Este es un mensaje automático. No responder."
        normal_text = "Hola, tengo una consulta sobre mi pedido."

        assert cleaner.is_auto_response(auto_text) is True
        assert cleaner.is_auto_response(normal_text) is False

    def test_clean_social_media(self, cleaner: TextCleaner) -> None:
        """Test social media text cleaning."""
        text = "@tienda Hola, mi pedido no llegó #ayuda #reclamo"
        result = cleaner.clean_social_media(text)

        assert "[USUARIO]" in result
        assert "#ayuda" in result  # Hashtags preserved
        assert "pedido" in result

    def test_normalize_whitespace(self, cleaner: TextCleaner) -> None:
        """Test whitespace normalization."""
        text = "Hola    mundo\n\n\n\nMás texto"
        result = cleaner.normalize_whitespace(text)

        assert "Hola mundo" in result
        assert "\n\n\n" not in result

    def test_clean_text_full_pipeline_email(self, cleaner: TextCleaner) -> None:
        """Test full cleaning pipeline for email."""
        text = """<p>Hola, necesito ayuda con mi pedido.</p>

<p>El número es 12345.</p>

Visita https://tracking.com/123 para ver el estado.

Saludos,
María

El 10 de enero escribió:
> Mensaje anterior"""

        result = cleaner.clean_text(text, Channel.EMAIL)

        assert "necesito ayuda" in result
        assert "<p>" not in result
        assert "[URL]" in result
        assert "Mensaje anterior" not in result

    def test_clean_text_social_channel(self, cleaner: TextCleaner) -> None:
        """Test cleaning for social media channel."""
        text = "@tienda Mi pedido #1234 no llegó 😡"
        result = cleaner.clean_text(text, Channel.SOCIAL)

        assert "[USUARIO]" in result
        assert "😡" in result  # Emoji preserved

    def test_separate_messages(self, cleaner: TextCleaner) -> None:
        """Test message separation."""
        comments_json = """[
            {"id": 1, "body": "Mensaje del cliente", "author_id": 100, "public": true},
            {"id": 2, "body": "Respuesta del agente", "author_id": 200, "public": false}
        ]"""

        customer, agent = cleaner.separate_messages(comments_json)

        assert len(customer) == 1
        assert "Mensaje del cliente" in customer[0]
        assert len(agent) == 1
        assert "Respuesta del agente" in agent[0]

    def test_process_ticket(self, cleaner: TextCleaner) -> None:
        """Test full ticket processing."""
        result = cleaner.process_ticket(
            ticket_id=12345,
            subject="Problema con pedido",
            description="No me llegó mi pedido #999",
            comments_json='[{"id": 1, "body": "Mensaje adicional", "author_id": 100, "public": true}]',
            channel="email",
        )

        assert result.ticket_id == 12345
        assert "Problema con pedido" in result.text_full
        assert result.word_count > 0
        assert result.channel == "email"

    def test_process_ticket_handles_none_values(self, cleaner: TextCleaner) -> None:
        """Test ticket processing with None values."""
        result = cleaner.process_ticket(
            ticket_id=12345,
            subject=None,
            description=None,
            comments_json=None,
            channel=None,
        )

        assert result.ticket_id == 12345
        assert result.channel == "other"
