# Claude Code instructions

`AGENTS.md` is the single canonical repository instruction file. Read it in
full before changing code, tests, infrastructure, workflows, or documentation,
and follow it as if its contents appeared directly in this file.

In particular:

- work on the `egorribun` branch unless the user explicitly requests another;
- never add a `Co-Authored-By` trailer;
- do not label testing, coverage, or quality-maintenance work as a business
  wave;
- preserve the exception-handling, SQLAlchemy relationship, frontend
  validation, security, Docker, and CI conventions defined in `AGENTS.md`;
- use `docs/README.md` as the canonical documentation index and
  `docs/audits/INDEX.md` for historical audit evidence.

Do not append session transcripts, prompts, handoffs, coverage snapshots, or
wave-by-wave history here. Durable architectural decisions belong in
`docs/adr/`; executable quality policy belongs in `quality/`; temporary work
plans belong outside the long-lived instruction surface and should be removed
after completion.
