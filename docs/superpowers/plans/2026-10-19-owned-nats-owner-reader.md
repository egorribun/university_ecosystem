# Existing signed-owner file boundary

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

The pure supplied-byte parser has 66 verified cases. The first reader slice introduced an unavailable seam and 24 existing-file tests. After observed RED it was implemented; all 24 passed on e5588a0, job 118329557122, along with all 66 parser cases. This remains a read-only metadata boundary, not runtime admission.

## Required contract

- Use the caller's same Deadline; stop dispatching new reads/stats/opens after observed expiry.
- Initially walk from / through each absolute state-root component and .secrets using directory-relative O_DIRECTORY/O_NOFOLLOW/O_CLOEXEC. Reject traversal components and initial symlink ancestors.
- Open only live-stand.json and live-stand-owner.key relative to the retained secrets descriptor, read-only with O_NOFOLLOW/O_NONBLOCK/O_CLOEXEC; require regular files.
- Marker cap is 65536 bytes, key exactly 32 bytes. Reads must remain bounded, including wrong/oversized inputs; no creation, replacement, chmod or rotation of existing files.
- Close every acquired descriptor even after expiry. Local, network and FUSE syscalls cannot be hard-preempted by these pre/post checks.
- Return repr-private SIGNED_METADATA only after the existing parser succeeds. Initial descriptor traversal does not establish that current ancestor pathnames still name the same directories after concurrent rename. Post-read chain revalidation, mutation/replacement races and lifecycle locking remain further requirements before runtime admission.

## Tests first

- [x] Add fail-closed seam with no I/O or runtime wiring.
- [x] Add 24 cases using real temporary files, independent canonical signing, read-only open guards, preserved capability probes, symlink/FIFO rejection, size bounds and descriptor cleanup.
- [x] Observe both positive-file status assertions and the read-triggered expiry oracle RED on c94d9be, job 118309305597.
- [x] Implement only this reader after intended RED, then verify all 24 cases on e5588a0.
- [ ] Add mutation/replacement and ancestor-path revalidation tests before combining with lifecycle locking or runtime admission.

POSIX-specific cases require supported descriptor APIs and flags. Capability-negative cases still verify fail-closed behavior before any open. Synthetic test keys are deterministic fixture bytes, not live credentials. The reader never invokes legacy key creation/loaders, Docker, SQL, HTTP, coordinator or CLI; the approved outage remains disabled.

## Minimal reader after observed RED

The 24 reader tests and 66 parser cases are unchanged. Initial nofollow component traversal and bounded regular-file reads are followed by both descriptor/name snapshot checks after both reads. Every acquired fd receives one reverse-order close attempt, including after deadline expiry; ambiguous interrupted closes are not retried. Ordinary cleanup errors prevent SIGNED_METADATA, and pending interrupts propagate after remaining cleanup attempts. Own-source initial GREEN is verified. Additional mutation/interrupt/close-failure oracles and post-read ancestor checks remain required before any lock or runtime wiring. This is neither an atomic file-pair snapshot nor authenticated key provenance.

## Extended tests-first boundary

The next 46-case cohort preserves the original 24, adds four post-key-EOF leaf replacement/metadata checks and twelve interrupt/ordinary-close cases, then six ancestor rename/symlink cases expected to expose the missing post-read chain check. Their execution is pending. Close interrupts cover release-then-interrupt; ordinary OSError covers both released and intentionally unreleased outcomes. Assertions distinguish one cleanup attempt from actual release, and test-only cleanup handles explicitly unreleased fixture descriptors. No atomic namespace snapshot, lock, key provenance or runtime admission is claimed.

## Ancestor revalidation after observed RED

On c1a9e0f / job 118334645347, all 40 pre-existing/leaf/fault cases pass and exactly six ancestor cases reach the forbidden parser. The follow-up retains every initially validated parent/name/child descriptor edge and rechecks directory type plus device/inode identity after both leaf checks, before parsing. It uses no new descriptor or deadline. A new expiry-during-revalidation test requires both leaf EOFs, the exact second state-root observation, parser exclusion, no later open/read/stat and full descriptor cleanup. Own-source GREEN is pending. These sequential checks are still not atomic namespace binding, lifecycle locking or authenticated key provenance.

The unchanged six ancestor counterexamples and new expiry oracle pass on 0869fab / job 118341023558: all 47 reader cases, 66 parser cases, 46 event cursor cases and both HTTP cases pass. Early aggregate is 671 PASS / 1 FAIL at 22:30:01 UTC; only the existing disabled-outage workflow hold remains. The next lock slice is independently unavailable/tests-first, not runtime admission.

## Explicit private-descriptor policy tests first

On 965a82d7859c01141f55e0981e2c189c8e2cad7b, checkout 541a03f73d8cea5431ef55dd0d1f2ef2a0ca2e8b has exact tree 25a692011f144e49c099ec4e121705aca0581def. Focused job 118391989539 reports 726 PASS / 1 existing disabled-outage workflow FAIL in 187.19 seconds. All fifty-five lifecycle/composition cases pass, including every previously observed leased-reader counterexample. This does not enable outage or authenticate file provenance.

The next tests-first slice requires pinned_owner_uid explicitly on both filesystem-reader APIs and forwards it unchanged through composition. The argument is accepted but not yet enforced in this source; do not mistake its presence for provenance validation. Caller fixtures provide their known creator UID and normalize only their own root/.secrets/marker/key objects to the existing writer contract (0700 directories, 0600 leaves). Standalone lock policy and all existing assertions remain unchanged.

Ten additive cases use explicit hosted POSIX capability assertions, not new skip markers: valid private objects; None/bool/negative pins; four noncontract modes; independently observed UID mismatch on each protected object; retained run-root mode drift after reads. Parser recording forwards to the real parser so initial RED is the explicit NOT_READY assertion, not an artificial guard exception. Every UID-loop iteration owns fresh parser/descriptor/deadline observations. Mutations and ambient UID lookup during the reader call are prohibited and recorded; cleanup counters remain exact.

After observed RED, policy checks should reuse already-observed descriptor metadata, without additional filesystem calls or altered deadline/ancestor sequencing. Required UID must be an exact nonnegative int. Only the retained run root/.secrets and marker/key receive exact private-mode checks; ordinary ancestors and lock helpers keep their current semantics. UID joins leaf metadata snapshots. Existing baseline metadata has zero entries for all three edited Python files; no baseline change is needed.

UID/private modes establish sampled caller-selected policy only. They cannot prove original creator, historical privacy, exclusive key possession, atomicity, absence of ACL/privileged access, or exclusion of same-UID self-consistent key/marker replacement. Trusted CI creation remains an external precondition. No chmod/chown, new credential, Docker/SQL/HTTP adapter, coordinator replacement or CLI wiring is added to production.

## Observed private-policy RED and metadata-only enforcement

The ten private-policy cases on 19a2f8a produce one valid-object PASS and nine intended SIGNED_METADATA-versus-NOT_READY failures. Focused job 118398335180 totals 727 PASS / 10 FAIL in 263.41 seconds, including the existing disabled-outage workflow hold. Existing reader and all fifty-five lock/composition cases retain their assertions.

The next implementation validates exact nonnegative integer pinned_owner_uid before I/O, reuses each already observed directory stat result, and checks only run-root/.secrets descriptors against UID/0700. Leaf snapshots include UID and require UID/0600 after the existing descriptor/name comparison. Initial and post-read checks use the same observations and deadline sequence; no extra filesystem calls, permission repair, default identity, exception swallowing or cleanup changes are introduced. Ordinary ancestors and standalone locks keep their previous semantics.

Own corrected-source GREEN is pending. Sampled UID/private modes are not original-creator authentication, historical privacy, exclusive key possession, atomicity or protection from same-UID self-consistent key/marker replacement. Trusted CI creation remains a precondition; Docker/SQL/HTTP adapters, coordinator/CLI wiring and outage remain disabled.

The initial UID loop spoofs descriptor metadata only. For leaves, named/descriptor UID disagreement can itself reject. A self-consistent wrong-UID leaf and same-UID re-signed replacement remain useful distinct follow-on tests; the current implementation explicitly checks UID but this initial cohort is not exhaustive provenance proof.
