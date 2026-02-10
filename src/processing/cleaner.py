"""Text cleaning pipeline for support tickets."""

import html
import json
import re
from dataclasses import dataclass
from enum import Enum


class Channel(str, Enum):
    EMAIL = "email"
    SOCIAL = "social"
    WEB = "web"
    CHAT = "chat"
    OTHER = "other"


@dataclass
class CleanedTicket:
    """Represents a cleaned ticket ready for processing."""

    ticket_id: int
    text_full: str
    text_customer_only: str
    text_agent_only: str
    channel: str
    word_count: int


class TextCleaner:
    """Cleans and normalizes text from support tickets."""

    # Email signature patterns (Spanish)
    EMAIL_SIGNATURE_PATTERNS = [
        r"^--\s*$",
        r"^_{2,}",
        r"^-{2,}",
        r"^Enviado desde mi (?:iPhone|iPad|Android|Samsung|Huawei)",
        r"^Sent from my (?:iPhone|iPad|Android)",
        r"^Saludos,?\s*$",
        r"^Atentamente,?\s*$",
        r"^Cordialmente,?\s*$",
        r"^Un abrazo,?\s*$",
        r"^Gracias,?\s*$",
        r"^Quedo atento,?\s*$",
        r"^Quedo atenta,?\s*$",
        r"^Best regards,?\s*$",
        r"^Kind regards,?\s*$",
        r"^Thanks,?\s*$",
        r"^Get Outlook for",
        r"^\*{3,}",
    ]

    # Quoted reply patterns
    QUOTED_REPLY_PATTERNS = [
        r"^>+\s*",  # Lines starting with >
        r"^El .+ escribió:$",  # "El [fecha] [nombre] escribió:"
        r"^On .+ wrote:$",  # English variant
        r"^De:\s*",  # "De: [sender]"
        r"^From:\s*",
        r"^Enviado:\s*",
        r"^Sent:\s*",
        r"^Para:\s*",
        r"^To:\s*",
        r"^Asunto:\s*",
        r"^Subject:\s*",
        r"^Fecha:\s*",
        r"^Date:\s*",
        r"^\*De:\*",  # Bold variants
        r"^\*From:\*",
    ]

    # Auto-response patterns
    AUTO_RESPONSE_PATTERNS = [
        r"este es un mensaje automático",
        r"this is an automated message",
        r"no-reply",
        r"noreply",
        r"do not reply",
        r"no responder",
        r"mensaje generado automáticamente",
        r"respuesta automática",
        r"auto-reply",
        r"autoreply",
        r"out of office",
        r"fuera de la oficina",
    ]

    # URL patterns (tracking links, etc.)
    URL_PATTERN = re.compile(
        r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[^\s]*",
        re.IGNORECASE,
    )

    # HTML patterns
    HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
    HTML_ENTITY_PATTERN = re.compile(r"&[a-zA-Z]+;|&#\d+;")

    # Social media patterns
    SOCIAL_MENTION_PATTERN = re.compile(r"@[\w]+")
    SOCIAL_HASHTAG_PATTERN = re.compile(r"#[\w]+")

    def __init__(self) -> None:
        self._signature_regex = re.compile(
            "|".join(self.EMAIL_SIGNATURE_PATTERNS),
            re.MULTILINE | re.IGNORECASE,
        )
        self._quoted_regex = re.compile(
            "|".join(self.QUOTED_REPLY_PATTERNS),
            re.MULTILINE | re.IGNORECASE,
        )
        self._auto_response_regex = re.compile(
            "|".join(self.AUTO_RESPONSE_PATTERNS),
            re.IGNORECASE,
        )

    def clean_html(self, text: str) -> str:
        """Remove HTML tags and decode entities."""
        # Remove HTML tags
        text = self.HTML_TAG_PATTERN.sub(" ", text)
        # Decode HTML entities
        text = html.unescape(text)
        return text

    def remove_urls(self, text: str, replace_with: str = "[URL]") -> str:
        """Remove or replace URLs in text."""
        return self.URL_PATTERN.sub(replace_with, text)

    def remove_email_signatures(self, text: str) -> str:
        """Remove common email signature patterns."""
        lines = text.split("\n")
        clean_lines = []
        in_signature = False

        for line in lines:
            # Check if this line starts a signature
            if self._signature_regex.search(line):
                in_signature = True

            if not in_signature:
                clean_lines.append(line)

        return "\n".join(clean_lines)

    def remove_quoted_replies(self, text: str) -> str:
        """Remove quoted reply content from emails."""
        lines = text.split("\n")
        clean_lines = []
        in_quote = False

        for line in lines:
            # Check if this line starts a quote block
            if self._quoted_regex.search(line):
                in_quote = True

            # Lines starting with > are quoted
            if line.strip().startswith(">"):
                in_quote = True
                continue

            if not in_quote:
                clean_lines.append(line)

        return "\n".join(clean_lines)

    def is_auto_response(self, text: str) -> bool:
        """Check if text appears to be an auto-response."""
        return bool(self._auto_response_regex.search(text.lower()))

    def clean_social_media(self, text: str) -> str:
        """
        Clean social media text while preserving meaningful content.

        - Normalize mentions to [MENTION]
        - Keep hashtags as they may be relevant
        - Keep emojis (can be useful for sentiment)
        """
        # Normalize mentions but keep a placeholder
        text = self.SOCIAL_MENTION_PATTERN.sub("[USUARIO]", text)
        return text

    def normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace in text."""
        # Replace multiple spaces with single space
        text = re.sub(r"[ \t]+", " ", text)
        # Replace multiple newlines with double newline
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Strip leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split("\n")]
        return "\n".join(lines).strip()

    def clean_text(
        self,
        text: str,
        channel: Channel = Channel.EMAIL,
        remove_urls: bool = True,
    ) -> str:
        """
        Apply full cleaning pipeline to text.

        Args:
            text: Raw text to clean
            channel: Source channel (affects cleaning strategy)
            remove_urls: Whether to remove/replace URLs

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # HTML cleaning (applies to all channels)
        text = self.clean_html(text)

        # URL handling
        if remove_urls:
            text = self.remove_urls(text)

        # Channel-specific cleaning
        if channel in (Channel.EMAIL, Channel.WEB):
            text = self.remove_email_signatures(text)
            text = self.remove_quoted_replies(text)
        elif channel == Channel.SOCIAL:
            text = self.clean_social_media(text)

        # Final normalization
        text = self.normalize_whitespace(text)

        return text

    def separate_messages(
        self,
        comments_json: str,
        requester_email: str | None = None,
    ) -> tuple[list[str], list[str]]:
        """
        Separate comments into customer and agent messages.

        Args:
            comments_json: JSON string of comments
            requester_email: Email of the ticket requester (customer)

        Returns:
            Tuple of (customer_messages, agent_messages)
        """
        try:
            comments = json.loads(comments_json) if comments_json else []
        except json.JSONDecodeError:
            return [], []

        customer_messages = []
        agent_messages = []

        for comment in comments:
            body = comment.get("body", "")
            if not body:
                continue

            is_public = comment.get("public", True)
            author_id = comment.get("author_id")

            # Heuristic: public messages from requester are customer messages
            # Internal notes and agent replies go to agent_messages
            if is_public and author_id:
                # This is a simplification - in production you'd match author_id
                # to the requester_id from the ticket
                customer_messages.append(body)
            else:
                agent_messages.append(body)

        return customer_messages, agent_messages

    def process_ticket(
        self,
        ticket_id: int,
        subject: str | None,
        description: str | None,
        comments_json: str | None,
        channel: str | None,
        requester_email: str | None = None,
    ) -> CleanedTicket:
        """
        Process a raw ticket into a cleaned ticket.

        Args:
            ticket_id: Ticket ID
            subject: Ticket subject
            description: Ticket description
            comments_json: JSON string of comments
            channel: Source channel
            requester_email: Customer email

        Returns:
            CleanedTicket with cleaned and separated text
        """
        # Determine channel enum
        channel_enum = Channel.OTHER
        if channel:
            channel_lower = channel.lower()
            if "email" in channel_lower or "mail" in channel_lower:
                channel_enum = Channel.EMAIL
            elif any(s in channel_lower for s in ["twitter", "facebook", "instagram", "social"]):
                channel_enum = Channel.SOCIAL
            elif "web" in channel_lower or "form" in channel_lower:
                channel_enum = Channel.WEB
            elif "chat" in channel_lower:
                channel_enum = Channel.CHAT

        # Separate messages
        customer_msgs, agent_msgs = self.separate_messages(
            comments_json or "[]",
            requester_email,
        )

        # Include description in customer messages if present
        if description:
            customer_msgs.insert(0, description)

        # Clean all messages
        clean_customer = [
            self.clean_text(msg, channel_enum) for msg in customer_msgs
        ]
        clean_agent = [
            self.clean_text(msg, channel_enum) for msg in agent_msgs
        ]

        # Filter out auto-responses
        clean_customer = [
            msg for msg in clean_customer
            if msg and not self.is_auto_response(msg)
        ]
        clean_agent = [
            msg for msg in clean_agent
            if msg and not self.is_auto_response(msg)
        ]

        # Combine texts
        text_customer_only = "\n\n".join(clean_customer)
        text_agent_only = "\n\n".join(clean_agent)

        # Full text includes subject + all messages
        full_parts = []
        if subject:
            full_parts.append(f"Asunto: {subject}")
        full_parts.extend(clean_customer)
        full_parts.extend(clean_agent)
        text_full = "\n\n".join(full_parts)

        # Count words
        word_count = len(text_full.split()) if text_full else 0

        return CleanedTicket(
            ticket_id=ticket_id,
            text_full=text_full,
            text_customer_only=text_customer_only,
            text_agent_only=text_agent_only,
            channel=channel_enum.value,
            word_count=word_count,
        )
