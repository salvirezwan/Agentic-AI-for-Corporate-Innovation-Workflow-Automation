# src/schemas.py
from pydantic import BaseModel
from typing import List, Optional, Any

class StartRequest(BaseModel):
    company_name: str

class AnswerItem(BaseModel):
    question: str
    answer: str

class AnswerRequest(BaseModel):
    answers: List[AnswerItem]

class UploadFileResponse(BaseModel):
    status: str
    file: str
