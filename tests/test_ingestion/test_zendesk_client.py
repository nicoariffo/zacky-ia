"""Tests for Zendesk client."""

from datetime import datetime, timezone

import pytest

from src.ingestion.zendesk_client import Ticket


class TestTicket:
    """Test Ticket dataclass."""

    def test_to_bq_row(self) -> None:
        """Test conversion to BigQuery row format."""
        ticket = Ticket(
            ticket_id=12345,
            subject="Test Subject",
            description="Test description",
            comments=[
                {"id": 1, "body": "Comment 1", "author_id": 100, "public": True},
                {"id": 2, "body": "Comment 2", "author_id": 200, "public": False},
            ],
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 16, 14, 0, 0, tzinfo=timezone.utc),
            tags=["tag1", "tag2"],
            channel="email",
            assignee_id=999,
            status="open",
            priority="high",
            requester_email="customer@example.com",
        )

        row = ticket.to_bq_row()

        assert row["ticket_id"] == 12345
        assert row["subject"] == "Test Subject"
        assert row["description"] == "Test description"
        assert "Comment 1" in row["comments_json"]
        assert "Comment 2" in row["comments_json"]
        assert row["tags"] == ["tag1", "tag2"]
        assert row["channel"] == "email"
        assert row["assignee_id"] == 999
        assert row["status"] == "open"
        assert row["priority"] == "high"
        assert row["requester_email"] == "customer@example.com"
        assert "ingested_at" in row

    def test_to_bq_row_with_none_values(self) -> None:
        """Test conversion handles None values correctly."""
        ticket = Ticket(
            ticket_id=12345,
            subject=None,
            description=None,
            comments=[],
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 16, 14, 0, 0, tzinfo=timezone.utc),
            tags=[],
            channel=None,
            assignee_id=None,
            status=None,
            priority=None,
            requester_email=None,
        )

        row = ticket.to_bq_row()

        assert row["ticket_id"] == 12345
        assert row["subject"] is None
        assert row["description"] is None
        assert row["comments_json"] == "[]"
        assert row["tags"] == []
        assert row["channel"] is None
        assert row["assignee_id"] is None

    def test_to_bq_row_unicode_handling(self) -> None:
        """Test that unicode characters are properly handled."""
        ticket = Ticket(
            ticket_id=12345,
            subject="Problema con pedido #123 - Devolución",
            description="Hola, necesito devolver mi pedido. ¿Cuánto demora?",
            comments=[
                {"id": 1, "body": "Gracias por contactarnos 😊", "author_id": 100, "public": True},
            ],
            created_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 16, 14, 0, 0, tzinfo=timezone.utc),
            tags=["devolución", "español"],
            channel="email",
            assignee_id=None,
            status="open",
            priority=None,
            requester_email=None,
        )

        row = ticket.to_bq_row()

        assert "Devolución" in row["subject"]
        assert "¿Cuánto demora?" in row["description"]
        assert "😊" in row["comments_json"]
        assert "devolución" in row["tags"]
