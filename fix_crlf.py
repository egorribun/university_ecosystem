"""One-shot CRLF -> LF converter for events.py (TD-001)."""

path = "app/api/events.py"
data = open(path, "rb").read()
fixed = data.replace(b"\r\n", b"\n")
open(path, "wb").write(fixed)
before = data.count(b"\r\n")
after = fixed.count(b"\r\n")
print(f"Converted {path}: CRLF {before} -> {after}")
