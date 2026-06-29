from hypothesis import given
from hypothesis import strategies as st

from app.utils.pagination import paginate


@given(
    st.integers(min_value=-100, max_value=1000), st.integers(min_value=1, max_value=100)
)
def test_pagination_bounds(page, size):
    result = paginate(page=page, size=size)
    assert result.offset >= 0
    assert result.limit > 0
