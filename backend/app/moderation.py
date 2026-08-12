from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModerationResult:
    flagged: bool
    categories: list[str] = field(default_factory=list)
    reason: str | None = None


def _dump_categories(categories: object) -> dict[str, bool]:
    dumped = getattr(categories, "model_dump", None)
    if callable(dumped):
        dumped_categories = dumped()
        if isinstance(dumped_categories, dict):
            return dumped_categories

    if isinstance(categories, dict):
        return categories

    return {}


async def check_content_moderation(text: str) -> ModerationResult:
    if not settings.moderation_enabled or not text.strip():
        return ModerationResult(flagged=False)

    if not settings.openai_api_key or not settings.openai_api_key.get_secret_value().strip():
        logger.warning("Moderation check skipped: OPENAI_API_KEY is not configured.")
        return ModerationResult(flagged=False)

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
        async with asyncio.timeout(settings.moderation_timeout_seconds):
            response = await client.moderations.create(
                input=text,
                model=settings.moderation_model,
            )

        if not response.results:
            return ModerationResult(flagged=False)

        first_result = response.results[0]
        if not first_result.flagged:
            return ModerationResult(flagged=False)

        categories_dict = _dump_categories(first_result.categories)
        flagged_categories = [category for category, is_flagged in categories_dict.items() if is_flagged]
        reason = "Content violates safety guidelines."
        if flagged_categories:
            reason = f"Content violates safety guidelines ({', '.join(flagged_categories)})."

        logger.warning("User input flagged by moderation API. Categories: %s", ", ".join(flagged_categories) or "none")
        return ModerationResult(flagged=True, categories=flagged_categories, reason=reason)

    except Exception:
        logger.exception("Moderation API request failed.")
        if settings.moderation_fail_open:
            logger.warning("Moderation fail-open policy active: allowing request despite moderation error.")
            return ModerationResult(flagged=False)

        return ModerationResult(
            flagged=True,
            reason="Moderation service is temporarily unavailable. Please try again later.",
        )
