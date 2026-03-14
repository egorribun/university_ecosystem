from pydantic import BaseModel as _PydanticBaseModel
from pydantic import ConfigDict


class SecureBaseModel(_PydanticBaseModel):
    """
    Project-wide base model with security hardening.
    - extra="forbid": Rejects unknown fields to prevent Mass Assignment (OWASP API3:2023)
    - validate_assignment=True: Ensures runtime validation when mutating fields
    - str_strip_whitespace=True: Standardizes string inputs
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        strict=False,
    )
