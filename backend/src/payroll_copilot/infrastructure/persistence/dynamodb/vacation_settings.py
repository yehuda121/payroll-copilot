"""DynamoDB vacation settings, OTP, pipeline counters, integration credentials."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from boto3.dynamodb.conditions import Attr

from payroll_copilot.application.ports.vacation_settings import (
    EmailOwnershipOtp,
    EmailOwnershipOtpRepository,
    IntegrationCredential,
    IntegrationCredentialRepository,
    VacationMailboxSettings,
    VacationPipelineAnalyticsRepository,
    VacationSettingsRepository,
)
from payroll_copilot.infrastructure.persistence.dynamodb import keys
from payroll_copilot.infrastructure.persistence.dynamodb.client import GSI2, DynamoTable
from payroll_copilot.infrastructure.persistence.dynamodb.serde import dumps_value, loads_datetime, loads_uuid


def _now() -> datetime:
    return datetime.now(UTC)


class DynamoVacationSettingsRepository(VacationSettingsRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _defaults(self, organization_id: UUID) -> VacationMailboxSettings:
        return VacationMailboxSettings(organization_id=organization_id)

    def _to_entity(self, organization_id: UUID, item: dict) -> VacationMailboxSettings:
        return VacationMailboxSettings(
            organization_id=organization_id,
            monitored_email_verified=item.get("monitored_email_verified"),
            monitored_email_pending=item.get("monitored_email_pending"),
            notification_email_verified=item.get("notification_email_verified"),
            notification_email_pending=item.get("notification_email_pending"),
            notify_on_new_vacation=bool(item.get("notify_on_new_vacation", True)),
            notify_on_error_or_attention=bool(item.get("notify_on_error_or_attention", True)),
            active_monitored_email=item.get("active_monitored_email"),
            pending_monitored_verified_at=loads_datetime(item.get("pending_monitored_verified_at")),
            mailbox_connection_status=str(item.get("mailbox_connection_status") or "disconnected"),
            mailbox_last_check_at=loads_datetime(item.get("mailbox_last_check_at")),
            mailbox_last_processed_at=loads_datetime(item.get("mailbox_last_processed_at")),
            mailbox_last_processed_message_id=item.get("mailbox_last_processed_message_id"),
            mailbox_last_error_code=item.get("mailbox_last_error_code"),
            mailbox_last_error_message=item.get("mailbox_last_error_message"),
            updated_at=loads_datetime(item.get("updated_at")),
        )

    async def get(self, organization_id: UUID) -> VacationMailboxSettings:
        item = await self._table.get_item(
            {"PK": keys.org_pk(organization_id), "SK": keys.vac_settings_sk()}
        )
        if item is None:
            return self._defaults(organization_id)
        return self._to_entity(organization_id, item)

    async def save(self, settings: VacationMailboxSettings) -> VacationMailboxSettings:
        settings.updated_at = _now()
        item = {
            "PK": keys.org_pk(settings.organization_id),
            "SK": keys.vac_settings_sk(),
            "entity_type": "vacation_settings",
            "organization_id": str(settings.organization_id),
            "monitored_email_verified": settings.monitored_email_verified,
            "monitored_email_pending": settings.monitored_email_pending,
            "notification_email_verified": settings.notification_email_verified,
            "notification_email_pending": settings.notification_email_pending,
            "notify_on_new_vacation": settings.notify_on_new_vacation,
            "notify_on_error_or_attention": settings.notify_on_error_or_attention,
            "active_monitored_email": settings.active_monitored_email,
            "pending_monitored_verified_at": dumps_value(settings.pending_monitored_verified_at),
            "mailbox_connection_status": settings.mailbox_connection_status,
            "mailbox_last_check_at": dumps_value(settings.mailbox_last_check_at),
            "mailbox_last_processed_at": dumps_value(settings.mailbox_last_processed_at),
            "mailbox_last_processed_message_id": settings.mailbox_last_processed_message_id,
            "mailbox_last_error_code": settings.mailbox_last_error_code,
            "mailbox_last_error_message": settings.mailbox_last_error_message,
            "updated_at": dumps_value(settings.updated_at),
        }
        await self._table.put_item({k: v for k, v in item.items() if v is not None})
        return settings


class DynamoEmailOwnershipOtpRepository(EmailOwnershipOtpRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    async def save(self, otp: EmailOwnershipOtp) -> None:
        email = otp.email.strip().lower()
        item = {
            "PK": keys.org_pk(otp.organization_id),
            "SK": keys.vac_otp_sk(purpose=otp.purpose, email=email),
            "entity_type": "email_ownership_otp",
            "organization_id": str(otp.organization_id),
            "purpose": otp.purpose,
            "email": email,
            "code_hash": otp.code_hash,
            "expires_at": otp.expires_at.isoformat(),
            "attempts": otp.attempts,
            "max_attempts": otp.max_attempts,
            "created_at": (otp.created_at or _now()).isoformat(),
            # Dynamo TTL attribute (epoch seconds)
            "ttl": int(otp.expires_at.timestamp()),
        }
        await self._table.put_item(item)

    async def get(
        self, organization_id: UUID, *, purpose: str, email: str
    ) -> EmailOwnershipOtp | None:
        item = await self._table.get_item(
            {
                "PK": keys.org_pk(organization_id),
                "SK": keys.vac_otp_sk(purpose=purpose, email=email.strip().lower()),
            }
        )
        if item is None:
            return None
        expires = loads_datetime(item.get("expires_at"))
        if expires is None:
            return None
        return EmailOwnershipOtp(
            organization_id=organization_id,
            purpose=str(item.get("purpose") or purpose),
            email=str(item.get("email") or email),
            code_hash=str(item.get("code_hash") or ""),
            expires_at=expires,
            attempts=int(item.get("attempts") or 0),
            max_attempts=int(item.get("max_attempts") or 5),
            created_at=loads_datetime(item.get("created_at")),
        )

    async def delete(self, organization_id: UUID, *, purpose: str, email: str) -> None:
        await self._table.delete_item(
            {
                "PK": keys.org_pk(organization_id),
                "SK": keys.vac_otp_sk(purpose=purpose, email=email.strip().lower()),
            }
        )


class DynamoVacationPipelineAnalyticsRepository(VacationPipelineAnalyticsRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    async def increment(
        self,
        organization_id: UUID,
        *,
        day: str,
        event_type: str,
        amount: int = 1,
    ) -> None:
        key = {"PK": keys.org_pk(organization_id), "SK": keys.vac_pipe_sk(day)}
        existing = await self._table.get_item(key)
        if existing is None:
            await self._table.put_item(
                {
                    "PK": key["PK"],
                    "SK": key["SK"],
                    "entity_type": "vacation_pipeline_day",
                    "organization_id": str(organization_id),
                    "day": day,
                    "counters": {event_type: amount},
                }
            )
            return
        counters = dict(existing.get("counters") or {})
        counters[event_type] = int(counters.get(event_type) or 0) + amount
        await self._table.put_item(
            {
                **existing,
                "counters": counters,
            }
        )

    async def try_claim_event(
        self,
        organization_id: UUID,
        *,
        event_id: str,
        ttl_epoch: int,
    ) -> bool:
        item = {
            "PK": keys.org_pk(organization_id),
            "SK": keys.vac_event_dedup_sk(event_id),
            "entity_type": "vacation_event_dedup",
            "organization_id": str(organization_id),
            "event_id": event_id,
            "ttl": ttl_epoch,
            "created_at": _now().isoformat(),
        }
        try:
            await self._table.put_item(item, condition_expression=Attr("PK").not_exists())
            return True
        except Exception as exc:  # noqa: BLE001 — ConditionalCheckFailed
            name = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if name == "ConditionalCheckFailedException" or "ConditionalCheckFailed" in str(exc):
                return False
            # ClientError from botocore
            from botocore.exceptions import ClientError

            if isinstance(exc, ClientError):
                if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    return False
            raise

    async def get_counters(
        self, organization_id: UUID, *, year: int
    ) -> dict[str, dict[str, int]]:
        items = await self._table.query_eq_pk(
            keys.org_pk(organization_id),
            sk_begins_with=f"VAC_PIPE#{year:04d}-",
        )
        out: dict[str, dict[str, int]] = {}
        for item in items:
            if item.get("entity_type") != "vacation_pipeline_day":
                continue
            day = str(item.get("day") or "")
            counters = {
                str(k): int(v)
                for k, v in dict(item.get("counters") or {}).items()
            }
            out[day] = counters
        return out


class DynamoIntegrationCredentialRepository(IntegrationCredentialRepository):
    def __init__(self, table: DynamoTable) -> None:
        self._table = table

    def _to_entity(self, item: dict) -> IntegrationCredential:
        return IntegrationCredential(
            id=UUID(str(item["id"])),
            organization_id=UUID(str(item["organization_id"])),
            key_hash=str(item.get("key_hash") or ""),
            key_prefix=str(item.get("key_prefix") or ""),
            label=str(item.get("label") or "n8n"),
            created_at=loads_datetime(item.get("created_at")),
            rotated_at=loads_datetime(item.get("rotated_at")),
            revoked_at=loads_datetime(item.get("revoked_at")),
        )

    async def get_by_key_hash(self, key_hash: str) -> IntegrationCredential | None:
        items = await self._table.query_eq_pk(
            keys.gsi2_integration_key_hash(key_hash),
            index_name=GSI2,
            limit=5,
        )
        for item in items:
            if item.get("entity_type") != "integration_credential":
                continue
            if item.get("revoked_at"):
                continue
            return self._to_entity(item)
        return None

    async def list_for_org(self, organization_id: UUID) -> list[IntegrationCredential]:
        items = await self._table.query_eq_pk(
            keys.org_pk(organization_id),
            sk_begins_with="INTEGRATION#",
        )
        return [
            self._to_entity(item)
            for item in items
            if item.get("entity_type") == "integration_credential" and not item.get("revoked_at")
        ]

    async def save(self, credential: IntegrationCredential) -> IntegrationCredential:
        item = {
            "PK": keys.org_pk(credential.organization_id),
            "SK": keys.integration_cred_sk(credential.id),
            "entity_type": "integration_credential",
            "GSI2PK": keys.gsi2_integration_key_hash(credential.key_hash),
            "GSI2SK": keys.integration_cred_sk(credential.id),
            "id": str(credential.id),
            "organization_id": str(credential.organization_id),
            "key_hash": credential.key_hash,
            "key_prefix": credential.key_prefix,
            "label": credential.label,
            "created_at": dumps_value(credential.created_at or _now()),
            "rotated_at": dumps_value(credential.rotated_at),
            "revoked_at": dumps_value(credential.revoked_at),
        }
        await self._table.put_item({k: v for k, v in item.items() if v is not None})
        return credential

    async def revoke(self, organization_id: UUID, credential_id: UUID) -> None:
        existing = await self._table.get_item(
            {
                "PK": keys.org_pk(organization_id),
                "SK": keys.integration_cred_sk(credential_id),
            }
        )
        if existing is None:
            return
        cred = self._to_entity(existing)
        cred.revoked_at = _now()
        await self.save(cred)


def create_integration_api_key() -> tuple[str, str, str]:
    """Return (plaintext_key, key_hash, key_prefix)."""
    import hashlib
    import secrets

    raw = f"pcn8n_{secrets.token_urlsafe(32)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, digest, raw[:12]
