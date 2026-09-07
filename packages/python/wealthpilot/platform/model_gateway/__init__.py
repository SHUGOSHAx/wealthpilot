"""The only model-service boundary used by WealthPilot business services."""

from .fake import FakeModelGateway
from .gateway import ModelGateway, ModelOutputError
from .models import ModelRequest, ModelResponse
from .openai_compatible import (
    ModelProviderError,
    OpenAICompatibleConfig,
    OpenAICompatibleModelGateway,
)

__all__ = [
    "FakeModelGateway",
    "ModelGateway",
    "ModelOutputError",
    "ModelProviderError",
    "ModelRequest",
    "ModelResponse",
    "OpenAICompatibleConfig",
    "OpenAICompatibleModelGateway",
]
