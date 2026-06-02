import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_query_budget_gate_passes_under_budget(root_client):
    # The news endpoint executes a database query and should be well under the default budget.
    response = await root_client.get("/api/v1/news")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_query_budget_gate_honors_override_header(root_client):
    # We can raise the budget using the X-Query-Budget header.
    response = await root_client.get("/api/v1/news", headers={"X-Query-Budget": "10"})
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_query_budget_gate_honors_disable_header(root_client):
    # We can disable the budget check entirely.
    response = await root_client.get(
        "/api/v1/news", headers={"X-Disable-Query-Budget": "true"}
    )
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_query_budget_gate_fails_when_exceeded(root_client):
    # By setting the budget to 0 via the header, any query executed (such as fetching news)
    # will exceed the budget and raise a pytest failure.
    with pytest.raises(pytest.fail.Exception) as excinfo:
        await root_client.get("/api/v1/news", headers={"X-Query-Budget": "0"})

    assert "SQL Query Budget exceeded" in str(excinfo.value)
