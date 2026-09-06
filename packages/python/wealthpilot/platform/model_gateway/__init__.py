"""The only model-service boundary used by WealthPilot business services."""

from .fake import FakeModelGateway
from .gateway import ModelGateway, ModelOutputError
from .models import ModelRequest, ModelResponse

__all__ = ["FakeModelGateway", "ModelGateway", "ModelOutputError", "ModelRequest", "ModelResponse"]
