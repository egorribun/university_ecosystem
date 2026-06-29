from hypothesis import strategies as st

from app.schemas.dtos import UserCreate

# Strategy for Pydantic Models
user_create_strategy = st.builds(
    UserCreate,
    username=st.text(min_size=3),
    email=st.emails(),
    password=st.text(min_size=8),
)

# Strategy for Validator logic
email_strategy = st.emails()
