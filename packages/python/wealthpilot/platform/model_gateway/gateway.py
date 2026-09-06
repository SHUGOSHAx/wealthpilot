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
        output = response.structured_output
        if set(output) != {"research_summary", "interpretation"}:
            raise ModelOutputError("model output must use the narrative-only schema")
        if not all(isinstance(output[key], str) and output[key] for key in output):
            raise ModelOutputError("model narrative fields must be non-empty strings")
        return response

    @abstractmethod
    def _generate(self, request: ModelRequest) -> ModelResponse:
        """Provider adapter hook; called only after boundary validation."""
