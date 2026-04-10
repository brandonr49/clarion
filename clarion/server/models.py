"""Pydantic request/response models for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# -- Note Models --


class LocationData(BaseModel):
    lat: float
    lon: float


class NoteCreate(BaseModel):
    content: str
    source_client: str
    input_method: str
    location: LocationData | None = None
    metadata: dict = Field(default_factory=dict)


class NoteResponse(BaseModel):
    id: str
    content: str
    source_client: str
    input_method: str
    location: dict | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: str
    status: str
    processed_at: str | None = None
    error: str | None = None


class NoteCreateResponse(BaseModel):
    note_id: str
    status: str
    created_at: str


class NoteListResponse(BaseModel):
    notes: list[NoteResponse]
    total: int
    limit: int
    offset: int


class NoteEdit(BaseModel):
    content: str
    reason: str


class NoteEditResponse(BaseModel):
    id: str
    content: str
    previous_content: str
    edited_at: str
    reason: str


# -- Query Models --


class QueryRequest(BaseModel):
    query: str
    source_client: str = "web"
    prefer_view: str | None = None


class QueryResponse(BaseModel):
    query_id: str
    raw_text: str


# -- Clarification Models --


class ClarificationResponse(BaseModel):
    id: str
    note_id: str
    question: str
    created_at: str


class ClarificationListResponse(BaseModel):
    clarifications: list[ClarificationResponse]


# -- Status Models --


class StatusResponse(BaseModel):
    status: str
    version: str


# -- Error Models --


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
