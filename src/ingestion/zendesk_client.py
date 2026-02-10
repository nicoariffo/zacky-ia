"""Zendesk API client with rate limiting and cursor-based pagination."""

import json
import time
from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings

logger = structlog.get_logger()


@dataclass
class Ticket:
    """Represents a Zendesk ticket with all relevant fields."""

    ticket_id: int
    subject: str | None
    description: str | None
    comments: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    tags: list[str]
    channel: str | None
    assignee_id: int | None
    status: str | None
    priority: str | None
    requester_email: str | None

    def to_bq_row(self) -> dict[str, Any]:
        """Convert to BigQuery row format."""
        return {
            "ticket_id": self.ticket_id,
            "subject": self.subject,
            "description": self.description,
            "comments_json": json.dumps(self.comments, ensure_ascii=False),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tags": self.tags,
            "channel": self.channel,
            "assignee_id": self.assignee_id,
            "status": self.status,
            "priority": self.priority,
            "requester_email": self.requester_email,
            "ingested_at": datetime.utcnow().isoformat(),
        }


class ZendeskClient:
    """Client for interacting with the Zendesk API."""

    def __init__(
        self,
        subdomain: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
    ):
        settings = get_settings()
        self.subdomain = subdomain or settings.zendesk_subdomain
        self.email = email or settings.zendesk_email
        self.api_token = api_token or settings.zendesk_api_token

        self.base_url = f"https://{self.subdomain}.zendesk.com/api/v2"
        self._client = httpx.Client(
            auth=(f"{self.email}/token", self.api_token),
            timeout=30.0,
            headers={"Content-Type": "application/json"},
        )

        # Rate limiting state
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: float | None = None

    def _handle_rate_limit(self, response: httpx.Response) -> None:
        """Track and handle rate limiting from Zendesk API."""
        self._rate_limit_remaining = int(
            response.headers.get("X-Rate-Limit-Remaining", 100)
        )
        retry_after = response.headers.get("Retry-After")

        if retry_after:
            self._rate_limit_reset = time.time() + int(retry_after)

        # Proactive rate limit handling
        if self._rate_limit_remaining is not None and self._rate_limit_remaining < 10:
            wait_time = 60  # Wait 1 minute if getting close to limit
            logger.warning(
                "Rate limit low, waiting",
                remaining=self._rate_limit_remaining,
                wait_seconds=wait_time,
            )
            time.sleep(wait_time)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=60),
    )
    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a rate-limited request to the Zendesk API."""
        url = f"{self.base_url}{endpoint}"

        # Check if we need to wait for rate limit reset
        if (
            self._rate_limit_reset is not None
            and time.time() < self._rate_limit_reset
        ):
            wait_time = self._rate_limit_reset - time.time()
            logger.info("Waiting for rate limit reset", wait_seconds=wait_time)
            time.sleep(wait_time)

        response = self._client.request(method, url, **kwargs)
        self._handle_rate_limit(response)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            logger.warning("Rate limited, waiting", retry_after=retry_after)
            time.sleep(retry_after)
            raise Exception("Rate limited")  # Will be retried by tenacity

        response.raise_for_status()
        return response.json()

    def get_ticket(self, ticket_id: int) -> Ticket:
        """Get a single ticket by ID."""
        data = self._request("GET", f"/tickets/{ticket_id}.json")
        ticket_data = data["ticket"]
        comments = self._get_ticket_comments(ticket_id)

        return self._parse_ticket(ticket_data, comments)

    def _get_ticket_comments(self, ticket_id: int) -> list[dict[str, Any]]:
        """Get all comments for a ticket."""
        comments = []
        endpoint = f"/tickets/{ticket_id}/comments.json"

        while endpoint:
            data = self._request("GET", endpoint)
            comments.extend(data.get("comments", []))

            # Handle pagination
            next_page = data.get("next_page")
            if next_page:
                endpoint = next_page.replace(self.base_url, "")
            else:
                endpoint = None

        return comments

    def _parse_ticket(
        self, ticket_data: dict[str, Any], comments: list[dict[str, Any]]
    ) -> Ticket:
        """Parse raw ticket data into a Ticket object."""
        # Determine channel from ticket via field
        via = ticket_data.get("via", {})
        channel = via.get("channel")

        # Parse comments to extract relevant fields
        parsed_comments = []
        for comment in comments:
            parsed_comments.append({
                "id": comment.get("id"),
                "body": comment.get("body"),
                "author_id": comment.get("author_id"),
                "public": comment.get("public", True),
                "created_at": comment.get("created_at"),
            })

        return Ticket(
            ticket_id=ticket_data["id"],
            subject=ticket_data.get("subject"),
            description=ticket_data.get("description"),
            comments=parsed_comments,
            created_at=datetime.fromisoformat(
                ticket_data["created_at"].replace("Z", "+00:00")
            ),
            updated_at=datetime.fromisoformat(
                ticket_data["updated_at"].replace("Z", "+00:00")
            ),
            tags=ticket_data.get("tags", []),
            channel=channel,
            assignee_id=ticket_data.get("assignee_id"),
            status=ticket_data.get("status"),
            priority=ticket_data.get("priority"),
            requester_email=ticket_data.get("requester", {}).get("email")
            if isinstance(ticket_data.get("requester"), dict)
            else None,
        )

    def iter_tickets(
        self,
        start_time: datetime | None = None,
        cursor: str | None = None,
    ) -> Generator[tuple[Ticket, str | None], None, None]:
        """
        Iterate over tickets using cursor-based pagination.

        Yields tuples of (ticket, next_cursor) to support checkpointing.
        """
        if cursor:
            endpoint = f"/incremental/tickets/cursor.json?cursor={cursor}"
        elif start_time:
            unix_time = int(start_time.timestamp())
            endpoint = f"/incremental/tickets/cursor.json?start_time={unix_time}"
        else:
            # Default: start from 1 year ago
            unix_time = int(time.time()) - (365 * 24 * 60 * 60)
            endpoint = f"/incremental/tickets/cursor.json?start_time={unix_time}"

        while True:
            data = self._request("GET", endpoint)

            tickets = data.get("tickets", [])
            after_cursor = data.get("after_cursor")
            end_of_stream = data.get("end_of_stream", False)

            logger.info(
                "Fetched ticket batch",
                count=len(tickets),
                end_of_stream=end_of_stream,
            )

            for ticket_data in tickets:
                try:
                    # Fetch comments for each ticket
                    comments = self._get_ticket_comments(ticket_data["id"])
                    ticket = self._parse_ticket(ticket_data, comments)
                    yield ticket, after_cursor
                except Exception as e:
                    logger.error(
                        "Error parsing ticket",
                        ticket_id=ticket_data.get("id"),
                        error=str(e),
                    )
                    continue

            if end_of_stream or not after_cursor:
                break

            endpoint = f"/incremental/tickets/cursor.json?cursor={after_cursor}"

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "ZendeskClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
