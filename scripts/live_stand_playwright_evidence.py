"""Pure validators for bounded Playwright evidence records used by live_stand."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

_PLAYWRIGHT_COUNT_LINE = re.compile(
    r" *(?P<count>0|[1-9][0-9]{0,4}) "
    r"(?P<kind>passed|failed|skipped|flaky|interrupted|did not run)"
    r"(?: \([0-9]{1,8}(?:\.[0-9])?(?:ms|s|m|h|d)\))? *"
)
_PLAYWRIGHT_FAILURE_HEADER = re.compile(
    r"  [1-9][0-9]{0,3}\) \[(?P<project>desktop|mobile)\] › "
    r"(?P<source>[^ :]{1,160}):(?P<line>[1-9][0-9]{0,4}):"
    r"(?P<column>[1-9][0-9]{0,4}) › "
)
_PLAYWRIGHT_FAILURE_DECLARATION_SOURCES = (
    "tests/e2e-live/activity-dashboard.live.spec.ts",
    "tests/e2e-live/activity-summary.live.spec.ts",
    "tests/e2e-live/admin-audit-rbac.live.spec.ts",
    "tests/e2e-live/admin-feature-flags-rbac.live.spec.ts",
    "tests/e2e-live/admin-notifications-rbac.live.spec.ts",
    "tests/e2e-live/admin-stories-rbac.live.spec.ts",
    "tests/e2e-live/admin-stories-smoke.live.spec.ts",
    "tests/e2e-live/admin-users-rbac.live.spec.ts",
    "tests/e2e-live/aud178-reset-referer-csp.live.spec.ts",
    "tests/e2e-live/auth-login-lockout.live.spec.ts",
    "tests/e2e-live/auth-roles.live.spec.ts",
    "tests/e2e-live/auth-safe-redirect.live.spec.ts",
    "tests/e2e-live/avatar-persistence.live.spec.ts",
    "tests/e2e-live/chat-attachment-isolation.live.spec.ts",
    "tests/e2e-live/core-a11y-live.live.spec.ts",
    "tests/e2e-live/email-otp-mfa-login.live.spec.ts",
    "tests/e2e-live/email-otp-verification.live.spec.ts",
    "tests/e2e-live/events-scroll-restoration.live.spec.ts",
    "tests/e2e-live/events-tab-keyboard.live.spec.ts",
    "tests/e2e-live/footer-bottom-navigation.live.spec.ts",
    "tests/e2e-live/map-gesture-isolation.live.spec.ts",
    "tests/e2e-live/map-zoom-longtask.live.spec.ts",
    "tests/e2e-live/messenger-a11y.live.spec.ts",
    "tests/e2e-live/messenger-focus-trap.live.spec.ts",
    "tests/e2e-live/messenger-group-isolation.live.spec.ts",
    "tests/e2e-live/messenger-keyboard-focus.live.spec.ts",
    "tests/e2e-live/messenger-membership-revocation.live.spec.ts",
    "tests/e2e-live/messenger-realtime.live.spec.ts",
    "tests/e2e-live/messenger-reconnect-ordering.live.spec.ts",
    "tests/e2e-live/messenger-reconnect.live.spec.ts",
    "tests/e2e-live/messenger-unread-read.live.spec.ts",
    "tests/e2e-live/navbar-layout-stability.live.spec.ts",
    "tests/e2e-live/new-chat-hit-targets.live.spec.ts",
    "tests/e2e-live/news-responsive-matrix.live.spec.ts",
    "tests/e2e-live/news-scroll-restoration.live.spec.ts",
    "tests/e2e-live/not-found-i18n.live.spec.ts",
    "tests/e2e-live/notification-in-app.live.spec.ts",
    "tests/e2e-live/notification-preferences.live.spec.ts",
    "tests/e2e-live/notification-topics-delivery.live.spec.ts",
    "tests/e2e-live/password-reset.live.spec.ts",
    "tests/e2e-live/profile-csrf.live.spec.ts",
    "tests/e2e-live/profile-persistence.live.spec.ts",
    "tests/e2e-live/push-delivery.live.spec.ts",
    "tests/e2e-live/push-permission-default.live.spec.ts",
    "tests/e2e-live/push-permission-denied.live.spec.ts",
    "tests/e2e-live/push-subscription.live.spec.ts",
    "tests/e2e-live/pwa-offline-shell-i18n.live.spec.ts",
    "tests/e2e-live/pwa-offline-shell.live.spec.ts",
    "tests/e2e-live/register-double-submit.live.spec.ts",
    "tests/e2e-live/schedule-200-equivalent-reflow.live.spec.ts",
    "tests/e2e-live/schedule-grid-keyboard.live.spec.ts",
    "tests/e2e-live/schedule-hydration-i18n.live.spec.ts",
    "tests/e2e-live/search-dialog-keyboard.live.spec.ts",
    "tests/e2e-live/settings-password-change-rollback.live.spec.ts",
    "tests/e2e-live/settings-radio-focus.live.spec.ts",
    "tests/e2e-live/settings-tabs-keyboard.live.spec.ts",
    "tests/e2e-live/settings-theme-roundtrip.live.spec.ts",
    "tests/e2e-live/ssr-hydration-i18n.live.spec.ts",
    "tests/e2e-live/story-viewer-keyboard.live.spec.ts",
    "tests/e2e-live/story-viewer-memory.live.spec.ts",
    "tests/e2e-live/story-viewer-reduced-motion.live.spec.ts",
    "tests/e2e-live/totp-recovery.live.spec.ts",
    "tests/e2e-live/zzz-aud174-prehydration-caddy-log.live.spec.ts",
)
_PLAYWRIGHT_FAILURE_SOURCES = {
    **{source: source for source in _PLAYWRIGHT_FAILURE_DECLARATION_SOURCES},
    **{
        source.replace("/", "\\"): source
        for source in _PLAYWRIGHT_FAILURE_DECLARATION_SOURCES
    },
}
_PLAYWRIGHT_FAILURE_FRAME_SOURCES = {
    **_PLAYWRIGHT_FAILURE_SOURCES,
    "tests/e2e-live/fixtures.ts": "tests/e2e-live/fixtures.ts",
    r"tests\e2e-live\fixtures.ts": "tests/e2e-live/fixtures.ts",
}
_PLAYWRIGHT_FAILURE_PROJECTS = {project: project for project in ("desktop", "mobile")}
_PLAYWRIGHT_FAILURE_FRAME = re.compile(
    r"        at (?:[^()]{1,256} \((?P<named>.+)\)|(?P<anonymous>.+))"
)
_PLAYWRIGHT_FRAME_LOCATION = re.compile(
    r"(?P<source>.{1,1024}):(?P<line>[1-9][0-9]{0,4}):"
    r"(?P<column>[1-9][0-9]{0,4})"
)
_PLAYWRIGHT_A11Y_CONTRAST_LINE = re.compile(
    r"UE_LIVE_A11Y_CONTRAST_V1 project=(?P<project>desktop|mobile) "
    r"route=(?P<route>dashboard|settings) "
    r"fg=(?P<foreground>#[0-9a-fA-F]{6}) bg=(?P<background>#[0-9a-fA-F]{6}) "
    r"ratio_milli=(?P<ratio>0|[1-9][0-9]{0,4})"
)
_PLAYWRIGHT_A11Y_CONTRAST_LIMIT = 16
_PLAYWRIGHT_A11Y_CONTRAST_PER_ROUTE_LIMIT = 4
_PlaywrightA11yContrast = tuple[str, str, str, str, int]

_PLAYWRIGHT_A11Y_PAINT_LINE = re.compile(
    r"UE_LIVE_A11Y_PAINT_V1 project=(?P<project>desktop|mobile) "
    r"route=(?P<route>dashboard|settings) "
    r"axe_fg=(?P<axe_foreground>#[0-9a-fA-F]{6}) "
    r"axe_bg=(?P<axe_background>#[0-9a-fA-F]{6}) "
    r"ratio_milli=(?P<ratio>0|[1-9][0-9]{0,4}) "
    r"css_fg=(?P<css_foreground>#[0-9a-fA-F]{6}) "
    r"text_color=(?P<text_color>opaque|translucent|transparent) "
    r"css_alpha_milli=(?P<css_alpha>0|[1-9][0-9]{0,2}|1000) "
    r"node_opacity_milli=(?P<node_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"ancestor_opacity_milli=(?P<ancestor_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"opacity_tag=(?P<opacity_tag>none|node|ancestor|fade|layout|fade-pending|multiple) "
    r"page_ready=(?P<page_ready>true|false) "
    r"page_opacity_milli=(?P<page_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"layout_opacity_milli=(?P<layout_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"animation=(?P<animation>none|opacity|transform|color|other|mixed) "
    r"active_animations=(?P<active_animations>0|[1-9][0-9]{0,2})"
)
_PLAYWRIGHT_A11Y_PAINT_LIMIT = 16
_PLAYWRIGHT_A11Y_PAINT_PER_ROUTE_LIMIT = 4
_PlaywrightA11yPaintState = tuple[
    str, str, str, str, int, str, str, int, int, int, str, bool, int, int, str, int
]

_PLAYWRIGHT_A11Y_PHASE_LINE = re.compile(
    r"UE_LIVE_A11Y_PHASE_V1 project=(?P<project>desktop|mobile) "
    r"route=(?P<route>dashboard|settings) "
    r"phase=(?P<phase>before_axe|after_axe) "
    r"page_ready=(?P<page_ready>true|false) "
    r"page_opacity_milli=(?P<page_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"root_opacity_milli=(?P<root_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"layout_opacity_milli=(?P<layout_opacity>0|[1-9][0-9]{0,2}|1000) "
    r"animation=(?P<animation>none|opacity|transform|color|other|mixed) "
    r"active_animations=(?P<active_animations>0|[1-9][0-9]{0,2})"
)
_PlaywrightA11yPhaseState = tuple[str, str, str, bool, int, int, int, str, int]

_PLAYWRIGHT_FOOTER_GEOMETRY_LINE = re.compile(
    r"UE_LIVE_FOOTER_GEOM_V1 project=(?P<project>desktop|mobile) "
    r"req_w_milli=(?P<requested_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"req_h_milli=(?P<requested_height>-?(?:0|[1-9][0-9]{0,6})) "
    r"inner_w_milli=(?P<inner_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"inner_h_milli=(?P<inner_height>-?(?:0|[1-9][0-9]{0,6})) "
    r"client_w_milli=(?P<client_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"scroll_w_milli=(?P<scroll_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_left_milli=(?P<nav_left>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_right_milli=(?P<nav_right>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_top_milli=(?P<nav_top>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_bottom_milli=(?P<nav_bottom>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_width_milli=(?P<nav_width>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_transform_present=(?P<nav_transform_present>true|false) "
    r"nav_tx_milli=(?P<nav_tx>-?(?:0|[1-9][0-9]{0,6})) "
    r"nav_ty_milli=(?P<nav_ty>-?(?:0|[1-9][0-9]{0,6})) "
    r"fixed_cb_found=(?P<fixed_cb_found>true|false) "
    r"fixed_cb_depth=(?P<fixed_cb_depth>0|[1-9][0-9]{0,1}|32) "
    r"cb_left_milli=(?P<cb_left>-?(?:0|[1-9][0-9]{0,6})) "
    r"cb_right_milli=(?P<cb_right>-?(?:0|[1-9][0-9]{0,6})) "
    r"cb_top_milli=(?P<cb_top>-?(?:0|[1-9][0-9]{0,6})) "
    r"cb_bottom_milli=(?P<cb_bottom>-?(?:0|[1-9][0-9]{0,6}))"
)
_PLAYWRIGHT_FOOTER_GEOMETRY_LIMIT = 16
_PlaywrightFooterGeometry = tuple[
    str,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    bool,
    int,
    int,
    bool,
    int,
    int,
    int,
    int,
    int,
]


_PLAYWRIGHT_NEWS_VIEWPORT_LINE = re.compile(
    r"UE_LIVE_NEWS_VIEWPORT_V1 project=(?P<project>desktop|mobile) "
    r"language=(?P<language>ru|en) "
    r"width=(?P<width>360|390|768|1024|1440) "
    r"viewportHeight=(?P<viewport_height>[1-9][0-9]{0,5}) "
    r"scrollY=(?P<scroll_y>-?(?:0|[1-9][0-9]{0,5})) "
    r"top=(?P<top>-?(?:0|[1-9][0-9]{0,5})) "
    r"bottom=(?P<bottom>-?(?:0|[1-9][0-9]{0,5})) "
    r"left=(?P<left>-?(?:0|[1-9][0-9]{0,5})) "
    r"right=(?P<right>-?(?:0|[1-9][0-9]{0,5}))"
)
_PLAYWRIGHT_NEWS_VIEWPORT_LIMIT = 20
_PlaywrightNewsViewport = tuple[str, str, int, int, int, int, int, int, int]


_PlaywrightPushObservation = tuple[str, str, str, str, bool, bool, int]
_PLAYWRIGHT_PUSH_OBSERVATION_LINE = re.compile(
    r"UE_LIVE_PUSH_OBS_V1 project=(?P<project>desktop|mobile) "
    r"permission=(?P<permission>default|granted|denied|unsupported) "
    r"ready=(?P<ready>resolved|timeout|error) "
    r"state=(?P<state>missing|installing|installed|activating|"
    r"activated|redundant|error) "
    r"controller=(?P<controller>[01]) subscription=(?P<subscription>[01]) "
    r"matches=(?P<matches>[01])"
)
_PLAYWRIGHT_PUSH_OBSERVATION_LIMIT = 4

_PLAYWRIGHT_STORY_MEMORY_PREFIX = "STORY_MEMORY_DIAG "
_PLAYWRIGHT_STORY_MEMORY_LINE_BYTES_LIMIT = 8192
_PLAYWRIGHT_STORY_MEMORY_RECORD_LIMIT = 4
_PLAYWRIGHT_STORY_MEMORY_MAX_COUNT = 9_007_199_254_740_991
_PLAYWRIGHT_STORY_MEMORY_DOM_KEYS = ("documents", "nodes", "jsEventListeners")
_PLAYWRIGHT_STORY_MEMORY_LISTENER_TARGETS = ("window", "document", "documentTree")
_PLAYWRIGHT_STORY_MEMORY_LISTENER_KEYS = (
    "total",
    "appinstalled",
    "beforeinstallprompt",
    "visibilitychange",
    "focus",
    "blur",
    "focusin",
    "focusout",
    "keydown",
    "keyup",
    "click",
    "ecosystem:push-education-requested",
    "mousedown",
    "mouseup",
    "pointerdown",
    "pointerup",
    "touchstart",
    "touchend",
    "online",
    "offline",
    "pwa:need-refresh",
    "resize",
    "scroll",
    "other",
)
_PLAYWRIGHT_STORY_MEMORY_RECORD_KEYS = (
    "schema",
    "project",
    "phase",
    "diagnosticStatus",
    "warmDOM",
    "cycle0DOM",
    "warmListeners",
    "cycle0Listeners",
)
_PlaywrightStoryMemoryRecord = dict[str, object]

_STORY_MEMORY_CYCLE_TRACE_PREFIX = "STORY_MEMORY_CYCLE_TRACE_DIAG "
_STORY_MEMORY_CYCLE_TRACE_KEYS = (
    "schema",
    "project",
    "diagnosticStatus",
    "samples",
)
_STORY_MEMORY_CYCLE_TRACE_SAMPLE_KEYS = (
    "baseline",
    "dialogOpen",
    "hiddenResumed",
    "afterCloseSettled",
)
_STORY_MEMORY_CYCLE_TRACE_COUNT_KEYS = ("documents", "nodes", "jsEventListeners")
_STORY_MEMORY_CYCLE_TRACE_LINE_BYTES_LIMIT = 2048
_STORY_MEMORY_CYCLE_TRACE_RECORD_LIMIT = 4


def _validated_story_memory_cycle_trace(value: object) -> dict[str, object] | None:
    record = _story_memory_object(value, _STORY_MEMORY_CYCLE_TRACE_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    status = record["diagnosticStatus"]
    if project not in ("desktop", "mobile") or status not in (
        "available",
        "partial",
        "unavailable",
    ):
        return None
    samples = _story_memory_object(
        record["samples"], _STORY_MEMORY_CYCLE_TRACE_SAMPLE_KEYS
    )
    if samples is None:
        return None
    normalized_samples: dict[str, dict[str, int] | None] = {}
    present = 0
    for sample_name in _STORY_MEMORY_CYCLE_TRACE_SAMPLE_KEYS:
        sample = samples[sample_name]
        if sample is None:
            normalized_samples[sample_name] = None
            continue
        counts = _story_memory_object(sample, _STORY_MEMORY_CYCLE_TRACE_COUNT_KEYS)
        if counts is None:
            return None
        normalized: dict[str, int] = {}
        for key in _STORY_MEMORY_CYCLE_TRACE_COUNT_KEYS:
            count = counts[key]
            if (
                type(count) is not int
                or count < 0
                or count > _PLAYWRIGHT_STORY_MEMORY_MAX_COUNT
            ):
                return None
            normalized[key] = count
        present += 1
        normalized_samples[sample_name] = normalized
    if (
        (status == "available" and present != 4)
        or (status == "partial" and not 1 <= present <= 3)
        or (status == "unavailable" and present != 0)
    ):
        return None
    return {
        "schema": 1,
        "project": project,
        "diagnosticStatus": status,
        "samples": normalized_samples,
    }


def _live_playwright_story_memory_cycle_trace_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _STORY_MEMORY_CYCLE_TRACE_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_STORY_MEMORY_CYCLE_TRACE_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_STORY_MEMORY_CYCLE_TRACE_PREFIX) :],
                object_pairs_hook=_story_memory_json_object,
                parse_constant=_reject_story_memory_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_story_memory_cycle_trace(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _STORY_MEMORY_CYCLE_TRACE_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


def _story_memory_object(
    value: object, expected_keys: tuple[str, ...]
) -> Mapping[str, object] | None:
    if not isinstance(value, dict):
        return None
    if set(value) != set(expected_keys):
        return None
    return value


def _story_memory_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate Story diagnostic key")
        value[key] = item
    return value


def _reject_story_memory_json_constant(value: str) -> None:
    raise ValueError(f"invalid Story diagnostic number: {value}")


def _story_memory_counts(
    value: object, expected_keys: tuple[str, ...], *, unavailable: bool
) -> dict[str, int | None] | None:
    record = _story_memory_object(value, expected_keys)
    if record is None:
        return None
    counts: dict[str, int | None] = {}
    for key in expected_keys:
        count = record[key]
        if unavailable:
            if count is not None:
                return None
            counts[key] = None
            continue
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or count < 0
            or count > _PLAYWRIGHT_STORY_MEMORY_MAX_COUNT
        ):
            return None
        counts[key] = count
    if not unavailable and "total" in counts:
        bucket_total = sum(
            count
            for key, count in counts.items()
            if key != "total" and count is not None
        )
        if bucket_total != counts["total"]:
            return None
    return counts


def _validated_story_memory_record(
    value: object,
) -> _PlaywrightStoryMemoryRecord | None:
    record = _story_memory_object(value, _PLAYWRIGHT_STORY_MEMORY_RECORD_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 2:
        return None
    project = record["project"]
    phase = record["phase"]
    status = record["diagnosticStatus"]
    if project not in ("desktop", "mobile"):
        return None
    if phase != "cycle0-after-settle-before-assertion":
        return None
    if status not in ("available", "unavailable"):
        return None

    unavailable = status == "unavailable"
    warm_dom = _story_memory_counts(
        record["warmDOM"], _PLAYWRIGHT_STORY_MEMORY_DOM_KEYS, unavailable=unavailable
    )
    cycle0_dom = _story_memory_counts(
        record["cycle0DOM"], _PLAYWRIGHT_STORY_MEMORY_DOM_KEYS, unavailable=unavailable
    )
    warm_listeners = _story_memory_object(
        record["warmListeners"], _PLAYWRIGHT_STORY_MEMORY_LISTENER_TARGETS
    )
    cycle0_listeners = _story_memory_object(
        record["cycle0Listeners"], _PLAYWRIGHT_STORY_MEMORY_LISTENER_TARGETS
    )
    if (
        warm_dom is None
        or cycle0_dom is None
        or warm_listeners is None
        or cycle0_listeners is None
    ):
        return None

    normalized_warm_listeners: dict[str, dict[str, int | None]] = {}
    normalized_cycle0_listeners: dict[str, dict[str, int | None]] = {}
    for target in _PLAYWRIGHT_STORY_MEMORY_LISTENER_TARGETS:
        warm_counts = _story_memory_counts(
            warm_listeners[target],
            _PLAYWRIGHT_STORY_MEMORY_LISTENER_KEYS,
            unavailable=unavailable,
        )
        cycle0_counts = _story_memory_counts(
            cycle0_listeners[target],
            _PLAYWRIGHT_STORY_MEMORY_LISTENER_KEYS,
            unavailable=unavailable,
        )
        if warm_counts is None or cycle0_counts is None:
            return None
        normalized_warm_listeners[target] = warm_counts
        normalized_cycle0_listeners[target] = cycle0_counts

    return {
        "schema": 2,
        "project": project,
        "phase": "cycle0-after-settle-before-assertion",
        "diagnosticStatus": status,
        "warmDOM": warm_dom,
        "cycle0DOM": cycle0_dom,
        "warmListeners": normalized_warm_listeners,
        "cycle0Listeners": normalized_cycle0_listeners,
    }


def _live_playwright_story_memory_records(
    output: str,
) -> list[_PlaywrightStoryMemoryRecord]:
    """Accept only the closed, byte-bounded Story memory diagnostic protocol."""
    records: list[_PlaywrightStoryMemoryRecord] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _PLAYWRIGHT_STORY_MEMORY_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_PLAYWRIGHT_STORY_MEMORY_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_PLAYWRIGHT_STORY_MEMORY_PREFIX) :],
                object_pairs_hook=_story_memory_json_object,
                parse_constant=_reject_story_memory_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_story_memory_record(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _PLAYWRIGHT_STORY_MEMORY_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_PLAYWRIGHT_STORY_SETUP_PREFIX = "STORY_SETUP_DIAG "
_PLAYWRIGHT_STORY_SETUP_LINE_BYTES_LIMIT = 512
_PLAYWRIGHT_STORY_SETUP_RECORD_LIMIT = 4
_PLAYWRIGHT_STORY_SETUP_KEYS = ("schema", "project", "stage", "exceptionKind")
_PLAYWRIGHT_STORY_SETUP_STAGES = (
    "browser-launch",
    "fixture-policy",
    "owner-cdp",
    "command-line",
    "debug-port",
    "cdp-attach",
    "default-context",
    "cookies",
    "main-target",
    "project-options",
    "bootstrap-listener",
    "login",
    "dashboard",
    "bootstrap",
    "story-trigger",
    "warm-up",
    "baseline",
    "cycle0",
    "measured-cycle",
    "acceptance",
    "cleanup",
)
_PLAYWRIGHT_STORY_SETUP_EXCEPTION_KINDS = (
    "error",
    "non-error",
    "cleanup",
    "error-with-cleanup",
    "non-error-with-cleanup",
)


def _validated_story_setup_record(value: object) -> dict[str, object] | None:
    record = _story_memory_object(value, _PLAYWRIGHT_STORY_SETUP_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    stage = record["stage"]
    exception_kind = record["exceptionKind"]
    if not isinstance(project, str) or project not in ("desktop", "mobile"):
        return None
    if not isinstance(stage, str) or stage not in _PLAYWRIGHT_STORY_SETUP_STAGES:
        return None
    if (
        not isinstance(exception_kind, str)
        or exception_kind not in _PLAYWRIGHT_STORY_SETUP_EXCEPTION_KINDS
    ):
        return None
    return {
        "schema": 1,
        "project": project,
        "stage": stage,
        "exceptionKind": exception_kind,
    }


def _live_playwright_story_setup_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    """Accept only closed, byte-bounded Story setup failures from stdout."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _PLAYWRIGHT_STORY_SETUP_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_PLAYWRIGHT_STORY_SETUP_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_PLAYWRIGHT_STORY_SETUP_PREFIX) :],
                object_pairs_hook=_story_memory_json_object,
                parse_constant=_reject_story_memory_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_story_setup_record(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _PLAYWRIGHT_STORY_SETUP_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_AUTH_UI_DIAG_PREFIX = "AUTH_UI_DIAG "
_AUTH_HTTP_DIAG_PREFIX = "AUTH_HTTP_DIAG "
_AUTH_DIAG_LINE_BYTES_LIMIT = 1024
_AUTH_DIAG_RECORD_LIMIT = 16
_AUTH_UI_DIAG_KEYS = (
    "schema",
    "project",
    "scenario",
    "status",
    "detailClass",
    "alertCount",
    "alertCountCapped",
    "alertVisible",
    "currentFieldInvalid",
    "loginChallenge",
    "pageError",
)
_AUTH_UI_DIAG_SCENARIOS = ("password_current_invalid", "totp_recovery_replay")
_AUTH_UI_DIAG_DETAIL_CLASSES = ("expected", "other-string", "non-string", "missing")
_AUTH_HTTP_DIAG_KEYS = ("schema", "project", "operation", "expectedStatus", "status")
_AUTH_HTTP_DIAG_EXPECTED_STATUS = {
    operation: (
        403
        if operation == "student_admin_read"
        else 400
        if operation in {"password_change_invalid", "totp_recovery_replay"}
        else 200
    )
    for operation in (
        "profile_read",
        "profile_identity_read",
        "password_settings_register",
        "totp_register",
        "password_change_invalid",
        "password_change_save",
        "totp_recovery_accept",
        "totp_recovery_replay",
        "push_topics_read",
        "push_subscribe",
        "push_topics_initial",
        "push_topics_optout",
        "push_unsubscribe",
        "push_rebind",
        "profile_update_enable",
        "profile_update_start",
        "profile_update_end",
        "profile_update_midnight_start",
        "profile_update_midnight_end",
        "profile_update_disable",
        "student_admin_read",
        "admin_topics_read",
        "admin_account_search",
        "admin_account_delete",
    )
}


def _auth_diag_object(
    value: object, expected_keys: tuple[str, ...]
) -> Mapping[str, object] | None:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    if set(value) != set(expected_keys):
        return None
    return value


def _auth_diag_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate auth diagnostic key")
        value[key] = item
    return value


def _reject_auth_diag_json_constant(value: str) -> None:
    raise ValueError(f"invalid auth diagnostic number: {value}")


def _validated_auth_ui_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _AUTH_UI_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    scenario = record["scenario"]
    status = record["status"]
    detail_class = record["detailClass"]
    alert_count = record["alertCount"]
    capped = record["alertCountCapped"]
    alert_visible = record["alertVisible"]
    current_invalid = record["currentFieldInvalid"]
    login_challenge = record["loginChallenge"]
    page_error = record["pageError"]
    if not isinstance(project, str) or project not in _PLAYWRIGHT_FAILURE_PROJECTS:
        return None
    if not isinstance(scenario, str) or scenario not in _AUTH_UI_DIAG_SCENARIOS:
        return None
    if type(status) is not int or not 100 <= status <= 599:
        return None
    if (
        not isinstance(detail_class, str)
        or detail_class not in _AUTH_UI_DIAG_DETAIL_CLASSES
    ):
        return None
    if type(alert_count) is not int or not 0 <= alert_count <= 8:
        return None
    if type(capped) is not bool or (capped and alert_count != 8):
        return None
    if type(alert_visible) is not bool:
        return None
    if type(page_error) is not bool:
        return None
    if scenario == "password_current_invalid":
        if type(current_invalid) is not bool or login_challenge is not None:
            return None
    elif current_invalid is not None or type(login_challenge) is not bool:
        return None
    return {
        "schema": 1,
        "project": project,
        "scenario": scenario,
        "status": status,
        "detailClass": detail_class,
        "alertCount": alert_count,
        "alertCountCapped": capped,
        "alertVisible": alert_visible,
        "currentFieldInvalid": current_invalid,
        "loginChallenge": login_challenge,
        "pageError": page_error,
    }


def _live_playwright_auth_ui_diagnostics(output: str) -> list[dict[str, object]]:
    """Retain only complete bounded Auth UI failure records from stdout."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _AUTH_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_AUTH_UI_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_AUTH_UI_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_auth_ui_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _AUTH_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


def _validated_auth_http_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _AUTH_HTTP_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    operation = record["operation"]
    expected_status = record["expectedStatus"]
    status = record["status"]
    if not isinstance(project, str) or project not in _PLAYWRIGHT_FAILURE_PROJECTS:
        return None
    if (
        not isinstance(operation, str)
        or operation not in _AUTH_HTTP_DIAG_EXPECTED_STATUS
    ):
        return None
    if (
        type(expected_status) is not int
        or expected_status != _AUTH_HTTP_DIAG_EXPECTED_STATUS[operation]
    ):
        return None
    if type(status) is not int or not 100 <= status <= 599:
        return None
    if status == expected_status:
        return None
    return {
        "schema": 1,
        "project": project,
        "operation": operation,
        "expectedStatus": expected_status,
        "status": status,
    }


_AUTH_REGISTRATION_DIAG_PREFIX = "AUTH_REGISTRATION_DIAG "
_AUTH_REGISTRATION_DIAG_KEYS = (
    "schema",
    "project",
    "scenario",
    "phase",
    "formValid",
    "submitEnabled",
    "requestObserved",
    "status",
)
_AUTH_REGISTRATION_DIAG_SCENARIOS = ("password-settings", "totp", "email-otp")
_AUTH_REGISTRATION_DIAG_PHASES = (
    "before-submit",
    "submit-click",
    "response-wait",
    "response-received",
    "navigation",
)
_AUTH_REGISTRATION_DIAG_LINE_BYTES_LIMIT = 512
_AUTH_REGISTRATION_DIAG_RECORD_LIMIT = 4


def _validated_auth_registration_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _AUTH_REGISTRATION_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    scenario = record["scenario"]
    phase = record["phase"]
    form_valid = record["formValid"]
    submit_enabled = record["submitEnabled"]
    request_observed = record["requestObserved"]
    status = record["status"]
    if not isinstance(project, str) or project not in _PLAYWRIGHT_FAILURE_PROJECTS:
        return None
    if (
        not isinstance(scenario, str)
        or scenario not in _AUTH_REGISTRATION_DIAG_SCENARIOS
    ):
        return None
    if not isinstance(phase, str) or phase not in _AUTH_REGISTRATION_DIAG_PHASES:
        return None
    if type(form_valid) is not bool or type(submit_enabled) is not bool:
        return None
    if type(request_observed) is not bool:
        return None
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        return None
    if phase == "before-submit" and (request_observed or status is not None):
        return None
    if phase == "submit-click" and status is not None and not request_observed:
        return None
    if phase == "response-wait" and status is not None:
        return None
    if phase in {"response-received", "navigation"} and (
        not request_observed or status is None
    ):
        return None
    return {
        "schema": 1,
        "project": project,
        "scenario": scenario,
        "phase": phase,
        "formValid": form_valid,
        "submitEnabled": submit_enabled,
        "requestObserved": request_observed,
        "status": status,
    }


def _live_playwright_auth_registration_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    """Retain only closed registration-failure rows from complete stdout lines."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _AUTH_REGISTRATION_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_AUTH_REGISTRATION_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_AUTH_REGISTRATION_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_auth_registration_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _AUTH_REGISTRATION_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_REGISTRATION_ADMISSION_DIAG_PREFIX = "REGISTRATION_ADMISSION_DIAG "
_REGISTRATION_ADMISSION_DIAG_KEYS = (
    "schema",
    "project",
    "stage",
    "errorClass",
    "nodeCode",
    "cost",
    "timeoutMs",
    "remainingMs",
    "requestCount",
    "activeRequestCount",
    "deadlineAvailable",
    "ownerPresent",
    "ledgerPresent",
    "requestObserved",
    "responseObserved",
    "actionFailed",
    "status",
)
_REGISTRATION_ADMISSION_DIAG_STAGES = (
    "deadline",
    "origin",
    "state-root",
    "owner-read",
    "ledger-read",
    "quiet-wait",
    "rolling-wait",
    "reserve",
    "submit",
    "request-drain",
    "confirm",
)
_REGISTRATION_ADMISSION_DIAG_ERROR_CLASSES = (
    "Error",
    "TypeError",
    "RangeError",
    "ReferenceError",
    "SyntaxError",
    "URIError",
    "EvalError",
    "AggregateError",
    "AbortError",
    "TimeoutError",
    "PlaywrightError",
    "AssertionError",
    "other",
)
_REGISTRATION_ADMISSION_DIAG_NODE_CODES = (
    "EACCES",
    "EADDRINUSE",
    "EBUSY",
    "ECONNRESET",
    "EEXIST",
    "EINVAL",
    "EISDIR",
    "EMFILE",
    "ENOENT",
    "ENOSPC",
    "EPERM",
    "ETIMEDOUT",
    "ERR_INVALID_ARG_TYPE",
    "ERR_MODULE_NOT_FOUND",
)
_REGISTRATION_ADMISSION_DIAG_LINE_BYTES_LIMIT = 1024
_REGISTRATION_ADMISSION_DIAG_RECORD_LIMIT = 4
_REGISTRATION_ADMISSION_DIAG_MAX_MS = 360_000
_REGISTRATION_ADMISSION_DIAG_MAX_REQUESTS = 256
_REGISTRATION_ADMISSION_DIAG_MAX_COST = 5


def _validated_registration_admission_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _REGISTRATION_ADMISSION_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    if (
        not isinstance(record["project"], str)
        or record["project"] not in _PLAYWRIGHT_FAILURE_PROJECTS
    ):
        return None
    if record["stage"] not in _REGISTRATION_ADMISSION_DIAG_STAGES:
        return None
    if record["errorClass"] not in _REGISTRATION_ADMISSION_DIAG_ERROR_CLASSES:
        return None
    if record["nodeCode"] is not None and record["nodeCode"] not in (
        *_REGISTRATION_ADMISSION_DIAG_NODE_CODES,
        "other",
    ):
        return None
    cost = record["cost"]
    if cost is not None and (
        type(cost) is not int or not 1 <= cost <= _REGISTRATION_ADMISSION_DIAG_MAX_COST
    ):
        return None
    for key in ("timeoutMs", "remainingMs"):
        number = record[key]
        if number is not None and (
            type(number) is not int
            or not 1 <= number <= _REGISTRATION_ADMISSION_DIAG_MAX_MS
        ):
            return None
    for key in ("requestCount", "activeRequestCount"):
        number = record[key]
        if (
            type(number) is not int
            or not 0 <= number <= _REGISTRATION_ADMISSION_DIAG_MAX_REQUESTS
        ):
            return None
    if record["activeRequestCount"] > record["requestCount"]:
        return None
    for key in (
        "deadlineAvailable",
        "ownerPresent",
        "ledgerPresent",
        "requestObserved",
        "responseObserved",
        "actionFailed",
    ):
        if type(record[key]) is not bool:
            return None
    if record["requestObserved"] != (record["requestCount"] > 0):
        return None
    if not record["deadlineAvailable"] and record["remainingMs"] is not None:
        return None
    if record["responseObserved"] and not record["requestObserved"]:
        return None
    status = record["status"]
    if status is not None and (type(status) is not int or not 100 <= status <= 599):
        return None
    if not record["responseObserved"] and status is not None:
        return None
    return dict(record)


_FORGOT_DIAGNOSTIC_PREFIX = "UE_LIVE_PASSWORD_FORGOT_V1 "
_PASSWORD_FORGOT_KEYS = frozenset(
    {
        "scope",
        "schema",
        "project",
        "attempt",
        "phase",
        "elapsed",
        "auth",
        "csrf",
        "forgot",
        "snapshot",
    }
)
_PASSWORD_FORGOT_STAT_KEYS = frozenset(
    {"requests", "responses", "completed", "failed", "status", "responsePhase"}
)
_PASSWORD_FORGOT_SNAPSHOT_KEYS = frozenset(
    {
        "forgotRoute",
        "hydrated",
        "formPresent",
        "formInvalid",
        "formAlert",
        "submitPresent",
        "submitDisabled",
        "submitBusy",
        "successMarkerVisible",
    }
)
_PASSWORD_FORGOT_COUNTS = frozenset({"0", "1", "many"})
_PASSWORD_FORGOT_STATUSES = frozenset(
    {"none", "2xx", "401", "403", "429", "4xx", "5xx", "other", "mixed", "unavailable"}
)


def _closed_diagnostic_label(value: object, labels: Iterable[str]) -> str | None:
    """Reconstruct a public label instead of retaining the observed string."""
    if type(value) is not str:
        return None
    for label in labels:
        if value == label:
            return label
    return None


def _validated_password_forgot_stat(value: object) -> dict[str, object] | None:
    if type(value) is not dict or set(value) != _PASSWORD_FORGOT_STAT_KEYS:
        return None
    for key in ("requests", "responses", "completed", "failed"):
        if type(value[key]) is not str or value[key] not in _PASSWORD_FORGOT_COUNTS:
            return None
    if (
        type(value["status"]) is not str
        or value["status"] not in _PASSWORD_FORGOT_STATUSES
        or type(value["responsePhase"]) is not str
        or value["responsePhase"]
        not in {
            "none",
            "before-click",
            "after-click",
            "mixed",
        }
    ):
        return None
    if value["requests"] == "0" and any(
        value[key] != "0" for key in ("responses", "completed", "failed")
    ):
        return None
    if (
        (value["responses"] == "0") != (value["status"] == "none")
        or (value["responses"] == "0") != (value["responsePhase"] == "none")
        or (value["completed"] != "0" and value["responses"] == "0")
    ):
        return None
    if value["requests"] == "1" and (
        any(value[key] == "many" for key in ("responses", "completed", "failed"))
        or (value["completed"] == "1" and value["failed"] == "1")
    ):
        return None
    return {
        "requests": _closed_diagnostic_label(
            value["requests"], _PASSWORD_FORGOT_COUNTS
        ),
        "responses": _closed_diagnostic_label(
            value["responses"], _PASSWORD_FORGOT_COUNTS
        ),
        "completed": _closed_diagnostic_label(
            value["completed"], _PASSWORD_FORGOT_COUNTS
        ),
        "failed": _closed_diagnostic_label(value["failed"], _PASSWORD_FORGOT_COUNTS),
        "status": _closed_diagnostic_label(value["status"], _PASSWORD_FORGOT_STATUSES),
        "responsePhase": _closed_diagnostic_label(
            value["responsePhase"], ("none", "before-click", "after-click", "mixed")
        ),
    }


def _validated_password_forgot_record(value: object) -> dict[str, object] | None:
    if type(value) is not dict or set(value) != _PASSWORD_FORGOT_KEYS:
        return None
    if (
        type(value["scope"]) is not str
        or value["scope"] not in {"main-frame-navigation-window", "unconfirmed"}
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or type(value["project"]) is not str
        or value["project"] not in {"desktop", "mobile"}
        or type(value["attempt"]) is not int
        or value["attempt"] not in {0, 1}
        or type(value["phase"]) is not str
        or value["phase"] not in {"navigate", "fill", "click", "success"}
        or type(value["elapsed"]) is not str
        or value["elapsed"] not in {"lt1s", "1to5s", "5to15s", "ge15s", "unavailable"}
    ):
        return None
    result: dict[str, object] = {
        "scope": _closed_diagnostic_label(
            value["scope"], ("main-frame-navigation-window", "unconfirmed")
        ),
        "schema": 1,
        "project": _closed_diagnostic_label(value["project"], ("desktop", "mobile")),
        "attempt": 0 if value["attempt"] == 0 else 1,
        "phase": _closed_diagnostic_label(
            value["phase"], ("navigate", "fill", "click", "success")
        ),
        "elapsed": _closed_diagnostic_label(
            value["elapsed"], ("lt1s", "1to5s", "5to15s", "ge15s", "unavailable")
        ),
    }
    for route in ("auth", "csrf", "forgot"):
        stat = _validated_password_forgot_stat(value[route])
        if stat is None:
            return None
        if value["scope"] == "unconfirmed" and stat["requests"] != "0":
            return None
        result[route] = stat
    snapshot = value["snapshot"]
    if snapshot is not None:
        if (
            type(snapshot) is not dict
            or set(snapshot) != _PASSWORD_FORGOT_SNAPSHOT_KEYS
            or any(type(flag) is not bool for flag in snapshot.values())
        ):
            return None
        if (
            not snapshot["formPresent"]
            and any(
                snapshot[key]
                for key in (
                    "formInvalid",
                    "formAlert",
                    "submitPresent",
                    "submitDisabled",
                    "submitBusy",
                )
            )
        ) or (
            not snapshot["submitPresent"]
            and (snapshot["submitDisabled"] or snapshot["submitBusy"])
        ):
            return None
        snapshot = {
            key: snapshot[key] is True
            for key in (
                "forgotRoute",
                "hydrated",
                "formPresent",
                "formInvalid",
                "formAlert",
                "submitPresent",
                "submitDisabled",
                "submitBusy",
                "successMarkerVisible",
            )
        }
    result["snapshot"] = snapshot
    return result


def _render_forgot_observation(value: object) -> str | None:
    """Enforce a finite public output domain at the final logging boundary."""
    if type(value) is not dict or _validated_password_forgot_record(value) is None:
        return None
    # Validation is a guard only. Rebuild independently from literal public
    # domains; never serialize its result or caller-owned strings/containers.
    observations: dict[str, object] = {}
    for route in ("auth", "csrf", "forgot"):
        stat = value[route]
        observations[route] = {
            "requests": _closed_diagnostic_label(stat["requests"], ("0", "1", "many")),
            "responses": _closed_diagnostic_label(
                stat["responses"], ("0", "1", "many")
            ),
            "completed": _closed_diagnostic_label(
                stat["completed"], ("0", "1", "many")
            ),
            "failed": _closed_diagnostic_label(stat["failed"], ("0", "1", "many")),
            "status": _closed_diagnostic_label(
                stat["status"],
                (
                    "none",
                    "2xx",
                    "401",
                    "403",
                    "429",
                    "4xx",
                    "5xx",
                    "other",
                    "mixed",
                    "unavailable",
                ),
            ),
            "responsePhase": _closed_diagnostic_label(
                stat["responsePhase"], ("none", "before-click", "after-click", "mixed")
            ),
        }
    snapshot = value["snapshot"]
    flags = (
        None
        if snapshot is None
        else {
            key: snapshot[key] is True
            for key in (
                "forgotRoute",
                "hydrated",
                "formPresent",
                "formInvalid",
                "formAlert",
                "submitPresent",
                "submitDisabled",
                "submitBusy",
                "successMarkerVisible",
            )
        }
    )
    output = {
        "scope": _closed_diagnostic_label(
            value["scope"], ("main-frame-navigation-window", "unconfirmed")
        ),
        "schema": 1,
        "project": _closed_diagnostic_label(value["project"], ("desktop", "mobile")),
        "attempt": 0 if value["attempt"] == 0 else 1,
        "phase": _closed_diagnostic_label(
            value["phase"], ("navigate", "fill", "click", "success")
        ),
        "elapsed": _closed_diagnostic_label(
            value["elapsed"], ("lt1s", "1to5s", "5to15s", "ge15s", "unavailable")
        ),
        **observations,
        "snapshot": flags,
    }
    return json.dumps(output, separators=(",", ":"))


def _live_playwright_password_forgot_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[tuple[object, object]] = set()
    for raw_line in output.split("\n")[:-1]:
        try:
            # Include CR when present and the consumed LF in the frame budget.
            if len(raw_line.encode("utf-8")) + 1 > 2_048:
                continue
        except UnicodeEncodeError:
            continue
        line = raw_line.removesuffix("\r")
        if not line.isprintable() or not line.startswith(_FORGOT_DIAGNOSTIC_PREFIX):
            continue
        try:
            value = json.loads(
                line[len(_FORGOT_DIAGNOSTIC_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError, RecursionError):
            continue
        record = _validated_password_forgot_record(value)
        if record is None:
            continue
        identity = (record["project"], record["attempt"])
        if identity in seen:
            continue
        seen.add(identity)
        records.append(record)
        if len(records) == 4:
            break
    return records


_PLAYWRIGHT_RESET_URL_LINE = re.compile(
    r"UE_LIVE_RESET_URL_V1 project=(desktop|mobile) phase=(history|reopen) "
    r"reset_route=(true|false) token_query_absent=(true|false) "
    r"token_fragment_absent=(true|false) token_url_absent=(true|false)"
)


def _live_playwright_reset_url_observations(
    output: str,
) -> list[tuple[str, str, bool, bool, bool, bool]]:
    """Retain only the first completed boolean observation per project/phase."""
    records: list[tuple[str, str, bool, bool, bool, bool]] = []
    seen: set[tuple[str, str]] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_RESET_URL_LINE.fullmatch(line)
        if match is None:
            continue
        key = (match.group(1), match.group(2))
        if key in seen:
            continue
        seen.add(key)
        records.append(
            (
                *key,
                match.group(3) == "true",
                match.group(4) == "true",
                match.group(5) == "true",
                match.group(6) == "true",
            )
        )
        if len(records) == 4:
            break
    return records


_PLAYWRIGHT_RESET_REGISTRATION_LINE = re.compile(
    r"UE_LIVE_RESET_REGISTRATION_V1 project=(desktop|mobile) "
    r"step=(arm-response|click|await-response)"
)


def _live_playwright_reset_registration_steps(output: str) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 128 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_RESET_REGISTRATION_LINE.fullmatch(line)
        if match is None:
            continue
        record = (match.group(1), match.group(2))
        if record not in records:
            records.append(record)
        if len(records) == 6:
            break
    return records


_RESET_REGISTRATION_V2_ERROR_KEYS = (
    "nameError",
    "emailError",
    "inviteError",
    "passwordError",
    "confirmError",
    "rootError",
)
_RESET_REGISTRATION_V2_SNAPSHOT_KEYS = (
    "hydrated",
    "formPresent",
    "formInvalid",
    "formError",
    *_RESET_REGISTRATION_V2_ERROR_KEYS,
    "submitPresent",
    "submitDisabled",
    "submitBusy",
)
_RESET_REGISTRATION_V2_KEYS = (
    "project",
    "step",
    "errorCategory",
    "snapshot",
    *_RESET_REGISTRATION_V2_SNAPSHOT_KEYS,
    "csrfRequested",
    "csrfResponse",
    "csrfFailed",
)


def _validated_reset_registration_v2(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _RESET_REGISTRATION_V2_KEYS)
    if record is None:
        return None
    allowed_values = {
        "project": ("desktop", "mobile"),
        "step": ("arm-response", "click", "await-response"),
        "errorCategory": (
            "timeout",
            "abort",
            "type-error",
            "target-closed",
            "error",
            "other",
        ),
        "snapshot": ("available", "unavailable"),
        "csrfResponse": (
            "not-observed",
            "success",
            "http-error",
            "mixed",
            "unavailable",
        ),
    }
    if any(record[key] not in values for key, values in allowed_values.items()):
        return None
    boolean_keys = (
        *_RESET_REGISTRATION_V2_SNAPSHOT_KEYS,
        "csrfRequested",
        "csrfFailed",
    )
    if any(type(record[key]) is not bool for key in boolean_keys):
        return None
    if record["snapshot"] == "unavailable" and any(
        record[key] for key in _RESET_REGISTRATION_V2_SNAPSHOT_KEYS
    ):
        return None
    if not record["formPresent"] and any(
        record[key] for key in _RESET_REGISTRATION_V2_SNAPSHOT_KEYS[2:]
    ):
        return None
    if not record["formError"] and any(
        record[key] for key in _RESET_REGISTRATION_V2_ERROR_KEYS
    ):
        return None
    if not record["submitPresent"] and (
        record["submitDisabled"] or record["submitBusy"]
    ):
        return None
    if not record["csrfRequested"] and (
        record["csrfResponse"] != "not-observed" or record["csrfFailed"]
    ):
        return None
    return dict(record)


def _live_playwright_reset_registration_v2(output: str) -> list[dict[str, object]]:
    prefix = "UE_LIVE_RESET_REGISTRATION_V2 "
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 1_024 or not line.isprintable() or not line.startswith(prefix):
            continue
        try:
            value = json.loads(
                line[len(prefix) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_reset_registration_v2(value)
        if record is None:
            continue
        identity = json.dumps(record, sort_keys=True, separators=(",", ":"))
        if identity in seen:
            continue
        seen.add(identity)
        records.append(record)
        if len(records) == 6:
            break
    return records


_RESET_REGISTRATION_V3_KEYS = (
    "project",
    "step",
    "beforeName",
    "afterName",
    "beforeSubmit",
)
_RESET_REGISTRATION_V3_SNAPSHOT_KEYS = ("hydrated", "nameState", "nameError")


def _validated_reset_registration_v3(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _RESET_REGISTRATION_V3_KEYS)
    if record is None:
        return None
    if not isinstance(record["project"], str) or record["project"] not in (
        "desktop",
        "mobile",
    ):
        return None
    if not isinstance(record["step"], str) or record["step"] not in (
        "arm-response",
        "click",
        "await-response",
    ):
        return None
    for field in ("beforeName", "afterName", "beforeSubmit"):
        if record[field] is None:
            continue
        snapshot_keys = (
            (*_RESET_REGISTRATION_V3_SNAPSHOT_KEYS, "trigger")
            if field == "beforeSubmit"
            else _RESET_REGISTRATION_V3_SNAPSHOT_KEYS
        )
        snapshot = _auth_diag_object(record[field], snapshot_keys)
        if snapshot is None or any(
            type(snapshot[key]) is not bool for key in ("hydrated", "nameError")
        ):
            return None
        state = snapshot["nameState"]
        if not isinstance(state, str) or state not in (
            "missing",
            "empty",
            "short",
            "at-least-two",
        ):
            return None
        if field == "beforeSubmit" and (
            not isinstance(snapshot["trigger"], str)
            or snapshot["trigger"] not in ("click", "invalid", "submit")
        ):
            return None
    return dict(record)


def _live_playwright_reset_registration_v3(output: str) -> list[dict[str, object]]:
    prefix = "UE_LIVE_RESET_REGISTRATION_V3 "
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > 1_024
            or not line.isprintable()
            or not line.startswith(prefix)
        ):
            continue
        try:
            value = json.loads(
                line[len(prefix) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_reset_registration_v3(value)
        if record is None:
            continue
        identity = json.dumps(record, sort_keys=True, separators=(",", ":"))
        if identity in seen:
            continue
        seen.add(identity)
        records.append(record)
        if len(records) == 6:
            break
    return records


def _live_playwright_registration_admission_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _REGISTRATION_ADMISSION_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_REGISTRATION_ADMISSION_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_REGISTRATION_ADMISSION_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_registration_admission_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _REGISTRATION_ADMISSION_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_PWA_BUNDLE_ROUTE_DIAG_PREFIX = "PWA_BUNDLE_ROUTE_DIAG "
_PWA_BUNDLE_ROUTE_DIAG_KEYS = (
    "schema",
    "project",
    "routeEntries",
    "originMatches",
    "bundlePathMatches",
    "serviceWorkerRequestSeen",
)
_PWA_BUNDLE_ROUTE_DIAG_LINE_BYTES_LIMIT = 512
_PWA_BUNDLE_ROUTE_DIAG_RECORD_LIMIT = 4
_PWA_BUNDLE_ROUTE_DIAG_MAX_COUNT = 64


def _validated_pwa_bundle_route_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _PWA_BUNDLE_ROUTE_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    project = record["project"]
    route_entries = record["routeEntries"]
    origin_matches = record["originMatches"]
    bundle_path_matches = record["bundlePathMatches"]
    service_worker_seen = record["serviceWorkerRequestSeen"]
    if not isinstance(project, str) or project not in _PLAYWRIGHT_FAILURE_PROJECTS:
        return None
    counts = (route_entries, origin_matches, bundle_path_matches)
    if any(
        type(count) is not int or not 0 <= count <= _PWA_BUNDLE_ROUTE_DIAG_MAX_COUNT
        for count in counts
    ):
        return None
    if origin_matches > route_entries or bundle_path_matches > origin_matches:
        return None
    if type(service_worker_seen) is not bool:
        return None
    if service_worker_seen and route_entries == 0:
        return None
    return {
        "schema": 1,
        "project": project,
        "routeEntries": route_entries,
        "originMatches": origin_matches,
        "bundlePathMatches": bundle_path_matches,
        "serviceWorkerRequestSeen": service_worker_seen,
    }


def _live_playwright_pwa_bundle_route_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    """Retain only closed, bounded PWA route observations from complete stdout lines."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _PWA_BUNDLE_ROUTE_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_PWA_BUNDLE_ROUTE_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_PWA_BUNDLE_ROUTE_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_pwa_bundle_route_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _PWA_BUNDLE_ROUTE_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_PWA_UPDATE_LIFECYCLE_DIAG_PREFIX = "PWA_UPDATE_LIFECYCLE_DIAG "
_PWA_UPDATE_LIFECYCLE_DIAG_KEYS = (
    "schema",
    "project",
    "diagnosticStatus",
    "controllerChangeCount",
    "controllerPresent",
    "controllerState",
    "installingState",
    "waitingState",
    "activeState",
    "controllerIsActive",
    "workerTransformApplied",
    "bundleUpdateResponseSeen",
    "routeEntries",
    "originMatches",
    "bundlePathMatches",
    "serviceWorkerRequestSeen",
)
_PWA_UPDATE_LIFECYCLE_STATES = (
    "none",
    "parsed",
    "installing",
    "installed",
    "activating",
    "activated",
    "redundant",
)
_PWA_UPDATE_LIFECYCLE_DIAG_LINE_BYTES_LIMIT = 1024
_PWA_UPDATE_LIFECYCLE_DIAG_RECORD_LIMIT = 4
_PWA_UPDATE_LIFECYCLE_DIAG_MAX_COUNT = 64


def _validated_pwa_update_lifecycle_diag(value: object) -> dict[str, object] | None:
    record = _auth_diag_object(value, _PWA_UPDATE_LIFECYCLE_DIAG_KEYS)
    if record is None or type(record["schema"]) is not int or record["schema"] != 1:
        return None
    if (
        not isinstance(record["project"], str)
        or record["project"] not in _PLAYWRIGHT_FAILURE_PROJECTS
    ):
        return None
    if record["diagnosticStatus"] not in ("available", "unavailable"):
        return None
    for key in (
        "controllerState",
        "installingState",
        "waitingState",
        "activeState",
    ):
        if record[key] not in _PWA_UPDATE_LIFECYCLE_STATES:
            return None
    for key in (
        "controllerChangeCount",
        "routeEntries",
        "originMatches",
        "bundlePathMatches",
    ):
        count = record[key]
        if count is not None and (
            type(count) is not int
            or not 0 <= count <= _PWA_UPDATE_LIFECYCLE_DIAG_MAX_COUNT
        ):
            return None
    for key in ("controllerPresent", "controllerIsActive"):
        if record[key] is not None and type(record[key]) is not bool:
            return None
    for key in (
        "workerTransformApplied",
        "bundleUpdateResponseSeen",
        "serviceWorkerRequestSeen",
    ):
        if type(record[key]) is not bool:
            return None
    route_entries = record["routeEntries"]
    origin_matches = record["originMatches"]
    bundle_path_matches = record["bundlePathMatches"]
    if (
        route_entries is not None
        and origin_matches is not None
        and bundle_path_matches is not None
        and not bundle_path_matches <= origin_matches <= route_entries
    ):
        return None
    if record["serviceWorkerRequestSeen"] and (
        route_entries is None or route_entries < 1
    ):
        return None
    if record["diagnosticStatus"] == "unavailable" and (
        record["controllerChangeCount"] is not None
        or record["controllerPresent"] is not None
        or record["controllerIsActive"] is not None
        or any(
            record[key] != "none"
            for key in (
                "controllerState",
                "installingState",
                "waitingState",
                "activeState",
            )
        )
    ):
        return None
    return dict(record)


def _live_playwright_pwa_update_lifecycle_diagnostics(
    output: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _PWA_UPDATE_LIFECYCLE_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_PWA_UPDATE_LIFECYCLE_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_PWA_UPDATE_LIFECYCLE_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_pwa_update_lifecycle_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _PWA_UPDATE_LIFECYCLE_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


def _live_playwright_auth_http_diagnostics(output: str) -> list[dict[str, object]]:
    """Retain only complete bounded Auth HTTP status mismatches from stdout."""
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if (
            len(line.encode("utf-8")) > _AUTH_DIAG_LINE_BYTES_LIMIT
            or not line.isprintable()
            or not line.startswith(_AUTH_HTTP_DIAG_PREFIX)
        ):
            continue
        try:
            raw = json.loads(
                line[len(_AUTH_HTTP_DIAG_PREFIX) :],
                object_pairs_hook=_auth_diag_json_object,
                parse_constant=_reject_auth_diag_json_constant,
            )
        except (json.JSONDecodeError, ValueError):
            continue
        record = _validated_auth_http_diag(raw)
        if record is None:
            continue
        identity = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if identity in seen:
            continue
        if len(records) >= _AUTH_DIAG_RECORD_LIMIT:
            break
        seen.add(identity)
        records.append(record)
    return records


_PLAYWRIGHT_LOGIN_FAILURE_LINE = re.compile(
    r"UE_LIVE_LOGIN_FAILURE_V1 project=(?P<project>desktop|mobile) "
    r"stage=(?P<stage>submit|navigation) "
    r"requests=(?P<requests>0|1|many) responses=(?P<responses>0|1|many) "
    r"status=(?P<status>none|[1-5][0-9]{2}) "
    r"route=(?P<route>login|dashboard|register|other|unavailable)"
)
_PLAYWRIGHT_LOGIN_FAILURE_LIMIT = 16
_PlaywrightLoginFailure = tuple[str, str, str, str, str, str]


def _live_playwright_login_failures(output: str) -> list[_PlaywrightLoginFailure]:
    """Accept only complete, closed login observations without raw URLs or errors."""
    records: list[_PlaywrightLoginFailure] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 192 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_LOGIN_FAILURE_LINE.fullmatch(line)
        if match is None:
            continue
        record: _PlaywrightLoginFailure = (
            match["project"],
            match["stage"],
            match["requests"],
            match["responses"],
            match["status"],
            match["route"],
        )
        if record in records:
            continue
        records.append(record)
        if len(records) >= _PLAYWRIGHT_LOGIN_FAILURE_LIMIT:
            break
    return records


_PLAYWRIGHT_HTTP_STATUS_LINE = re.compile(
    r"UE_LIVE_HTTP_STATUS_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>student-users-denied|teacher-users-denied|"
    r"student-feature-flags-denied|teacher-feature-flags-denied|"
    r"admin-users|admin-feature-flags|admin-feature-flags-ui|password-reset-replay|"
    r"auth-login|auth-session-cap|auth-logout|auth-session-preflight|"
    r"messenger-message-send|chat-attachment-create|email-otp-register|"
    r"email-otp-verification-start|email-otp-verification-wrong-code|"
    r"email-otp-verification-resend|email-otp-verification-stale-code|"
    r"email-otp-verification-accept|email-mfa-register|email-mfa-initial-login|"
    r"email-mfa-sibling-login|email-mfa-verification-start|"
    r"email-mfa-verification-accept|email-mfa-enable-start|email-mfa-enable-accept|"
    r"email-mfa-enabled-login|email-mfa-login-resend-early|email-mfa-login-accept) "
    r"status=(?P<status>[1-5][0-9]{2})"
)
_PLAYWRIGHT_HTTP_STATUS_CHECKS = {
    check: check
    for check in (
        "student-users-denied",
        "teacher-users-denied",
        "student-feature-flags-denied",
        "teacher-feature-flags-denied",
        "admin-users",
        "admin-feature-flags",
        "admin-feature-flags-ui",
        "password-reset-replay",
        "auth-login",
        "auth-session-cap",
        "auth-logout",
        "auth-session-preflight",
        "messenger-message-send",
        "chat-attachment-create",
        "email-otp-register",
        "email-otp-verification-start",
        "email-otp-verification-wrong-code",
        "email-otp-verification-resend",
        "email-otp-verification-stale-code",
        "email-otp-verification-accept",
        "email-mfa-register",
        "email-mfa-initial-login",
        "email-mfa-sibling-login",
        "email-mfa-verification-start",
        "email-mfa-verification-accept",
        "email-mfa-enable-start",
        "email-mfa-enable-accept",
        "email-mfa-enabled-login",
        "email-mfa-login-resend-early",
        "email-mfa-login-accept",
    )
}
# Keep the existing hard output bound as the closed check set grows.
_PLAYWRIGHT_HTTP_STATUS_LIMIT = 104


_PLAYWRIGHT_RETRY_DECISION_LINE = re.compile(
    r"UE_LIVE_RETRY_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>auth-logout|password-reset-replay|"
    r"email-otp-verification-wrong-code|email-otp-verification-stale-code|"
    r"email-mfa-enabled-login) "
    r"retry_after_seconds=(?P<retry_after>invalid|[1-9][0-9]{0,2}) "
    r"decision=(?P<decision>retry|declined-header|declined-deadline|not-retried) "
    r"remaining_ms=(?P<remaining>0|[1-9][0-9]{0,3}|[1-5][0-9]{4}|60000)"
)
_PLAYWRIGHT_RETRY_DECISION_LIMIT = 32
_PlaywrightRetryDecision = tuple[str, str, int | None, str, int]

_PLAYWRIGHT_RATE_LIMIT_LINE = re.compile(
    r"UE_LIVE_RATE_LIMIT_V1 project=(?P<project>desktop|mobile) "
    r"check=auth-logout "
    r"x_ratelimit_limit=(?P<limit>invalid|[1-9][0-9]{0,5}) "
    r"x_ratelimit_remaining=(?P<remaining>invalid|0|[1-9][0-9]{0,5})"
)
_PLAYWRIGHT_RATE_LIMIT_MAX = 100_000
_PLAYWRIGHT_RATE_LIMIT_RECORD_LIMIT = 32
_PlaywrightRateLimit = tuple[str, int | None, int | None]


def _live_playwright_a11y_contrasts(output: str) -> list[_PlaywrightA11yContrast]:
    """Accept bounded contrast values from the fixed stdout protocol only."""
    records: list[_PlaywrightA11yContrast] = []
    route_counts: dict[tuple[str, str], int] = {}
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_A11Y_CONTRAST_LINE.fullmatch(line)
        if match is None:
            continue
        ratio_milli = int(match["ratio"])
        if ratio_milli > 21_000:
            continue
        project = _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]]
        route = match["route"]
        record: _PlaywrightA11yContrast = (
            project,
            route,
            match["foreground"].lower(),
            match["background"].lower(),
            ratio_milli,
        )
        if record in records:
            continue
        route_key = (project, route)
        if route_counts.get(route_key, 0) >= _PLAYWRIGHT_A11Y_CONTRAST_PER_ROUTE_LIMIT:
            continue
        records.append(record)
        route_counts[route_key] = route_counts.get(route_key, 0) + 1
        if len(records) == _PLAYWRIGHT_A11Y_CONTRAST_LIMIT:
            break
    return records


def _live_playwright_a11y_paint_states(output: str) -> list[_PlaywrightA11yPaintState]:
    """Accept only fixed paint, opacity, text-color and animation tags."""
    records: list[_PlaywrightA11yPaintState] = []
    route_counts: dict[tuple[str, str], int] = {}
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 480 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_A11Y_PAINT_LINE.fullmatch(line)
        if match is None:
            continue
        ratio_milli = int(match["ratio"])
        if ratio_milli > 21_000:
            continue
        record: _PlaywrightA11yPaintState = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            match["route"],
            match["axe_foreground"].lower(),
            match["axe_background"].lower(),
            ratio_milli,
            match["css_foreground"].lower(),
            match["text_color"],
            int(match["css_alpha"]),
            int(match["node_opacity"]),
            int(match["ancestor_opacity"]),
            match["opacity_tag"],
            match["page_ready"] == "true",
            int(match["page_opacity"]),
            int(match["layout_opacity"]),
            match["animation"],
            int(match["active_animations"]),
        )
        route_key = (record[0], record[1])
        if record in records or route_counts.get(route_key, 0) >= (
            _PLAYWRIGHT_A11Y_PAINT_PER_ROUTE_LIMIT
        ):
            continue
        records.append(record)
        route_counts[route_key] = route_counts.get(route_key, 0) + 1
        if len(records) == _PLAYWRIGHT_A11Y_PAINT_LIMIT:
            break
    return records


def _live_playwright_a11y_phase_states(output: str) -> list[_PlaywrightA11yPhaseState]:
    """Accept only fixed phase, page/root opacity and animation measurements."""
    records: list[_PlaywrightA11yPhaseState] = []
    phases_by_route: dict[tuple[str, str], set[str]] = {}
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 400 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_A11Y_PHASE_LINE.fullmatch(line)
        if match is None:
            continue
        record: _PlaywrightA11yPhaseState = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            match["route"],
            match["phase"],
            match["page_ready"] == "true",
            int(match["page_opacity"]),
            int(match["root_opacity"]),
            int(match["layout_opacity"]),
            match["animation"],
            int(match["active_animations"]),
        )
        route_key = (record[0], record[1])
        phase_set = phases_by_route.setdefault(route_key, set())
        if record[2] in phase_set:
            continue
        records.append(record)
        phase_set.add(record[2])
    return records


def _live_playwright_footer_geometries(output: str) -> list[_PlaywrightFooterGeometry]:
    """Accept bounded viewport/nav measurements and fixed-block flags only."""
    records: list[_PlaywrightFooterGeometry] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 768 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_FOOTER_GEOMETRY_LINE.fullmatch(line)
        if match is None:
            continue
        number_names = (
            "requested_width",
            "requested_height",
            "inner_width",
            "inner_height",
            "client_width",
            "scroll_width",
            "nav_left",
            "nav_right",
            "nav_top",
            "nav_bottom",
            "nav_width",
            "nav_tx",
            "nav_ty",
            "fixed_cb_depth",
            "cb_left",
            "cb_right",
            "cb_top",
            "cb_bottom",
        )
        values = {name: int(match[name]) for name in number_names}
        if any(abs(value) > 5_000_000 for value in values.values()):
            continue
        if (
            values["requested_width"] <= 0
            or values["requested_height"] <= 0
            or values["inner_width"] <= 0
            or values["inner_height"] <= 0
            or values["client_width"] < 0
            or values["scroll_width"] < 0
            or values["nav_width"] < 0
            or values["fixed_cb_depth"] > 32
        ):
            continue
        fixed_found = match["fixed_cb_found"] == "true"
        depth = values["fixed_cb_depth"]
        cb_rect = tuple(
            values[name] for name in ("cb_left", "cb_right", "cb_top", "cb_bottom")
        )
        if (fixed_found and depth == 0) or (
            not fixed_found and (depth != 0 or any(cb_rect))
        ):
            continue
        record: _PlaywrightFooterGeometry = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            values["requested_width"],
            values["requested_height"],
            values["inner_width"],
            values["inner_height"],
            values["client_width"],
            values["scroll_width"],
            values["nav_left"],
            values["nav_right"],
            values["nav_top"],
            values["nav_bottom"],
            values["nav_width"],
            match["nav_transform_present"] == "true",
            values["nav_tx"],
            values["nav_ty"],
            fixed_found,
            depth,
            values["cb_left"],
            values["cb_right"],
            values["cb_top"],
            values["cb_bottom"],
        )
        if record not in records:
            records.append(record)
            if len(records) == _PLAYWRIGHT_FOOTER_GEOMETRY_LIMIT:
                break
    return records


def _live_playwright_news_viewports(output: str) -> list[_PlaywrightNewsViewport]:
    # Parse only the fixed stdout geometry fields.
    records: list[_PlaywrightNewsViewport] = []
    seen: set[tuple[str, str, int]] = set()
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 256 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_NEWS_VIEWPORT_LINE.fullmatch(line)
        if match is None:
            continue
        viewport_height = int(match["viewport_height"])
        scroll_y = int(match["scroll_y"])
        top = int(match["top"])
        bottom = int(match["bottom"])
        left = int(match["left"])
        right = int(match["right"])
        if (
            viewport_height <= 0
            or bottom < top
            or right < left
            or any(
                abs(value) > 999_999 for value in (scroll_y, top, bottom, left, right)
            )
        ):
            continue
        project = _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]]
        language = match["language"]
        width = int(match["width"])
        key = (project, language, width)
        if key in seen:
            continue
        record: _PlaywrightNewsViewport = (
            project,
            language,
            width,
            viewport_height,
            scroll_y,
            top,
            bottom,
            left,
            right,
        )
        records.append(record)
        seen.add(key)
        if len(records) == _PLAYWRIGHT_NEWS_VIEWPORT_LIMIT:
            break
    return records


def _live_playwright_push_observations(
    output: str,
) -> list[_PlaywrightPushObservation]:
    """Accept only closed, bounded browser-only Push observations from stdout."""
    observations: list[_PlaywrightPushObservation] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 240 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_PUSH_OBSERVATION_LINE.fullmatch(line)
        if match is None:
            continue
        record: _PlaywrightPushObservation = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            match["permission"],
            match["ready"],
            match["state"],
            match["controller"] == "1",
            match["subscription"] == "1",
            int(match["matches"]),
        )
        if record in observations:
            continue
        if len(observations) >= _PLAYWRIGHT_PUSH_OBSERVATION_LIMIT:
            break
        observations.append(record)
    return observations


def _live_playwright_http_statuses(output: str) -> list[tuple[str, str, int]]:
    """Accept only complete stdout protocol records; discard all other content."""
    statuses: list[tuple[str, str, int]] = []
    # LF and CRLF terminate records; bare controls and EOF never do.
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 96 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_HTTP_STATUS_LINE.fullmatch(line)
        if match is None:
            continue
        check = _PLAYWRIGHT_HTTP_STATUS_CHECKS[match["check"]]
        status = int(match["status"])
        # The producer emits this row only after the exact API detail check.
        if check == "auth-session-cap" and status != 403:
            continue
        record = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            check,
            status,
        )
        if record not in statuses:
            statuses.append(record)
            if len(statuses) == _PLAYWRIGHT_HTTP_STATUS_LIMIT:
                break
    return statuses


def _live_playwright_retry_decisions(output: str) -> list[_PlaywrightRetryDecision]:
    """Accept only bounded retry-decision records from the live E2E helper."""
    decisions: list[_PlaywrightRetryDecision] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_RETRY_DECISION_LINE.fullmatch(line)
        if match is None:
            continue

        retry_after_text = match["retry_after"]
        retry_after = None if retry_after_text == "invalid" else int(retry_after_text)
        decision = match["decision"]
        check = match["check"]
        if check == "email-otp-verification-stale-code":
            if decision != "not-retried" or (
                retry_after is not None and retry_after > 600
            ):
                continue
        else:
            if decision == "not-retried" or (
                retry_after is not None and retry_after > 60
            ):
                continue
            if (retry_after is None) != (decision == "declined-header"):
                continue
        remaining_ms = int(match["remaining"])
        if decision == "retry" and remaining_ms == 0:
            continue
        record: _PlaywrightRetryDecision = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            check,
            retry_after,
            decision,
            remaining_ms,
        )
        if record not in decisions:
            decisions.append(record)
            if len(decisions) == _PLAYWRIGHT_RETRY_DECISION_LIMIT:
                break
    return decisions


def _live_playwright_rate_limit_headers(output: str) -> list[_PlaywrightRateLimit]:
    """Accept only bounded logout-header records; never retain raw header text."""
    records: list[_PlaywrightRateLimit] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_RATE_LIMIT_LINE.fullmatch(line)
        if match is None:
            continue

        limit_text = match["limit"]
        remaining_text = match["remaining"]
        limit = None if limit_text == "invalid" else int(limit_text)
        remaining = None if remaining_text == "invalid" else int(remaining_text)
        if (
            (limit is not None and not 1 <= limit <= _PLAYWRIGHT_RATE_LIMIT_MAX)
            or (
                remaining is not None
                and not 0 <= remaining <= _PLAYWRIGHT_RATE_LIMIT_MAX
            )
            or (limit is not None and remaining is not None and remaining > limit)
        ):
            continue

        record: _PlaywrightRateLimit = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            limit,
            remaining,
        )
        if record not in records:
            records.append(record)
            if len(records) == _PLAYWRIGHT_RATE_LIMIT_RECORD_LIMIT:
                break
    return records


_PLAYWRIGHT_PAGE_ERROR_LINE = re.compile(
    r"UE_LIVE_PAGE_ERROR_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>password-reset|admin-notifications|auth-roles|map-gesture|"
    r"schedule-grid-keyboard) "
    r"page=(?P<page>register|login|forgot-password|reset-password|dashboard|"
    r"admin-notifications|admin-users|admin-feature-flags|map|schedule|other) "
    r"type=(?P<type>error|type-error|reference-error|syntax-error|range-error|uri-error|"
    r"eval-error|aggregate-error|abort-error|security-error|invalid-state-error|react-418|other) "
    r"count=(?P<count>[1-9][0-9]{0,2})"
)
# One aggregate per allowed project/check/page/type combination across all checks.
_PLAYWRIGHT_PAGE_ERROR_LIMIT = 534

_PLAYWRIGHT_PAGE_ERROR_DETAIL_LINE = re.compile(
    r"UE_LIVE_PAGE_ERROR_DETAIL_V1 project=(?P<project>desktop|mobile) "
    r"check=(?P<check>map-gesture|schedule-grid-keyboard) "
    r"page=(?P<page>login|map|schedule|other) "
    r"type=(?P<type>error|type-error|reference-error|syntax-error|range-error|uri-error|"
    r"eval-error|aggregate-error|abort-error|security-error|invalid-state-error|react-418|other) "
    r"source=(?P<source>map-worker|map-shared|map-bundle|schedule-bundle|remote-script|unknown) "
    r"line=(?P<line>0|[1-9][0-9]{0,5}) "
    r"column=(?P<column>0|[1-9][0-9]{0,5}) "
    r"count=(?P<count>[1-9][0-9]{0,2})"
)
_PLAYWRIGHT_PAGE_ERROR_DETAIL_LIMIT = 156
_PlaywrightPageErrorDetail = tuple[str, str, str, str, str, int, int, int]


_PLAYWRIGHT_PROFILE_SAVE_LINE = re.compile(
    r"UE_LIVE_PROFILE_SAVE_V1 project=(?P<project>desktop|mobile) "
    r"status=(?P<status>[1-5][0-9]{2}) "
    r"detail=(?P<detail>absent|array|object|string|number|boolean|null|unavailable) "
    r"detail_count=(?P<detail_count>unknown|0|[1-9][0-9]{0,2}) "
    r"detail_msg=(?P<detail_msg>true|false|unknown) "
    r"alert_count=(?P<alert_count>unknown|0|[1-9][0-9]{0,2}) "
    r"save_disabled=(?P<save_disabled>true|false|unknown) "
    r"route=(?P<route>profile|login|register|dashboard|other) "
    r"page_error_count=(?P<page_error_count>unknown|0|[1-9][0-9]{0,2}) "
    r"page_error=(?P<page_error>none|error|type-error|reference-error|syntax-error|range-error|"
    r"uri-error|eval-error|aggregate-error|abort-error|security-error|invalid-state-error|other|unknown)"
)
_PLAYWRIGHT_PROFILE_SAVE_LIMIT = 4
_ProfileSaveDiagnostic = tuple[
    str,
    int,
    str,
    int | None,
    bool | None,
    int | None,
    bool | None,
    str,
    int | None,
    str,
]


def _profile_save_diagnostic_count(match: re.Match[str], name: str) -> int | None:
    value = match[name]
    return None if value == "unknown" else int(value)


def _profile_save_diagnostic_flag(match: re.Match[str], name: str) -> bool | None:
    value = match[name]
    return None if value == "unknown" else value == "true"


def _live_playwright_profile_save_diagnostics(
    output: str,
) -> list[_ProfileSaveDiagnostic]:
    """Accept only the fixed profile-save diagnostic protocol and discard all other text."""
    records: list[_ProfileSaveDiagnostic] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 320 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_PROFILE_SAVE_LINE.fullmatch(line)
        if match is None:
            continue

        record: _ProfileSaveDiagnostic = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            int(match["status"]),
            match["detail"],
            _profile_save_diagnostic_count(match, "detail_count"),
            _profile_save_diagnostic_flag(match, "detail_msg"),
            _profile_save_diagnostic_count(match, "alert_count"),
            _profile_save_diagnostic_flag(match, "save_disabled"),
            match["route"],
            _profile_save_diagnostic_count(match, "page_error_count"),
            match["page_error"],
        )
        if record not in records:
            records.append(record)
            if len(records) == _PLAYWRIGHT_PROFILE_SAVE_LIMIT:
                break
    return records


def _live_playwright_page_errors(output: str) -> list[tuple[str, str, str, str, int]]:
    """Accept fixed current-page/type counts only, without retaining private text."""
    records: list[tuple[str, str, str, str, int]] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 160 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_PAGE_ERROR_LINE.fullmatch(line)
        if match is None:
            continue
        if match["check"] == "admin-notifications":
            if match["page"] not in {
                "login",
                "dashboard",
                "admin-notifications",
                "other",
            }:
                continue
        elif match["check"] == "auth-roles":
            if match["page"] not in {
                "login",
                "dashboard",
                "admin-users",
                "admin-feature-flags",
                "other",
            }:
                continue
        elif match["check"] == "map-gesture":
            if match["page"] not in {"login", "map", "other"}:
                continue
        elif match["check"] == "schedule-grid-keyboard":
            if match["project"] != "desktop" or match["page"] not in {
                "login",
                "schedule",
                "other",
            }:
                continue
        elif (
            match["page"]
            not in {
                "register",
                "login",
                "forgot-password",
                "reset-password",
                "dashboard",
                "other",
            }
            or match["type"] == "react-418"
        ):
            continue
        record = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            match["check"],
            match["page"],
            match["type"],
            int(match["count"]),
        )
        if record not in records:
            records.append(record)
            if len(records) == _PLAYWRIGHT_PAGE_ERROR_LIMIT:
                break
    return records


def _live_playwright_page_error_details(
    output: str,
) -> list[_PlaywrightPageErrorDetail]:
    # Retain only bounded source buckets linked to accepted summaries.
    summaries = set(_live_playwright_page_errors(output))
    records: list[_PlaywrightPageErrorDetail] = []
    for line in output.split("\n")[:-1]:
        line = line.removesuffix("\r")
        if len(line) > 256 or not line.isprintable():
            continue
        match = _PLAYWRIGHT_PAGE_ERROR_DETAIL_LINE.fullmatch(line)
        if match is None:
            continue
        check = match["check"]
        page = match["page"]
        source = match["source"]
        if check == "map-gesture":
            if page not in {"login", "map", "other"} or source not in {
                "map-worker",
                "map-shared",
                "map-bundle",
                "remote-script",
                "unknown",
            }:
                continue
        elif (
            match["project"] != "desktop"
            or page not in {"login", "schedule", "other"}
            or source not in {"schedule-bundle", "remote-script", "unknown"}
        ):
            continue
        line_number = int(match["line"])
        column = int(match["column"])
        if (source == "unknown") != (line_number == 0 and column == 0):
            continue
        if source != "unknown" and (line_number == 0 or column == 0):
            continue
        count = int(match["count"])
        record: _PlaywrightPageErrorDetail = (
            _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]],
            check,
            page,
            match["type"],
            source,
            line_number,
            column,
            count,
        )
        summary = (record[0], check, page, record[3], count)
        if summary not in summaries or record in records:
            continue
        records.append(record)
        if len(records) == _PLAYWRIGHT_PAGE_ERROR_DETAIL_LIMIT:
            break
    return records


def _live_playwright_counts(output: str) -> dict[str, int]:
    """Extract only numeric aggregate counts from exact Playwright summary lines."""
    counts: dict[str, int] = {}
    for line in output.split("\n"):
        match = _PLAYWRIGHT_COUNT_LINE.fullmatch(line.removesuffix("\r"))
        if match is not None:
            kind = match.group("kind").replace(" ", "_")
            counts[kind] = counts.get(kind, 0) + int(match.group("count"))
    return counts


_PlaywrightSkipIdentity = tuple[str, str, int]
_PLAYWRIGHT_EXPECTED_SKIP_IDENTITIES: tuple[_PlaywrightSkipIdentity, ...] = (
    ("desktop", "tests/e2e-live/auth-roles.live.spec.ts", 144),
    ("mobile", "tests/e2e-live/auth-roles.live.spec.ts", 144),
    ("mobile", "tests/e2e-live/navbar-layout-stability.live.spec.ts", 174),
    ("mobile", "tests/e2e-live/schedule-grid-keyboard.live.spec.ts", 5),
    ("mobile", "tests/e2e-live/schedule-200-equivalent-reflow.live.spec.ts", 5),
    ("mobile", "tests/e2e-live/map-gesture-isolation.live.spec.ts", 178),
    ("mobile", "tests/e2e-live/map-gesture-isolation.live.spec.ts", 209),
    ("desktop", "tests/e2e-live/map-gesture-isolation.live.spec.ts", 248),
)
_PLAYWRIGHT_SKIPPED_ROW_PREFIX = re.compile(r"^  - {2,4}[1-9][0-9]{0,2} ")
_PLAYWRIGHT_SKIPPED_ROW_HEADER = re.compile(
    r"^  - {2,4}(?P<index>[1-9][0-9]{0,2}) "
    r"\[(?P<project>desktop|mobile)\] \u203a "
    r"(?P<source>[^ :\t]{1,160}):(?P<line>[1-9][0-9]{0,4}):"
    r"(?P<column>[1-9][0-9]{0,4}) \u203a (?=.)"
)
_PLAYWRIGHT_FULL_COLLECTION_COUNT = 230
_PLAYWRIGHT_SKIP_IDENTITY_LIMIT = 220
_PLAYWRIGHT_SKIP_SCAN_LINE_LIMIT = 8192
_PLAYWRIGHT_SKIP_LINE_LENGTH_LIMIT = 4096


def _live_playwright_skipped_identities(
    output: str, *, cwd: Path
) -> tuple[list[_PlaywrightSkipIdentity], int, bool]:
    """Extract bounded allowlisted skip identities, never test titles or reasons."""
    identities: list[_PlaywrightSkipIdentity] = []
    rejected_rows = 0
    overflow = False
    seen_indexes: set[int] = set()
    source_cache: dict[str, list[str]] = {}
    try:
        frontend_root = cwd.resolve(strict=True)
    except (OSError, RuntimeError):
        return identities, 0, True

    position = 0
    scanned_lines = 0
    while True:
        line_end = output.find("\n", position)
        if line_end < 0:
            break  # Only complete reporter rows are accepted.
        if scanned_lines >= _PLAYWRIGHT_SKIP_SCAN_LINE_LIMIT:
            overflow = True
            break
        line = output[position:line_end]
        position = line_end + 1
        scanned_lines += 1
        if line.endswith("\r"):
            line = line[:-1]
        if _PLAYWRIGHT_SKIPPED_ROW_PREFIX.match(line) is None:
            continue
        if len(line) > _PLAYWRIGHT_SKIP_LINE_LENGTH_LIMIT or not line.isprintable():
            rejected_rows += 1
            continue
        match = _PLAYWRIGHT_SKIPPED_ROW_HEADER.match(line)
        if match is None:
            rejected_rows += 1
            continue
        index = int(match["index"])
        source = _PLAYWRIGHT_FAILURE_SOURCES.get(match["source"])
        project = _PLAYWRIGHT_FAILURE_PROJECTS.get(match["project"])
        line_number = int(match["line"])
        column = int(match["column"])
        if (
            index > _PLAYWRIGHT_SKIP_IDENTITY_LIMIT
            or index in seen_indexes
            or source is None
            or project is None
        ):
            rejected_rows += 1
            continue
        seen_indexes.add(index)
        if source not in source_cache:
            try:
                source_path = frontend_root / source
                if source_path.is_symlink():
                    raise OSError("skip source is a symlink")
                resolved_source = source_path.resolve(strict=True)
                if (
                    not resolved_source.is_relative_to(frontend_root)
                    or not resolved_source.is_file()
                ):
                    raise OSError("skip source is outside the frontend root")
                source_cache[source] = resolved_source.read_text(
                    encoding="utf-8"
                ).splitlines()
            except (OSError, RuntimeError, UnicodeError):
                rejected_rows += 1
                continue
        source_lines = source_cache[source]
        if line_number > len(source_lines):
            rejected_rows += 1
            continue
        declaration = source_lines[line_number - 1]
        indentation = len(declaration) - len(declaration.lstrip())
        if not declaration.lstrip().startswith("test(") or column != indentation + 1:
            rejected_rows += 1
            continue
        identities.append((project, source, line_number))
    return identities, rejected_rows, overflow


def _live_playwright_failure_locations(
    output: str, *, cwd: Path
) -> list[tuple[str, str, int, str]]:
    """Return public declarations/frames, never titles, function names or errors."""
    locations: list[tuple[str, str, int, str]] = []
    source_lines: dict[str, list[str]] = {}
    frame_sources = {
        **_PLAYWRIGHT_FAILURE_FRAME_SOURCES,
        **{
            str(cwd.absolute() / source): source
            for source in _PLAYWRIGHT_FAILURE_FRAME_SOURCES.values()
        },
    }
    project = ""
    # Split only actual reporter newlines, not control characters in a title.
    for reporter_line in output.split("\n"):
        # A new top-level reporter line ends the previous failure, even if its
        # project, path or location cannot be validated. Blank lines are normal
        # between a failure header, error message and its indented stack.
        if reporter_line and not reporter_line.startswith("    "):
            project = ""
        if len(reporter_line) > 4096 or (
            reporter_line and not reporter_line.isprintable()
        ):
            project = ""
            continue
        match = _PLAYWRIGHT_FAILURE_HEADER.match(reporter_line)
        kind = "declaration"
        if match is not None:
            source = _PLAYWRIGHT_FAILURE_SOURCES.get(match["source"])
        elif project:
            frame = _PLAYWRIGHT_FAILURE_FRAME.fullmatch(reporter_line)
            if frame is None:
                continue
            match = _PLAYWRIGHT_FRAME_LOCATION.fullmatch(
                frame["named"] or frame["anonymous"]
            )
            if match is None:
                continue
            source = frame_sources.get(match["source"])
            kind = "frame"
        else:
            continue
        if source is None:
            continue
        if source not in source_lines:
            try:
                source_lines[source] = (
                    (cwd / source).read_text(encoding="utf-8").splitlines()
                )
            except (OSError, UnicodeError):
                # Diagnostics must not expose paths/errors or replace the exit status.
                source_lines[source] = []
        lines = source_lines[source]
        line_number = int(match["line"])
        column = int(match["column"])
        if line_number > len(lines) or column > len(lines[line_number - 1]) + 1:
            continue
        if kind == "declaration":
            project = _PLAYWRIGHT_FAILURE_PROJECTS[match["project"]]
        location = (project, source, line_number, kind)
        if location not in locations:
            locations.append(location)
    return locations


_PLAYWRIGHT_FAILURE_DIAGNOSTIC_LIMIT = 256
_PLAYWRIGHT_FAILURE_EXPECT_LINE = re.compile(r"^ {4}Error: expect\(")
_PLAYWRIGHT_FAILURE_MATCHER_HEADER = re.compile(
    r"^ {4}Error: expect\((?:locator|page|received)\)\."
    r"(?P<negated>not\.)?(?P<matcher>toBe|toEqual|toStrictEqual|toContain|toMatch|"
    r"toBeVisible|toBeHidden|toBeEnabled|toBeDisabled|toBeChecked|"
    r"toBeFocused|toBeEditable|toBeEmpty|toBeAttached|toBeInViewport|toHaveText|"
    r"toContainText|toHaveValue|toHaveAttribute|toHaveClass|toHaveCount|toHaveCSS|"
    r"toHaveJSProperty|toHaveTitle|toHaveURL|toHaveId|toHaveRole|"
    r"toHaveAccessibleName|toHaveAccessibleDescription|toMatchAriaSnapshot|toPass)\s*\("
)
_PLAYWRIGHT_FAILURE_TIMEOUT_LINE = re.compile(
    r"^ {4}(?:"
    r"Error: (?:(?:locator|page)\.[A-Za-z]+: )?"
    r"Timeout [0-9]{1,6}(?:\.[0-9]{1,3})?(?:ms|s) exceeded\."
    r'|Error: page\.waitForResponse: Timeout [0-9]{1,6}ms exceeded while waiting for event "response"'
    r"|Test timeout of [0-9]{1,6}ms exceeded\."
    r"|Test timeout of [0-9]{1,6}ms exceeded while setting up "
    r'"[^"\r\n]{0,256}"\.'
    r'|Tearing down "[^"\r\n]{0,256}" exceeded the test timeout of '
    r"[0-9]{1,6}ms\."
    r'|Test timeout of [0-9]{1,6}ms exceeded while running "(?:beforeEach|afterEach)" hook\.'
    r'|"(?:beforeAll|afterAll)" hook timeout of [0-9]{1,6}ms exceeded\.'
    r"|Worker teardown timeout of [0-9]{1,6}ms exceeded"
    r'(?: while (?:setting up|tearing down) "[^"\r\n]{0,256}")?\.'
    r'|"(?:skip|slow|fixme|fail)" modifier timeout of [0-9]{1,6}ms exceeded\.'
    r'|Fixture "[^"\r\n]{0,256}" timeout of [0-9]{1,6}ms exceeded during (?:setup|teardown)\.'
    r")$"
)
_PLAYWRIGHT_FAILURE_NAVIGATION_LINE = re.compile(
    r"^ {4}Error: page\.(?:goto|waitForURL)\b"
)
_PLAYWRIGHT_FAILURE_LOCATOR_LINE = re.compile(r"^ {4}Error: locator\.[A-Za-z]+\b")
_PLAYWRIGHT_FAILURE_RUNTIME_LINE = re.compile(
    r"^ {4}(?:Error: )?(?:TypeError|ReferenceError|SyntaxError|RangeError|EvalError|"
    r"URIError|AggregateError|AbortError|SecurityError|InvalidStateError):"
)
_PLAYWRIGHT_FAILURE_LOCATOR_CALL = re.compile(
    r"^ {6}- waiting for (?:(?:page|locator)\.)?"
    r"(?P<method>getByRole|getByLabel|getByPlaceholder|getByText|getByTestId|"
    r"getByAltText|getByTitle|locator)\s*\("
)
_PLAYWRIGHT_FAILURE_CALL_LOG_START = re.compile(r"^ {4}Call log:$")
_PLAYWRIGHT_FAILURE_LOCATOR_CATEGORIES = {
    "getByRole": "role",
    "getByLabel": "label",
    "getByPlaceholder": "placeholder",
    "getByText": "text",
    "getByTestId": "test_id",
    "getByAltText": "alt_text",
    "getByTitle": "title",
    "locator": "locator",
}


def _live_playwright_failure_diagnostics(
    output: str, *, cwd: Path
) -> list[tuple[str, str, int, str, str, str]]:
    """Classify validated failure headers using fixed public enums only."""
    diagnostics: list[tuple[str, str, int, str, str, str]] = []
    source_lines: dict[str, list[str]] = {}
    current: dict[str, str | int] | None = None

    def finish() -> None:
        nonlocal current
        if current is None or len(diagnostics) >= _PLAYWRIGHT_FAILURE_DIAGNOSTIC_LIMIT:
            current = None
            return
        diagnostics.append(
            (
                str(current["project"]),
                str(current["source"]),
                int(current["line"]),
                str(current["category"]),
                str(current["matcher"]),
                str(current["locator"]),
            )
        )
        current = None

    for reporter_line in output.split("\n"):
        if reporter_line and not reporter_line.startswith("    "):
            finish()
        if len(reporter_line) > 4096 or (
            reporter_line and not reporter_line.isprintable()
        ):
            current = None
            continue
        if len(diagnostics) >= _PLAYWRIGHT_FAILURE_DIAGNOSTIC_LIMIT:
            break

        header = _PLAYWRIGHT_FAILURE_HEADER.match(reporter_line)
        if header is not None:
            source = _PLAYWRIGHT_FAILURE_SOURCES.get(header["source"])
            project = _PLAYWRIGHT_FAILURE_PROJECTS.get(header["project"])
            if source is None or project is None:
                current = None
                continue
            if source not in source_lines:
                try:
                    source_lines[source] = (
                        (cwd / source).read_text(encoding="utf-8").splitlines()
                    )
                except (OSError, UnicodeError):
                    source_lines[source] = []
            lines = source_lines[source]
            line_number = int(header["line"])
            column = int(header["column"])
            if line_number > len(lines) or column > len(lines[line_number - 1]) + 1:
                current = None
                continue
            current = {
                "project": project,
                "source": source,
                "line": line_number,
                "category": "unknown",
                "matcher": "none",
                "locator": "none",
                "in_call_log": False,
            }
            continue
        if current is None:
            continue

        if _PLAYWRIGHT_FAILURE_CALL_LOG_START.fullmatch(reporter_line):
            current["in_call_log"] = True
            continue
        if current["in_call_log"]:
            locator = _PLAYWRIGHT_FAILURE_LOCATOR_CALL.match(reporter_line)
            if locator is not None and current["locator"] == "none":
                current["locator"] = _PLAYWRIGHT_FAILURE_LOCATOR_CATEGORIES[
                    locator["method"]
                ]
            elif not reporter_line.startswith("      "):
                current["in_call_log"] = False

        if current["category"] != "unknown":
            continue
        if _PLAYWRIGHT_FAILURE_TIMEOUT_LINE.fullmatch(reporter_line):
            current["category"] = "timeout"
        elif _PLAYWRIGHT_FAILURE_EXPECT_LINE.match(reporter_line):
            current["category"] = "assertion"
            matcher = _PLAYWRIGHT_FAILURE_MATCHER_HEADER.match(reporter_line)
            if matcher is None:
                current["matcher"] = "other"
            else:
                matcher_name = matcher["matcher"]
                current["matcher"] = (
                    f"not.{matcher_name}" if matcher["negated"] else matcher_name
                )
        elif _PLAYWRIGHT_FAILURE_NAVIGATION_LINE.match(reporter_line):
            current["category"] = "navigation"
        elif _PLAYWRIGHT_FAILURE_LOCATOR_LINE.match(reporter_line):
            current["category"] = "locator"
        elif _PLAYWRIGHT_FAILURE_RUNTIME_LINE.match(reporter_line):
            current["category"] = "runtime"

    finish()
    return diagnostics
