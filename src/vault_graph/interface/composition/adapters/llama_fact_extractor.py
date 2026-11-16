"""Session fact extractor that calls a local `llama-server` (spec 2026-11-16 D18, F7, F8).

It posts one OpenAI-compatible request to `<endpoint>/v1/chat/completions` with the configured model and a
`json_schema` response format, and checks the answer like the Claude CLI adapter. It sends no API key. Only
`fact_extractor_selection` imports this module (I2).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from vault_graph.interface.composition.adapters.claude_fact_extractor import (
    FACTS_SCHEMA,
    build_facts_prompt,
    parse_facts_answer,
)
from vault_graph.interface.composition.adapters.fact_extractor import (
    ExtractedFact,
    FactExchange,
    FactExtractorUnavailable,
    FactOutputInvalid,
)
from vault_graph.operation.scope.facts_settings import LOCAL_FACTS_ENDPOINT

LLAMA_TIMEOUT_SECONDS = 900.0


class LlamaFactExtractor:
    """`FactExtractor` that calls the `llama-server` chat completion endpoint."""

    extractor = "llama-server"

    def __init__(
        self,
        *,
        endpoint: str | None = LOCAL_FACTS_ENDPOINT,
        model: str,
        timeout_seconds: float = LLAMA_TIMEOUT_SECONDS,
    ) -> None:
        self.endpoint = (endpoint or LOCAL_FACTS_ENDPOINT).rstrip("/")
        self.model = model
        self._timeout_seconds = timeout_seconds

    def extract(self, exchanges: Sequence[FactExchange]) -> list[ExtractedFact]:
        if not exchanges:
            return []
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": build_facts_prompt(exchanges)}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "session_facts", "strict": True, "schema": FACTS_SCHEMA},
            },
            "temperature": 0,
            "stream": False,
            # Thinking models (Qwen3.5) otherwise reason for thousands of tokens first: about 190 s against
            # 14 s per session part on this Mac, with a similar number of facts (spec 2026-11-16 D18).
            "chat_template_kwargs": {"enable_thinking": False},
        }
        url = f"{self.endpoint}/v1/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise FactExtractorUnavailable(f"llama-server at {url} answered HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise FactExtractorUnavailable(f"llama-server at {url} did not answer: {exc}") from exc
        return parse_facts_answer(_message_content(raw), exchanges)


def _message_content(raw: bytes) -> str:
    try:
        payload: Any = json.loads(raw.decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise FactOutputInvalid("llama-server answer is not a chat completion") from exc
    if not isinstance(content, str):
        raise FactOutputInvalid("llama-server chat completion has no text content")
    return content
