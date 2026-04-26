"""Standard API envelope (`Docs/Architecture.md` — API contract)."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: str | None = None


class APIEnvelope(BaseModel, Generic[T]):
    success: bool = True
    message: str | None = None
    data: T | None = None
    errors: list[ErrorDetail] = Field(default_factory=list)
