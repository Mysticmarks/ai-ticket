"""Validation utilities that prefer Pydantic but fall back to a minimal local implementation."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Iterable

try:  # pragma: no cover - exercised when Pydantic is installed
    from pydantic import BaseModel as PydanticBaseModel
    from pydantic import ValidationError as PydanticValidationError
except ImportError:  # pragma: no cover - fallback covered by unit tests

    class ValidationError(Exception):
        """Simplified validation error with a Pydantic-like interface."""

        def __init__(self, errors: Iterable[Dict[str, Any]]) -> None:
            super().__init__("Validation failed")
            self._errors = list(errors)

        def errors(self) -> list[Dict[str, Any]]:
            return self._errors

    class _ModelMeta(type):
        def __new__(mcls, name: str, bases: tuple[type, ...], namespace: Dict[str, Any]):
            annotations: Dict[str, Any] = {}
            for base in reversed(bases):
                annotations.update(getattr(base, "__annotations__", {}))
            annotations.update(namespace.get("__annotations__", {}))
            namespace["__annotations__"] = annotations

            extra_behavior = "ignore"
            config_cls = namespace.get("Config")
            if config_cls is not None and hasattr(config_cls, "extra"):
                extra_behavior = getattr(config_cls, "extra")
            else:
                for base in bases:
                    extra_behavior = getattr(getattr(base, "__config__", SimpleNamespace(extra="ignore")), "extra", extra_behavior)

            namespace["__config__"] = SimpleNamespace(extra=extra_behavior)
            cls = super().__new__(mcls, name, bases, namespace)
            return cls

    class BaseModel(metaclass=_ModelMeta):
        """Very small subset of the Pydantic BaseModel API used by the service."""

        def __init__(self, **data: Any) -> None:
            annotations: Dict[str, Any] = getattr(self, "__annotations__", {})
            values: Dict[str, Any] = {}
            errors = []
            for field_name in annotations:
                if field_name not in data:
                    errors.append({"loc": [field_name], "msg": "field required", "type": "value_error.missing"})
                else:
                    values[field_name] = data.pop(field_name)
            if errors:
                raise ValidationError(errors)

            self.__data = values
            extra_behavior = getattr(self.__class__, "__config__", SimpleNamespace(extra="ignore")).extra
            if extra_behavior == "forbid" and data:
                raise ValidationError(
                    {"loc": [name], "msg": "extra fields not permitted", "type": "value_error.extra"} for name in data
                )
            if extra_behavior == "allow":
                for key, value in data.items():
                    self.__data[key] = value
            self.__dict__.update(self.__data)

        def dict(self) -> Dict[str, Any]:
            return dict(self.__data)

    __all__ = ["BaseModel", "ValidationError"]

else:  # pragma: no cover
    BaseModel = PydanticBaseModel
    ValidationError = PydanticValidationError
    __all__ = ["BaseModel", "ValidationError"]
