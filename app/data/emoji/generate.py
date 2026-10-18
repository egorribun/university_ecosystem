from __future__ import annotations

import argparse
import re
from hashlib import sha256
from pathlib import Path

SOURCE_URL = "https://www.unicode.org/Public/18.0.0/emoji/emoji-test.txt"
SOURCE_SHA256 = "8f3735cda1f92a779d78af67cf86066bb1f07143dc22f2ac29394d9bc57ab21a"
EXPECTED_VERSION = "18.0"
ACCEPTED_STATUSES = frozenset({"fully-qualified", "minimally-qualified"})
_RECORD = re.compile(
    r"^\s*([0-9A-F]+(?:\s+[0-9A-F]+)*)\s*;\s*"
    r"(fully-qualified|minimally-qualified|unqualified|component)\s+#"
)


def parse_emoji_test(source_text: str) -> list[str]:
    """Return exact code-point rows for qualified Emoji 18.0 sequences only."""
    if f"# Version: {EXPECTED_VERSION}" not in source_text.splitlines():
        raise ValueError("Unicode emoji data version mismatch")

    accepted: set[str] = set()
    for line in source_text.splitlines():
        match = _RECORD.match(line)
        if match is None or match.group(2) not in ACCEPTED_STATUSES:
            continue
        sequence = " ".join(match.group(1).split())
        for codepoint_text in sequence.split():
            codepoint = int(codepoint_text, 16)
            if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
                raise ValueError("Unicode emoji data contains an invalid code point")
        accepted.add(sequence)

    if not accepted:
        raise ValueError("Unicode emoji data contains no qualified sequences")
    return sorted(accepted)


def generate_file(source_path: Path, output_path: Path) -> None:
    """Verify the pinned upstream input, then write its compact membership set."""
    raw_source = source_path.read_bytes()
    actual_hash = sha256(raw_source).hexdigest()
    if actual_hash != SOURCE_SHA256:
        raise ValueError("Unicode emoji source checksum mismatch")
    sequences = parse_emoji_test(raw_source.decode("utf-8"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(("\n".join(sequences) + "\n").encode("ascii"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="verified upstream emoji-test.txt")
    parser.add_argument("output", type=Path, help="generated membership data path")
    args = parser.parse_args()
    generate_file(args.source, args.output)


if __name__ == "__main__":
    main()
