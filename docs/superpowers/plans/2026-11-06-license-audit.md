# License Audit Implementation Plan

> **For agentic workers:** Root owns Git and implementation. Three read-only
> reviewers independently inventory npm/assets, Python/Rust, and Go/containers.

**Goal:** Audit licensing across documentation, package metadata, bundled
materials, dependencies, and distribution artifacts; fix supported
contradictions without withdrawing prior permissions or weakening gates.

**Architecture:** Inventory the audited development and default-branch
snapshots, record evidence and unresolved ownership separately, reconcile
first-party notices and distribution paths, and retain repeatable verification.

**Tech Stack:** Git, JSON/TOML lockfiles and manifests, upstream license texts,
existing package/build tooling, Markdown audit and component inventories.

## Tasks

- [x] Enumerate tracked manifests, notices, archives, assets, copied code,
      skills/reference tooling, dependency graphs, and container declarations.
- [x] Audit all project-wide license assertions and first-party metadata,
      including immutable component archives and historical notices.
- [x] Classify dependency and service licenses with upstream evidence;
      distinguish runtime, build, development, and independent service roles.
- [x] Repair confirmed documentation/metadata/packaging contradictions.
      Preserve third-party notices and record unverifiable ownership explicitly.
- [x] Prepare bounded machine-readable inventories and an evidence-backed
      audit with counts, limitations, unresolved items, and maintainer actions.
- [x] Validate changed metadata and distributions, run relevant tests and
      existing hooks, and prepare the review change targeting `egorribun`. Do not merge or bypass
      required checks, change scanner dispositions, or fix unrelated vulnerabilities.

Integration: submit this verified change through the ordinary PR flow to `egorribun`. Merge, main promotion and deployment are separate owner-controlled actions. The audit retains open rights/provenance items; this plan does not certify full legal clearance or full CI.
