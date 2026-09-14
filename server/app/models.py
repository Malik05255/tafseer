from typing import Literal
from pydantic import BaseModel, Field


class Answer(BaseModel):
    question_id: str
    question_text: str = ""
    value: str


class InterpretRequest(BaseModel):
    dream: str = Field(min_length=8, max_length=12000)
    answers: list[Answer] = []


class QuestionOption(BaseModel):
    id: str
    label: str


class Question(BaseModel):
    id: str
    title: str
    explanation: str
    options: list[QuestionOption] = []
    allow_text: bool = False
    text_hint: str = "اكتب إجابتك هنا…"


class Evidence(BaseModel):
    title: str
    explanation: str


class FinalResult(BaseModel):
    interpretation: str
    nature: Literal["coherent", "mixed", "daily_thoughts", "fragmented", "uncertain"]
    nature_label: str
    evidence: list[Evidence]
    alternatives: list[str]
    why_this_interpretation: str
    caution: str = "هذا تأويل اجتهادي وليس حكمًا يقينيًا، والله أعلم."


class InterpretResponse(BaseModel):
    status: Literal["question", "complete"]
    progress_checkpoint: int
    question: Question | None = None
    result: FinalResult | None = None
