import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.utils.encryption import EncryptedString


class SpotifyIntegration(Base):
    __tablename__ = "spotify_integrations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    spotify_user_id = Column(String, unique=True, index=True)
    access_token: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(EncryptedString(), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), index=True)
    scope = Column(String)
    display_name = Column(String)
    is_connected = Column(Boolean, default=False, index=True)
    is_playing = Column(Boolean, default=False, index=True)
    last_checked_at = Column(DateTime(timezone=True), index=True)
    last_track_id = Column(String, index=True)
    last_track_name = Column(String)
    last_artist_name = Column(String)
    last_album_name = Column(String)
    last_track_url = Column(String)
    last_album_image_url = Column(String)

    user = relationship("User", back_populates="spotify")

    def __repr__(self) -> str:
        return (
            f"<SpotifyIntegration(user_id={self.user_id}, "
            f"connected={self.is_connected}, playing={self.is_playing})>"
        )
