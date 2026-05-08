import re
from typing import Annotated

from pydantic import AfterValidator


def _validate_hex_color(v: str) -> str:
    if not re.match(r"^#[0-9A-Fa-f]{6}$", v):
        raise ValueError("Must be a valid 6-digit hex color, e.g. #FF5733.")
    return v.upper()


# Reusable annotated type — apply to any color field in any schema.
HexColor = Annotated[str, AfterValidator(_validate_hex_color)]
