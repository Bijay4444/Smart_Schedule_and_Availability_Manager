"""Groq transport only; credentials and SDK objects stay outside scheduling logic."""
from django.conf import settings
from groq import Groq, GroqError, RateLimitError


class AssistantUnavailable(Exception):
    pass


def complete(messages, tools):
    if not settings.GROQ_API_KEY:
        raise AssistantUnavailable("Chat is not configured yet. Set GROQ_API_KEY on the server using a Groq Free-tier account.")
    try:
        with Groq(api_key=settings.GROQ_API_KEY, timeout=15, max_retries=0) as client:
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL, messages=messages, tools=tools,
                tool_choice="auto", max_completion_tokens=1000,
            )
        return response.choices[0].message.model_dump(exclude_none=True)
    except RateLimitError:
        raise AssistantUnavailable("The model's free quota is temporarily exhausted. Wait before trying again; no paid fallback is enabled.") from None
    except (GroqError, IndexError):
        raise AssistantUnavailable("The chat provider could not answer. Please try again shortly.") from None
