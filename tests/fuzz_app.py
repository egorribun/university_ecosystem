"""Standalone Atheris harness for the deliberately small fuzz target.

The target lives in :mod:`tests.app`, rather than the production ``app``
package.  Atheris is only distributed for supported platforms, so importing
this module must remain safe on developer machines where it is unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import atheris
except ImportError:
    atheris = None

if atheris is not None:
    # Instrument the target import so Atheris can observe its branches.
    with atheris.instrument_imports():
        from tests.app import process_user_data
else:
    from tests.app import process_user_data


def TestOneInput(data):
    # Use FuzzedDataProvider to consume the raw bytes
    if atheris is None:
        raise RuntimeError("Atheris is required to execute the fuzz callback")
    fdp = atheris.FuzzedDataProvider(data)
    try:
        # Generate a string from the random data
        input_str = fdp.ConsumeUnicodeNoSurrogates(100)
        process_user_data(input_str)
    except ValueError, UnicodeDecodeError:
        # Catch expected exceptions to let the fuzzer continue
        pass


def main():
    if atheris is None:
        print("Atheris not available, skipping.")
        return
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
