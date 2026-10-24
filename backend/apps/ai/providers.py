"""LLM provider adapters. The rest of the app only sees `complete()` and the message helpers.

- "anthropic": Claude via the official Anthropic SDK.
- "openai": any OpenAI-compatible Chat Completions API (OpenAI, Groq, Gemini's OpenAI endpoint, OpenRouter...).
The API key is read from settings (env) on the server only.
"""
import json
from dataclasses import dataclass, field

import requests
from django.conf import settings


class ProviderError(Exception):
    pass


class ProviderTimeout(ProviderError):
    pass


class ProviderUnconfigured(ProviderError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMTurn:
    text: str
    tool_calls: list = field(default_factory=list)
    assistant_message: dict = None  # provider-native message to append to history
    refused: bool = False


class AnthropicProvider:
    name = "anthropic"
    default_model = "claude-opus-5-5"

    def __init__(self, api_key, model=None, base_url=None, effort=None):
        import anthropic

        self._anthropic = anthropic
        kwargs = {"api_key": api_key, "max_retries": 0}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)
        self.model = model or self.default_model
        self.effort = effort

    def user_message(self, text):
        return {"role": "user", "content": text}

    def assistant_text(self, text):
        return {"role": "assistant", "content": text}

    def tool_results(self, results):
        return [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call.id, "content": content, "is_error": is_error}
            for call, content, is_error in results]}]

    def complete(self, *, system, messages, tools=None, timeout=15.0, max_tokens=2048):
        params = {"model": self.model, "max_tokens": max_tokens, "system": system, "messages": messages}
        if tools:
            params["tools"] = [{"name": t["name"], "description": t["description"],
                                "input_schema": t["parameters"]} for t in tools]
        if self.effort:
            params["output_config"] = {"effort": self.effort}
        try:
            response = self.client.with_options(timeout=timeout).messages.create(**params)
        except self._anthropic.APITimeoutError as exc:
            raise ProviderTimeout(str(exc))
        except self._anthropic.APIConnectionError as exc:
            raise ProviderError(f"connection: {exc}")
        except self._anthropic.APIStatusError as exc:
            raise ProviderError(f"{exc.status_code}: {exc.message}")
        text = "".join(b.text for b in response.content if b.type == "text")
        calls = [ToolCall(b.id, b.name, dict(b.input or {})) for b in response.content if b.type == "tool_use"]
        return LLMTurn(text=text, tool_calls=calls,
                       assistant_message={"role": "assistant", "content": response.content},
                       refused=response.stop_reason == "refusal")


class OpenAICompatibleProvider:
    name = "openai"
    default_model = "gpt-4o-mini"

    def __init__(self, api_key, model=None, base_url=None, effort=None):
        self.api_key = api_key
        self.model = model or self.default_model
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    def user_message(self, text):
        return {"role": "user", "content": text}

    def assistant_text(self, text):
        return {"role": "assistant", "content": text}

    def tool_results(self, results):
        return [{"role": "tool", "tool_call_id": call.id, "content": content} for call, content, _ in results]

    def complete(self, *, system, messages, tools=None, timeout=15.0, max_tokens=2048):
        body = {"model": self.model, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, *messages]}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
            body["tool_choice"] = "auto"
        try:
            r = requests.post(f"{self.base_url}/chat/completions", json=body, timeout=timeout,
                              headers={"Authorization": f"Bearer {self.api_key}"})
        except requests.Timeout as exc:
            raise ProviderTimeout(str(exc))
        except requests.RequestException as exc:
            raise ProviderError(f"connection: {exc}")
        if r.status_code >= 400:
            raise ProviderError(f"{r.status_code}: {r.text[:300]}")
        try:
            msg = r.json()["choices"][0]["message"]
        except (ValueError, KeyError, IndexError):
            raise ProviderError("Malformed provider response.")
        calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except ValueError:
                args = {"__invalid_json__": tc["function"].get("arguments")}
            calls.append(ToolCall(tc["id"], tc["function"]["name"], args if isinstance(args, dict) else {}))
        assistant = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            assistant["tool_calls"] = msg["tool_calls"]
        return LLMTurn(text=msg.get("content") or "", tool_calls=calls, assistant_message=assistant)


PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAICompatibleProvider}


def get_provider():
    if not settings.AI_API_KEY:
        raise ProviderUnconfigured("AI_API_KEY is not set on the server.")
    cls = PROVIDERS.get(settings.AI_PROVIDER)
    if cls is None:
        raise ProviderUnconfigured(f"Unknown AI_PROVIDER '{settings.AI_PROVIDER}'.")
    return cls(settings.AI_API_KEY, settings.AI_MODEL or None, settings.AI_BASE_URL or None,
               getattr(settings, "AI_EFFORT", "") or None)
