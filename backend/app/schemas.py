from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_OPTIONS = {"A", "B", "C", "D"}


class LoginRequest(BaseModel):
    password: str


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    aruco_id: int = Field(ge=0)


class StudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    aruco_id: int
    created_at: datetime


class StudentAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class StudentLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class StudentMe(BaseModel):
    id: int
    name: str
    email: str



class QuestionCreate(BaseModel):
    text: str = Field(min_length=1)
    option_a: str = Field(min_length=1, max_length=500)
    option_b: str = Field(min_length=1, max_length=500)
    option_c: str = Field(min_length=1, max_length=500)
    option_d: str = Field(min_length=1, max_length=500)
    correct_option: str

    @field_validator("correct_option")
    @classmethod
    def validar_opcion_correcta(cls, value: str) -> str:
        value = value.upper()
        if value not in VALID_OPTIONS:
            raise ValueError("correct_option debe ser A, B, C o D")
        return value


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    created_at: datetime


class SessionCreate(BaseModel):
    question_id: int
