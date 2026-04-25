import asyncio

import httpx


async def test_httpx():
    async with httpx.AsyncClient(base_url="http://testserver/api/v1") as client:
        print(f"Base URL: {client.base_url}")
        print(
            f"Requesting '/auth/mfa/verify' -> {client.build_request('POST', '/auth/mfa/verify').url}"
        )
        print(
            f"Requesting 'auth/mfa/verify' -> {client.build_request('POST', 'auth/mfa/verify').url}"
        )


asyncio.run(test_httpx())
