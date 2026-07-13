#!/usr/bin/env python
# tests/fuzz/run_atheris.py — coverage-guided Python API fuzzer
import sys

import atheris

# Instrument imports to track coverage
with atheris.instrument_imports():
    from fastapi import HTTPException
    from pydantic import ValidationError

    from app.auth.security import decode_token
    from app.schemas.schemas import ResetPasswordIn, UserPreferencesBase
    from app.utils.sanitization import (
        sanitize_filename,
        sanitize_html,
        sanitize_rich_text,
        sanitize_url,
    )
    from app.utils.uuid_v7 import extract_timestamp_from_uuid_v7


def TestOneInput(data):
    fdp = atheris.FuzzedDataProvider(data)

    # 1. Fuzz sanitization functions
    try:
        html_input = fdp.ConsumeUnicodeNoSurrogates(1000)
        allow_basic = fdp.ConsumeBool()
        sanitize_html(html_input, allow_basic_tags=allow_basic)
        sanitize_rich_text(html_input)
    except HTTPException:
        # Expected domain exception from sanitize_rich_text
        pass
    except Exception as e:
        # Raise any unexpected exceptions as bug crashes
        print(f"CRASH in HTML sanitization: {e}", file=sys.stderr)
        raise

    try:
        filename_input = fdp.ConsumeUnicodeNoSurrogates(500)
        max_len = fdp.ConsumeIntegerInRange(1, 300)
        sanitize_filename(filename_input, max_length=max_len)
    except Exception as e:
        print(f"CRASH in filename sanitization: {e}", file=sys.stderr)
        raise

    try:
        url_input = fdp.ConsumeUnicodeNoSurrogates(500)
        sanitize_url(url_input)
    except Exception as e:
        print(f"CRASH in URL sanitization: {e}", file=sys.stderr)
        raise

    # 2. Fuzz Pydantic validation (UserPreferencesBase)
    try:
        dnd_enabled = fdp.ConsumeBool()
        timezone = fdp.ConsumeUnicodeNoSurrogates(100)

        # Construct raw payload
        payload = {
            "dnd_enabled": dnd_enabled,
            "timezone": timezone,
        }
        # Sometimes provide time strings
        if fdp.ConsumeBool():
            payload["dnd_start"] = fdp.ConsumeUnicodeNoSurrogates(20)
        if fdp.ConsumeBool():
            payload["dnd_end"] = fdp.ConsumeUnicodeNoSurrogates(20)

        UserPreferencesBase.model_validate(payload)
    except ValidationError, ValueError:
        # Expected validation / domain logic errors
        pass
    except Exception as e:
        print(f"CRASH in UserPreferencesBase validation: {e}", file=sys.stderr)
        raise

    # 3. Fuzz Pydantic validation (ResetPasswordIn)
    try:
        token = fdp.ConsumeUnicodeNoSurrogates(100)
        password = fdp.ConsumeUnicodeNoSurrogates(300)
        payload = {"token": token, "password": password}
        ResetPasswordIn.model_validate(payload)
    except ValidationError, ValueError:
        # Expected validation / domain logic errors
        pass
    except Exception as e:
        print(f"CRASH in ResetPasswordIn validation: {e}", file=sys.stderr)
        raise

    # 4. Fuzz JWT decoding
    try:
        jwt_token = fdp.ConsumeUnicodeNoSurrogates(500)
        decode_token(jwt_token)
    except Exception as e:
        # Expected decode exceptions are caught inside decode_token and return None.
        # Unhandled library exceptions (e.g. key errors, structure issues) must raise to crash.
        print(f"CRASH in JWT decoding: {e}", file=sys.stderr)
        raise

    # 5. Fuzz UUID v7 extraction
    try:
        uuid_str = fdp.ConsumeUnicodeNoSurrogates(100)
        extract_timestamp_from_uuid_v7(uuid_str)
    except ValueError:
        # Expected ValueError for malformed UUID format
        pass
    except Exception as e:
        print(f"CRASH in UUID v7 extraction: {e}", file=sys.stderr)
        raise


def main():
    # Setup and run fuzzer
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
