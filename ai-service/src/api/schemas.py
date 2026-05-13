from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    session_id: str
    question: str


class ChatResponse(BaseModel):
    answer: str


class HealthResponse(BaseModel):
    status: str