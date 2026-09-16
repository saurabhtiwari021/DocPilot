from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=72)


class UserOut(BaseModel):
    id: str
    username: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
