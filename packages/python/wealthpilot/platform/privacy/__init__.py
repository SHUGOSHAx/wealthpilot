"""Privacy enforcement at external model boundaries."""

from .guard import PrivacyBoundaryError, assert_model_safe

__all__ = ["PrivacyBoundaryError", "assert_model_safe"]
