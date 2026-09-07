"""Unified model gateway abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod

from wealthpilot.platform.privacy import assert_model_safe

from .models import ModelRequest, ModelResponse


class ModelOutputError(ValueError):
    """A provider returned data outside the narrative-only response contract."""


class ModelGateway(ABC):
    """Business code depends on this port, never on a vendor SDK."""

    def generate_structured(self, request: ModelRequest) -> ModelResponse:
        """Enforce privacy and the narrative-only schema around every adapter."""

        assert_model_safe(request.as_payload(), privacy_level=request.privacy_level)
        response = self._generate(request)
        _validate_output(request.response_contract, response.structured_output)
        return response

    @abstractmethod
    def _generate(self, request: ModelRequest) -> ModelResponse:
        """Provider adapter hook; called only after boundary validation."""


def _validate_output(contract: str, output: object) -> None:
    if not isinstance(output, dict):
        raise ModelOutputError("structured model output must be an object")
    if contract == "NARRATIVE_V1":
        if set(output) != {"research_summary", "interpretation"}:
            raise ModelOutputError("model output must use NARRATIVE_V1")
        if not all(isinstance(output[key], str) and output[key] for key in output):
            raise ModelOutputError("model narrative fields must be non-empty strings")
        return
    if contract == "EQUITY_RESEARCH_MEMO_V1":
        if set(output) != {"research_summary", "key_positives", "key_risks"}:
            raise ModelOutputError("model output must use EQUITY_RESEARCH_MEMO_V1")
        if not isinstance(output["research_summary"], str) or not output["research_summary"]:
            raise ModelOutputError("research_summary must be a non-empty string")
        for field in ("key_positives", "key_risks"):
            items = output[field]
            if not isinstance(items, list):
                raise ModelOutputError(f"{field} must be a list")
            for item in items:
                if not isinstance(item, dict) or set(item) != {"claim", "evidence_ids"}:
                    raise ModelOutputError(f"{field} items must be cited claims")
                if not isinstance(item["claim"], str) or not item["claim"]:
                    raise ModelOutputError("claim must be a non-empty string")
                if not isinstance(item["evidence_ids"], list) or not item["evidence_ids"]:
                    raise ModelOutputError("every claim must cite evidence")
                if not all(isinstance(value, str) and value for value in item["evidence_ids"]):
                    raise ModelOutputError("evidence IDs must be non-empty strings")
        return
    raise ModelOutputError(f"unsupported response contract: {contract}")
