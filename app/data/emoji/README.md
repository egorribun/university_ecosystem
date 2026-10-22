# Unicode Emoji 18.0 membership data

`emoji_18_0_qualified_sequences.txt` is generated from the official Unicode Emoji 18.0
`emoji-test.txt` source at
<https://www.unicode.org/Public/18.0.0/emoji/emoji-test.txt>.
The pinned source SHA-256 is
`8f3735cda1f92a779d78af67cf86066bb1f07143dc22f2ac29394d9bc57ab21a`.
The generated ASCII file contains 4,992 code-point sequences whose source
status is exactly `fully-qualified` or `minimally-qualified`; each line is one
sequence, represented by uppercase hexadecimal code points separated by spaces.
Unqualified sequences and standalone components are omitted. The source enumerates fully-qualified, minimally-qualified, unqualified, and
Emoji_Component records. This API intentionally accepts only fully-qualified
and minimally-qualified sequences; standalone components are excluded. The set includes valid ZWJ, modifier,
keycap, regional-flag, and tag sequences; arbitrary concatenations are not
included.

To reproduce the file, download that exact source URL and run:

```powershell
python app/data/emoji/generate.py path/to/emoji-test.txt app/data/emoji/emoji_18_0_qualified_sequences.txt
```

The generator verifies the pinned source SHA-256 and data version before writing.
The generated file SHA-256 is
`56eb5190116bfec86b4bee875731e878599f76641a7217458614fef971cb6f0e`.
The backend checks this digest at import, so a missing or changed membership set
fails closed. Do not edit the generated file by hand; update the pinned source,
regenerate, update both hashes, and review the exact set change together.

The source data and derived data are covered by the Unicode License v3
(`Unicode-3.0`); the license text is retained in `LICENSE.txt`. Unicode's
official licensing FAQ identifies `Unicode-3.0` as the SPDX identifier and
states that most Unicode data files are released under that license:
<https://www.unicode.org/faq/unicode_license.html>.
