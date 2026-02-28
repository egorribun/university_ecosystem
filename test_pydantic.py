from pydantic import BaseModel, ConfigDict


class SecureBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OrmModel(SecureBaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(OrmModel):
    id: int
    name: str


class DummyOrm:
    def __init__(self):
        self.id = 1
        self.name = "Test"
        self.extra_field = "Should be ignored"


try:
    UserOut(id=1, name="Test", extra_field="bad")
    print("Init with extra succeeded (BAD)")
except Exception as e:
    print("Init strict:", type(e).__name__)

try:
    obj = DummyOrm()
    out = UserOut.model_validate(obj)
    print("from_attributes succeeded")
except Exception as e:
    print("from_attributes failed:", e)
