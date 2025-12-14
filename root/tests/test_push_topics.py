import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services import push_topics


@settings(max_examples=25)
@given(
    raw_topics=st.lists(
        st.sampled_from(["News", "NEWS", "events", "system", "custom", ""]),
        min_size=1,
        max_size=6,
    )
)
def test_normalize_topics_respects_allowed_and_deduplicates(raw_topics: list[str]) -> None:
    allowed = {"news", "events", "system", "custom"}
    normalized = push_topics.normalize_topics(raw_topics, allowed_topics=allowed)

    expected: list[str] = []
    for raw in raw_topics:
        candidate = raw.strip().lower()
        if candidate and candidate in allowed and candidate not in expected:
            expected.append(candidate)

    assert normalized == expected


def test_normalize_topic_strict_unknown_topic():
    with pytest.raises(ValueError):
        push_topics.normalize_topic(
            "unsupported", allowed_topics={"news"}, strict=True
        )


def test_sort_topics_uses_allowed_order():
    allowed = ["system", "events", "news"]
    topics = ["news", "system", "events"]

    assert push_topics.sort_topics(topics, allowed_topics=allowed) == [
        "system",
        "events",
        "news",
    ]
