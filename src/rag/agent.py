from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.rag.prompts import build_repair_prompt, build_supply_chain_prompt
from src.rag.retriever import retrieve_context


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma:2b")


def analyze_with_rag(raw_text: str, metadata: dict[str, Any] | None = None) -> str:
    """
    Convert raw supply-chain text into SupplyChainAnalysis JSON using:
    local knowledge retrieval + Ollama local LLM generation.
    """
    metadata = _with_metadata_defaults(metadata)
    retrieved_context = retrieve_context(raw_text, top_k=5)
    prompt = build_supply_chain_prompt(raw_text, retrieved_context, metadata)
    response_text = _call_ollama(prompt)
    return _coerce_valid_json_string(response_text)


def repair_agent_output(
    raw_text: str,
    invalid_json: str,
    validation_error: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    metadata = _with_metadata_defaults(metadata)
    prompt = build_repair_prompt(raw_text, invalid_json, validation_error, metadata)
    response_text = _call_ollama(prompt)
    return _coerce_valid_json_string(response_text)


def _with_metadata_defaults(metadata: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(metadata or {})
    data.setdefault("organization_id", "org-greenchem-demo")
    data.setdefault("document_id", "doc-rag-ollama-001")
    data.setdefault("source_type", "RAW_DOCUMENT")
    data.setdefault("filename", "unknown.txt")
    data.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())
    return data


def _call_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
        },
    }

    request = Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(
            "Could not call Ollama. Make sure Ollama is running and the model "
            f"'{OLLAMA_MODEL}' is installed. Original error: {exc}"
        ) from exc

    data = json.loads(raw)
    return data.get("response", "")


def _coerce_valid_json_string(text: str) -> str:
    """
    Ollama JSON mode should return JSON, but this helper keeps the pipeline
    resilient if a small model adds text around the object.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Ollama did not return a JSON object: {text[:500]}")
        parsed = json.loads(cleaned[start : end + 1])

    return json.dumps(parsed, indent=2)
