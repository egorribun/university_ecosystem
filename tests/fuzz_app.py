import sys

try:
    import atheris
    # Instrument your code so Atheris can track coverage
    with atheris.instrument_imports():
        from app import process_user_data
    HAS_ATHERIS = True
except (ImportError, RuntimeError):
    from app import process_user_data
    HAS_ATHERIS = False


def TestOneInput(data):
    # Use FuzzedDataProvider to consume the raw bytes
    fdp = atheris.FuzzedDataProvider(data)
    try:
        # Generate a string from the random data
        input_str = fdp.ConsumeUnicodeNoSurrogates(100)
        process_user_data(input_str)
    except (ValueError, UnicodeDecodeError):
        # Catch expected exceptions to let the fuzzer continue
        pass


def main():
    if not HAS_ATHERIS:
        print("Atheris not available, skipping.")
        return
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
