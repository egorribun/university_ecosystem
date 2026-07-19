import sys

try:
    import atheris

    HAS_ATHERIS = True
except ImportError, RuntimeError:
    HAS_ATHERIS = False

if HAS_ATHERIS:
    with atheris.instrument_imports():
        from app.services.content_processing import SanitizationMode, sanitize
else:
    try:
        from app.services.content_processing import SanitizationMode, sanitize
    except ImportError:
        pass


def TestOneInput(data):
    if not HAS_ATHERIS:
        return
    fdp = atheris.FuzzedDataProvider(data)
    try:
        # Generate random string with size between 0 and 10000
        html = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 10000))
        # Pick one mode from SanitizationMode enum
        mode = fdp.PickValueInList(list(SanitizationMode))
        sanitize(html, mode=mode)
    except ValueError:
        pass


def main():
    if not HAS_ATHERIS:
        print("Atheris not installed. Skipping fuzz test.")
        sys.exit(0)
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
