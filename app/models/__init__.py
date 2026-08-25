from app.core.database import Base as Base
from app.models.auth import (
    ActiveSession as ActiveSession,
)
from app.models.auth import (
    ChallengeState as ChallengeState,
)
from app.models.auth import (
    EmailChangeToken as EmailChangeToken,
)
from app.models.auth import (
    FailedLoginAttempt as FailedLoginAttempt,
)
from app.models.auth import (
    LoginHistory as LoginHistory,
)
from app.models.auth import (
    MfaChallenge as MfaChallenge,
)
from app.models.auth import (
    MfaEmailDelivery as MfaEmailDelivery,
)
from app.models.auth import (
    MfaTotpEnrollment as MfaTotpEnrollment,
)
from app.models.auth import (
    PasswordResetToken as PasswordResetToken,
)
from app.models.auth import (
    RecoveryCode as RecoveryCode,
)
from app.models.auth import (
    TrustedDevice as TrustedDevice,
)
from app.models.chat import (
    Attachment as Attachment,
)
from app.models.chat import (
    Chat as Chat,
)
from app.models.chat import (
    ChatReadReceipt as ChatReadReceipt,
)
from app.models.chat import (
    Message as Message,
)
from app.models.chat import (
    MessageReaction as MessageReaction,
)
from app.models.cwv import CwvObservation as CwvObservation
from app.models.dead_letter import (
    DeadLetterJob as DeadLetterJob,
)
from app.models.dead_letter import (
    JobStatus as JobStatus,
)
from app.models.domain_events import StoredEvent as StoredEvent
from app.models.enums import UserRole as UserRole
from app.models.events import (
    Event as Event,
)
from app.models.events import (
    EventAttendance as EventAttendance,
)
from app.models.events import (
    EventFile as EventFile,
)
from app.models.failed_outbox_events import FailedOutboxEvent as FailedOutboxEvent
from app.models.grade import Grade as Grade
from app.models.logs import DataAccessLog as DataAccessLog
from app.models.news import (
    News as News,
)
from app.models.news import (
    NewsComment as NewsComment,
)
from app.models.news import (
    NewsLike as NewsLike,
)
from app.models.notifications import (
    Notification as Notification,
)
from app.models.notifications import (
    NotificationDelivery as NotificationDelivery,
)
from app.models.notifications import (
    NotificationQueueJob as NotificationQueueJob,
)
from app.models.notifications import (
    PushSubscription as PushSubscription,
)
from app.models.notifications import (
    UserPushTopic as UserPushTopic,
)
from app.models.schedule import Group as Group
from app.models.schedule import Schedule as Schedule
from app.models.spotify import SpotifyIntegration as SpotifyIntegration
from app.models.stories import Story as Story
from app.models.tenant import Tenant as Tenant
from app.models.users import (
    EducationPath as EducationPath,
)
from app.models.users import (
    InviteCode as InviteCode,
)
from app.models.users import (
    User as User,
)
from app.models.users import (
    UserPreferences as UserPreferences,
)
from app.models.users import (
    UserProfile as UserProfile,
)
from app.models.vector_shard import VectorChunk as VectorChunk


# Re-added DeadLetterJob (fixed Alembic schema drift; model moved to app/models/dead_letter.py)
