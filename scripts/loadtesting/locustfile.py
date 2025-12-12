import os

from locust import HttpUser, between, task


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
GROUP_ID = os.getenv("GROUP_ID", "1")
CHAT_ID = os.getenv("CHAT_ID", "1")
CACHE_PROFILE = os.getenv("CACHE_PROFILE", "memory")


class APILoadUser(HttpUser):
    host = BASE_URL
    wait_time = between(0.5, 1.5)

    def on_start(self):
        headers = {
            "Accept-Encoding": "br,gzip",
            "X-Cache-Profile": CACHE_PROFILE,
        }
        if AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
        self.common_headers = headers

    @task(3)
    def schedule(self):
        self.client.get(
            f"/schedule/{GROUP_ID}",
            headers=self.common_headers,
            name="schedule",
        )

    @task(2)
    def news(self):
        self.client.get(
            "/news?limit=20",
            headers=self.common_headers,
            name="news",
        )

    @task(3)
    def events(self):
        self.client.get(
            "/events?limit=25&is_active=true",
            headers=self.common_headers,
            name="events",
        )

    @task(2)
    def chat(self):
        self.client.get(
            f"/chat/{CHAT_ID}/messages?limit=25",
            headers=self.common_headers,
            name="chat",
        )
