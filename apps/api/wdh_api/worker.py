"""Durable DB-backed ingest worker. Run separately: python -m wdh_api.worker."""

import argparse
import signal
import time
from datetime import UTC, datetime, timedelta
from itertools import islice
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, sessionmaker
from wdh_adapters.files import Manifest, Record, iter_records, normalize
from wdh_domain.models import (
    Attachment,
    AuditEvent,
    Contact,
    Conversation,
    IngestBatch,
    Job,
    Message,
    MessageAttachment,
    MessageEvent,
    Observation,
    ProcessingResult,
    RawRecord,
    Review,
    Workspace,
)
from wdh_storage.cas import ContentStore

from wdh_api.config import Settings, get_settings
from wdh_api.db import make_engine, sessions
from wdh_api.ingest import fingerprint, sniff


class LeaseLost(Exception):
    pass


def review(session: Session, workspace: str, kind: str, key: str, payload: dict[str, Any]) -> None:
    existing = session.scalar(
        select(Review.id).where(Review.workspace_id == workspace, Review.review_key == key)
    )
    if not existing:
        session.add(
            Review(workspace_id=workspace, review_type=kind, review_key=key, payload=payload)
        )


def normalize_record(
    session: Session,
    store: ContentStore,
    batch: IngestBatch,
    manifest: Manifest,
    raw: RawRecord,
    value: dict[str, Any],
) -> None:
    workspace = batch.workspace_id
    conversation = session.scalar(
        select(Conversation).where(
            Conversation.workspace_id == workspace,
            Conversation.account_id == batch.account_id,
            Conversation.native_ref == value["conversation_ref"],
        )
    )
    if not conversation:
        conversation = Conversation(
            workspace_id=workspace,
            account_id=batch.account_id,
            native_ref=value["conversation_ref"],
            title=str(value.get("conversation_title") or value["conversation_ref"])[:300],
            kind=str(value.get("conversation_kind") or "unknown"),
        )
        session.add(conversation)
        session.flush()
    contact = None
    sender = value.get("sender_ref")
    if sender:
        if not isinstance(sender, str) or len(sender) > 200:
            raise ValueError("INVALID_SENDER_REFERENCE")
        contact = session.scalar(
            select(Contact).where(
                Contact.workspace_id == workspace,
                Contact.account_id == batch.account_id,
                Contact.native_ref == sender,
            )
        )
        name = str(value.get("sender_name") or sender)[:300]
        if not contact:
            contact = Contact(
                workspace_id=workspace,
                account_id=batch.account_id,
                native_ref=sender,
                display_name=name,
                aliases=[],
            )
            session.add(contact)
            session.flush()
            same_name = session.scalar(
                select(Contact)
                .where(
                    Contact.workspace_id == workspace,
                    Contact.account_id == batch.account_id,
                    Contact.display_name == name,
                    Contact.id != contact.id,
                )
                .limit(1)
            )
            if same_name:
                review(
                    session,
                    workspace,
                    "identity",
                    fingerprint(sorted([contact.id, same_name.id])),
                    {"contact_ids": [same_name.id, contact.id]},
                )
        if not any(alias["name"] == name for alias in contact.aliases):
            contact.aliases = [*contact.aliases, {"name": name, "raw_record_id": raw.id}]
    for key in ("source_record_id", "native_server_id", "reply_to", "direction"):
        item = value.get(key)
        if item is not None and (not isinstance(item, (str, int)) or len(str(item)) > 200):
            raise ValueError("INVALID_SOURCE_IDENTIFIER")
    signature = fingerprint(
        [
            value.get(key)
            for key in (
                "sent_at",
                "body_text",
                "message_type",
                "original_type_code",
                "sender_ref",
                "direction",
            )
        ]
    )
    native = str(value["native_server_id"]) if value.get("native_server_id") else None
    strong = (
        fingerprint([batch.account_id, conversation.id, manifest.certified_namespace, native])
        if native and manifest.certified_namespace
        else None
    )
    weak = fingerprint(
        [batch.account_id, conversation.id, signature, value["original_time_precision"]]
    )
    message = (
        session.scalar(
            select(Message).where(Message.workspace_id == workspace, Message.strong_key == strong)
        )
        if strong
        else None
    )
    reply_ref = str(value["reply_to"]) if value.get("reply_to") is not None else None
    conflicting = (
        message
        if message
        and (message.content_signature != signature or message.reply_source_ref != reply_ref)
        else None
    )
    while message and message.merged_into:
        message = session.scalar(
            select(Message).where(
                Message.workspace_id == workspace, Message.id == message.merged_into
            )
        )
    if message and (
        message.content_signature != signature or message.reply_source_ref != reply_ref
    ):
        conflicting = message
    if conflicting:
        message = None
    if not message:
        possible = session.scalar(
            select(Message)
            .where(
                Message.workspace_id == workspace,
                Message.weak_key == weak,
                Message.merged_into.is_(None),
            )
            .limit(1)
        )
        message = Message(
            workspace_id=workspace,
            account_id=batch.account_id,
            conversation_id=conversation.id,
            sender_contact_id=contact.id if contact else None,
            sent_at=value["sent_at"],
            original_time_text=value["original_time_text"],
            original_time_precision=value["original_time_precision"],
            message_type=value["message_type"],
            original_type_code=value["original_type_code"],
            body_text=value["body_text"],
            search_text=value["search_text"],
            strong_key=None if conflicting else strong,
            weak_key=weak,
            content_signature=signature,
            native_server_id=native,
            direction=str(value["direction"]) if value.get("direction") is not None else None,
            reply_source_ref=str(value["reply_to"]) if value.get("reply_to") else None,
        )
        session.add(message)
        session.flush()
        other = conflicting or possible
        if other:
            kind = "conflict" if conflicting else "duplicate"
            other.merge_status = message.merge_status = "conflicted" if conflicting else "candidate"
            review(
                session,
                workspace,
                kind,
                fingerprint(sorted([message.id, other.id])),
                {"message_ids": [other.id, message.id]},
            )
    else:
        message.merge_status = "verified"
    observation = Observation(
        workspace_id=workspace,
        message_id=message.id,
        batch_id=batch.id,
        raw_record_id=raw.id,
        device_id=batch.device_id,
        source_message_id=str(value["source_record_id"]) if value.get("source_record_id") else None,
        observed_fields={
            "field_provenance": value["field_provenance"],
            "normalization_version": "1.0.0",
            "adapter_version": batch.adapter_version,
        },
    )
    session.add(observation)
    files = batch.manifest["_archive"]["files"]
    for position, media in enumerate(value["media"]):
        path = media["path"]
        metadata = files.get(path) or files.get(str(PurePosixPath(manifest.media_base_path) / path))
        attachment = (
            session.scalar(
                select(Attachment).where(
                    Attachment.workspace_id == workspace, Attachment.sha256 == metadata["sha256"]
                )
            )
            if metadata
            else None
        )
        if not attachment:
            mime = "application/octet-stream"
            if metadata:
                with store.open(metadata["sha256"]) as stream:
                    mime = sniff(stream.read(32))
            attachment = Attachment(
                workspace_id=workspace,
                sha256=metadata["sha256"] if metadata else None,
                byte_size=metadata["byte_size"] if metadata else None,
                original_filename=PurePosixPath(path).name,
                availability="available" if metadata else "missing",
                mime_type=mime,
            )
            session.add(attachment)
            session.flush()
        session.add(
            MessageAttachment(
                workspace_id=workspace,
                message_id=message.id,
                attachment_id=attachment.id,
                raw_record_id=raw.id,
                position=position,
                original_media_path=path,
            )
        )
    if value.get("event") or value["message_type"] == "system":
        session.add(
            MessageEvent(
                workspace_id=workspace,
                message_id=message.id,
                raw_record_id=raw.id,
                event_type=str(value.get("event") or "system")[:50],
                payload={"source_record_id": observation.source_message_id},
            )
        )
    raw.parse_status = "normalized"


class Worker:
    def __init__(self, settings: Settings, factory: sessionmaker[Session] | None = None) -> None:
        self.settings = settings
        self.engine = None if factory else make_engine(settings)
        self.factory = factory or sessions(self.engine)  # type: ignore[arg-type]
        self.store = ContentStore(settings.data_root, settings.import_max_bytes)

    def claim(self) -> tuple[str, str] | None:
        now = datetime.now(UTC)
        with self.factory.begin() as session:
            eligible = or_(
                Job.status == "queued",
                and_(
                    Job.status == "failed_retryable",
                    or_(Job.next_retry_at.is_(None), Job.next_retry_at <= now),
                ),
                and_(Job.status == "running", Job.lease_until < now),
            )
            job = session.scalar(
                select(Job)
                .where(
                    Job.kind.in_(["ingest", "ocr", "asr", "embedding", "llm", "model_install"]),
                    eligible,
                )
                .order_by(Job.created_at, Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if not job:
                return None
            if job.attempt_count >= 4:
                job.status, job.failure_code = "dead_letter", "RETRY_LIMIT"
                return None
            token = uuid4().hex
            job.status, job.lease_token = "running", token
            job.attempt_count += 1
            job.lease_until = now + timedelta(
                seconds=90
                if job.kind == "ingest"
                else 660
                if job.kind == "model_install"
                else self.settings.processing_timeout_seconds + 60
            )
            job.updated_at = now
            return job.id, token

    @staticmethod
    def owned_job(session: Session, job_id: str, token: str) -> Job:
        job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job or job.status != "running" or job.lease_token != token:
            raise LeaseLost()
        return job

    def chunk(self, job_id: str, token: str, path: str, records: list[Record]) -> None:
        with self.factory.begin() as session:
            job = self.owned_job(session, job_id, token)
            session.scalar(
                select(Workspace).where(Workspace.id == job.workspace_id).with_for_update()
            )
            batch = session.get(IngestBatch, job.batch_id)
            if batch is None:
                raise ValueError("BATCH_NOT_FOUND")
            batch.batch_status = "normalizing"
            manifest = Manifest.model_validate(batch.manifest)
            for source in records:
                locator = f"{path}#{source.locator}"
                if session.scalar(
                    select(RawRecord.id).where(
                        RawRecord.batch_id == batch.id, RawRecord.source_record_locator == locator
                    )
                ):
                    continue
                raw = RawRecord(
                    workspace_id=batch.workspace_id,
                    batch_id=batch.id,
                    source_record_locator=locator,
                    raw_sha256=source.sha256,
                    raw_payload=source.payload,
                    source_primary_key=str(source.payload.get("source_record_id", ""))[:200]
                    if source.payload
                    else None,
                    parse_status="quarantined" if source.error else "pending",
                    parse_errors=[{"code": source.error}] if source.error else [],
                )
                session.add(raw)
                session.flush()
                if not source.error and source.payload is not None:
                    try:
                        normalized = normalize(source.payload, manifest)
                        with session.begin_nested():
                            normalize_record(session, self.store, batch, manifest, raw, normalized)
                    except (ValueError, OverflowError, OSError) as exc:
                        code = str(exc) if re_safe_code(str(exc)) else "INVALID_RECORD"
                        raw.parse_status, raw.parse_errors = "quarantined", [{"code": code}]
            job.lease_until = datetime.now(UTC) + timedelta(seconds=90)
            job.updated_at = datetime.now(UTC)

    def run_claimed(self, job_id: str, token: str) -> None:
        try:
            with self.factory() as session:
                job = self.owned_job(session, job_id, token)
                if job.kind == "model_install":
                    session.close()
                    self.install_model(job_id, token)
                    return
                if job.kind != "ingest":
                    session.close()
                    self.run_processing(job_id, token)
                    return
                batch = session.get(IngestBatch, job.batch_id) if job.batch_id else None
                if batch is None:
                    raise ValueError("BATCH_NOT_FOUND")
                manifest = Manifest.model_validate(batch.manifest)
                files = batch.manifest["_archive"]["files"]
            for payload in manifest.payload_files:
                with self.store.open(files[payload.path]["sha256"]) as stream:
                    iterator = iter_records(stream, manifest)
                    while records := list(islice(iterator, 100)):
                        self.chunk(job_id, token, payload.path, records)
            with self.factory.begin() as session:
                job = self.owned_job(session, job_id, token)
                batch = session.get(IngestBatch, job.batch_id)
                if batch is None:
                    raise ValueError("BATCH_NOT_FOUND")
                # Resolve references within the same account/conversation; retain source keys.
                unresolved = session.scalars(
                    select(Message).where(
                        Message.workspace_id == job.workspace_id,
                        Message.reply_source_ref.is_not(None),
                        Message.reply_to_id.is_(None),
                    )
                )
                for message in unresolved:
                    sources = list(
                        session.scalars(
                            select(Observation).where(
                                Observation.workspace_id == job.workspace_id,
                                Observation.message_id == message.id,
                            )
                        )
                    )
                    targets = (
                        select(Message)
                        .join(Observation, Observation.message_id == Message.id)
                        .where(
                            Message.workspace_id == job.workspace_id,
                            Message.account_id == message.account_id,
                            Message.conversation_id == message.conversation_id,
                            Observation.source_message_id == message.reply_source_ref,
                        )
                    )
                    matches = list(
                        session.scalars(
                            targets.where(
                                Observation.batch_id.in_([source.batch_id for source in sources])
                            )
                            .distinct()
                            .limit(2)
                        )
                    )
                    if not matches:
                        matches = list(
                            session.scalars(
                                targets.where(
                                    Observation.device_id.in_(
                                        [source.device_id for source in sources]
                                    )
                                )
                                .distinct()
                                .limit(2)
                            )
                        )
                    if len(matches) == 1:
                        message.reply_to_id = matches[0].merged_into or matches[0].id
                errors = (
                    session.scalar(
                        select(func.count())
                        .select_from(RawRecord)
                        .where(
                            RawRecord.batch_id == batch.id, RawRecord.parse_status == "quarantined"
                        )
                    )
                    or 0
                )
                batch.batch_status = "review_required" if errors else "completed"
                job.status, job.lease_until = "completed", None
                job.failure_code, job.updated_at = None, datetime.now(UTC)
                session.add(
                    AuditEvent(
                        workspace_id=job.workspace_id,
                        event_type="import.completed",
                        object_id=batch.id,
                        details={"quarantined": errors},
                    )
                )
        except LeaseLost:
            return
        except Exception as exc:
            from wdh_api.processing import ModelBusy

            with self.factory.begin() as session:
                try:
                    job = self.owned_job(session, job_id, token)
                except LeaseLost:
                    return
                permanent = isinstance(exc, (ValueError, KeyError, zipfile_error()))
                if isinstance(exc, ModelBusy):
                    job.attempt_count -= 1
                job.status = (
                    "failed_permanent"
                    if permanent
                    else ("dead_letter" if job.attempt_count >= 4 else "failed_retryable")
                )
                job.failure_code = (
                    (str(exc) if re_safe_code(str(exc)) else "INVALID_SOURCE")
                    if permanent
                    else "LOCAL_MODEL_BUSY"
                    if isinstance(exc, ModelBusy)
                    else "PROCESSING_FAILED"
                )
                job.lease_until = None
                job.next_retry_at = datetime.now(UTC) + timedelta(seconds=2**job.attempt_count)
                batch = session.get(IngestBatch, job.batch_id) if job.batch_id else None
                if batch:
                    batch.batch_status = job.status

    def run_processing(self, job_id: str, token: str) -> None:
        from wdh_api import ai, processing

        with self.factory() as session:
            job = self.owned_job(session, job_id, token)
            if not processing.enabled(session, self.settings, job.workspace_id, job.kind):
                raise ValueError("MODULE_DISABLED")
            result = session.scalar(
                select(ProcessingResult).where(ProcessingResult.job_id == job.id)
            )
            if not result:
                raise ValueError("PROCESSING_RESULT_MISSING")
            kind = job.kind
            source_id = job.payload.get("source_result_id")
            actor_id = job.payload.get("actor_id")
            attachment = None
            source_text = ""
            if kind in {"ocr", "asr"}:
                attachment = session.get(Attachment, result.attachment_id)
                if not attachment or attachment.workspace_id != job.workspace_id:
                    raise ValueError("ATTACHMENT_MISSING")
                if attachment.sha256 != result.source_sha256:
                    raise ValueError("SOURCE_CHANGED")
                session.expunge(attachment)
            else:
                source_text = ai.material(session, job.workspace_id, result.message_id, source_id)
                if ai.text_hash(source_text) != result.source_sha256:
                    raise ValueError("SOURCE_CHANGED")
            current = processing.capability(self.settings, job.kind)
            if not current["available"]:
                raise ValueError("PROVIDER_UNAVAILABLE")
            if current["provider_version"] != result.provider_version:
                raise ValueError("PROVIDER_VERSION_CHANGED")
        if kind in {"ocr", "asr"}:
            if attachment is None:
                raise ValueError("ATTACHMENT_MISSING")
            processor = processing.ocr if kind == "ocr" else processing.asr
            text, details = processor(self.settings, self.store, attachment)
        else:
            processor_ai = ai.embedding if kind == "embedding" else ai.extract
            text, details = processor_ai(self.settings, source_text)
            details["source_result_id"] = source_id
        with self.factory.begin() as session:
            job = self.owned_job(session, job_id, token)
            if not processing.enabled(session, self.settings, job.workspace_id, job.kind):
                raise ValueError("MODULE_DISABLED")
            result = session.scalar(
                select(ProcessingResult).where(ProcessingResult.job_id == job.id)
            )
            if not result:
                raise ValueError("PROCESSING_RESULT_MISSING")
            if kind in {"embedding", "llm"}:
                current_source = ai.material(
                    session, job.workspace_id, result.message_id, source_id, lock=True
                )
                if ai.text_hash(current_source) != result.source_sha256:
                    raise ValueError("SOURCE_CHANGED")
                if kind == "llm":
                    if not actor_id:
                        raise ValueError("INVALID_JOB_CONTEXT")
                    ai.persist_candidates(session, result, details, source_id, actor_id)
            result.text, result.search_text, result.details = text, processing.folded(text), details
            if kind == "embedding":
                from wdh_api.semantic import write_index

                write_index(session, result)
            job.status, job.lease_until = "completed", None
            job.failure_code, job.updated_at = None, datetime.now(UTC)
            session.add(
                AuditEvent(
                    workspace_id=job.workspace_id,
                    event_type="processing.completed",
                    object_id=job.id,
                    details={"kind": job.kind},
                )
            )

    def install_model(self, job_id: str, token: str) -> None:
        from wdh_api.models import install, revision
        from wdh_api.processing import KINDS

        with self.factory() as session:
            job = self.owned_job(session, job_id, token)
            module = job.payload.get("module")
            if module not in KINDS or job.payload.get("asset_revision") != revision(module):
                raise ValueError("MODEL_VERSION_CHANGED")
        checked = 0.0

        def checkpoint() -> None:
            nonlocal checked
            if time.monotonic() - checked < 2:
                return
            with self.factory() as session:
                self.owned_job(session, job_id, token)
            checked = time.monotonic()

        install(module, self.settings, checkpoint=checkpoint)
        with self.factory.begin() as session:
            job = self.owned_job(session, job_id, token)
            job.status, job.failure_code, job.lease_until = "completed", None, None
            job.updated_at = datetime.now(UTC)
            session.add(
                AuditEvent(
                    workspace_id=job.workspace_id,
                    event_type="model.installed",
                    object_id=job.id,
                    details={"module": module},
                )
            )

    def run_once(self) -> bool:
        claimed = self.claim()
        if not claimed:
            return False
        self.run_claimed(*claimed)
        return True


def re_safe_code(code: str) -> bool:
    return bool(code) and len(code) <= 80 and all(c.isupper() or c == "_" for c in code)


def zipfile_error() -> type[Exception]:
    from zipfile import BadZipFile

    return BadZipFile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    worker = Worker(settings)
    stopping = False

    def stop(_: int, __: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        ran = worker.run_once()
        if args.once:
            break
        if not ran:
            time.sleep(settings.worker_poll_seconds)
    if worker.engine:
        worker.engine.dispose()


if __name__ == "__main__":
    main()
