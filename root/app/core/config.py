from functools import cached_property
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    frontend_origin: str = "http://localhost:5173"
    frontend_origins: str = ""
    app_base_url: str = "http://localhost:5173"
    static_dir: str = "app/static"
    trusted_hosts: str = "localhost,127.0.0.1"
    auto_create_schema: bool = True
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    mail_from: str = "no-reply@example.com"
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8000/spotify/callback"
    spotify_scopes: str = "user-read-currently-playing user-read-playback-state"
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = ""
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    @cached_property
    def SECRET_KEY(self):
        return self.secret_key

    @cached_property
    def ALGORITHM(self):
        return self.algorithm

    @cached_property
    def frontend_origins_list(self) -> list[str]:
        values: list[str] = []
        for v in (self.frontend_origins, self.frontend_origin, self.app_base_url):
            if not v:
                continue
            values.extend([p.strip().rstrip("/") for p in v.split(",") if p.strip()])
        values.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
        seen: set[str] = set()
        out: list[str] = []
        for o in values:
            if o and o not in seen:
                seen.add(o)
                out.append(o)
        return out

    @cached_property
    def trusted_hosts_list(self) -> list[str]:
        return [p.strip() for p in self.trusted_hosts.split(",") if p.strip()]

settings = Settings()