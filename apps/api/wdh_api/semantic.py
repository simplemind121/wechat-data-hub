"""Permission-filtered exact pgvector retrieval; JSON vectors are durable rebuild evidence."""

import json
import math
import re
from datetime import datetime
from importlib.resources import files
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from wdh_domain.models import Conversation, Job, Message, ProcessingResult

from wdh_api import ai, processing
from wdh_api.config import Settings
from wdh_api.security import ApiError


def ensure_index(session: Session) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    for statement in files("wdh_api").joinpath("vector_index.sql").read_text().split(";"):
        if statement.strip():
            session.execute(text(statement))


def write_index(session: Session, result: ProcessingResult) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    for index, chunk in enumerate(result.details["chunks"]):
        session.execute(
            text("""INSERT INTO wdh_vectors_v1.chunks
          (workspace_id,result_id,message_id,chunk_index,model_version,start_offset,end_offset,body_text,embedding)
          VALUES(CAST(:workspace AS uuid),CAST(:result AS uuid),CAST(:message AS uuid),
                 :index,:version,
                 :start,:end,:body,CAST(:vector AS public.vector(512)))
          ON CONFLICT(result_id,chunk_index) DO UPDATE SET message_id=EXCLUDED.message_id,
            model_version=EXCLUDED.model_version,start_offset=EXCLUDED.start_offset,
            end_offset=EXCLUDED.end_offset,body_text=EXCLUDED.body_text,embedding=EXCLUDED.embedding
          """),
            {
                "workspace": result.workspace_id,
                "result": result.id,
                "message": result.message_id,
                "index": index,
                "version": result.provider_version,
                "start": chunk["start"],
                "end": chunk["end"],
                "body": chunk["text"],
                "vector": json.dumps(chunk["vector"], allow_nan=False),
            },
        )


def visible_results(session: Session, workspace: str, version: str) -> Any:
    return (
        select(ProcessingResult)
        .join(Job, Job.id == ProcessingResult.job_id)
        .join(Message, Message.id == ProcessingResult.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            ProcessingResult.workspace_id == workspace,
            ProcessingResult.kind == "embedding",
            ProcessingResult.provider_version == version,
            Job.status == "completed",
            Message.merged_into.is_(None),
            Conversation.workspace_id == workspace,
            Conversation.privacy_scope == "business_approved",
        )
    )


def restore_cache(session: Session, workspace: str, version: str) -> None:
    # Only a derived cache is repaired; original messages and saved vectors are never rewritten.
    ensure_index(session)
    missing = visible_results(session, workspace, version).where(
        ~select(text("1"))
        .select_from(text("wdh_vectors_v1.chunks v"))
        .where(text("v.result_id = processing_results.id"))
        .exists()
    )
    for result in session.scalars(missing.execution_options(yield_per=100)):
        write_index(session, result)


def retrieve(
    session: Session,
    settings: Settings,
    workspace: str,
    query: str,
    conversation_id: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 10,
    mode: str = "semantic",
) -> list[dict[str, Any]]:
    if not processing.enabled(session, settings, workspace, "embedding"):
        raise ApiError(409, "MODULE_DISABLED", "请先启用本地语义检索模块")
    provider = processing.capability(settings, "embedding")
    if not provider["available"]:
        raise ApiError(409, "PROVIDER_UNAVAILABLE", "本地语义模型尚未就绪")
    vector = ai.query_vector(settings, query)
    version = provider["provider_version"]
    terms = [re.sub(r"\s+", "", processing.folded(term)) for term in query.split()]
    hits = []
    if session.get_bind().dialect.name == "postgresql":
        restore_cache(session, workspace, version)
        parameters: dict[str, Any] = {
            "workspace": workspace,
            "version": version,
            "query": json.dumps(vector),
            "limit": limit,
            "conversation": conversation_id,
            "start": start,
            "end": end,
            "terms": json.dumps(terms),
            "hybrid": mode == "hybrid",
        }
        records = session.execute(
            text(r"""WITH permitted AS MATERIALIZED (
            SELECT v.*,r.message_id AS current_message_id,
              NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(CAST(:terms AS jsonb)) term
                WHERE strpos(regexp_replace(lower(normalize(v.body_text,NFKC)),
                    '\s+','','g'),term.value)=0) AS lexical_match
            FROM wdh_vectors_v1.chunks v
            JOIN processing_results r ON r.id=v.result_id AND r.workspace_id=v.workspace_id
            JOIN jobs j ON j.id=r.job_id JOIN messages m ON m.id=r.message_id
            JOIN conversations c ON c.id=m.conversation_id
            WHERE v.workspace_id=CAST(:workspace AS uuid) AND v.model_version=:version
              AND j.status='completed' AND m.merged_into IS NULL
              AND c.privacy_scope='business_approved'
              AND c.workspace_id=CAST(:workspace AS uuid)
              AND (CAST(:conversation AS uuid) IS NULL
                   OR m.conversation_id=CAST(:conversation AS uuid))
              AND (CAST(:start AS timestamptz) IS NULL OR m.sent_at>=CAST(:start AS timestamptz))
              AND (CAST(:end AS timestamptz) IS NULL OR m.sent_at<=CAST(:end AS timestamptz))
            ), ranked AS (
            SELECT *,1-(embedding <=> CAST(:query AS public.vector(512))) AS similarity,
              row_number() OVER(PARTITION BY current_message_id
                 ORDER BY embedding <=> CAST(:query AS public.vector(512))) AS position,
              row_number() OVER(PARTITION BY current_message_id
                 ORDER BY lexical_match DESC,
                   embedding <=> CAST(:query AS public.vector(512))) AS keyword_position
              FROM permitted),
            semantic_hits AS (SELECT *, 'semantic' AS channel FROM ranked WHERE position=1
              ORDER BY similarity DESC,current_message_id LIMIT :limit),
            keyword_hits AS (SELECT *, 'keyword' AS channel FROM ranked
              WHERE :hybrid AND keyword_position=1 AND lexical_match
              ORDER BY similarity DESC,current_message_id LIMIT :limit)
            SELECT * FROM semantic_hits UNION ALL SELECT * FROM keyword_hits
              ORDER BY similarity DESC,current_message_id
            """),
            parameters,
        ).mappings()
        for row in records:
            hits.append(
                {
                    "message_id": str(row["current_message_id"]),
                    "result_id": str(row["result_id"]),
                    "source_span": row["body_text"],
                    "start": row["start_offset"],
                    "end": row["end_offset"],
                    "similarity": float(row["similarity"]),
                    "channel": row["channel"],
                }
            )
    else:
        records = visible_results(session, workspace, version)
        if conversation_id:
            records = records.where(Message.conversation_id == conversation_id)
        if start:
            records = records.where(Message.sent_at >= start)
        if end:
            records = records.where(Message.sent_at <= end)
        best: dict[str, dict[str, Any]] = {}
        keyword_best: dict[str, dict[str, Any]] = {}
        count = 0
        for result in session.scalars(records):
            for chunk in result.details["chunks"]:
                count += 1
                if count > 10_000:
                    raise ApiError(409, "POSTGRES_REQUIRED", "大规模语义检索需要PostgreSQL部署")
                values = chunk["vector"]
                length = math.sqrt(sum(v * v for v in values))
                if len(values) != 512 or not math.isfinite(length) or length <= 0:
                    raise ValueError("INVALID_EMBEDDING_NORM")
                similarity = sum(x * y for x, y in zip(vector, values, strict=True)) / length
                hit = {
                    "message_id": result.message_id,
                    "result_id": result.id,
                    "source_span": chunk["text"],
                    "start": chunk["start"],
                    "end": chunk["end"],
                    "similarity": similarity,
                }
                if (
                    result.message_id not in best
                    or similarity > best[result.message_id]["similarity"]
                ):
                    best[result.message_id] = hit
                if (
                    mode == "hybrid"
                    and all(
                        term in re.sub(r"\s+", "", processing.folded(chunk["text"]))
                        for term in terms
                    )
                    and (
                        result.message_id not in keyword_best
                        or similarity > keyword_best[result.message_id]["similarity"]
                    )
                ):
                    keyword_best[result.message_id] = {**hit, "channel": "keyword"}
        hits = sorted(best.values(), key=lambda row: (-row["similarity"], row["message_id"]))[
            :limit
        ]
        hits.extend(sorted(keyword_best.values(), key=lambda row: -row["similarity"])[:limit])
    if mode == "hybrid":
        return fuse(hits, limit)
    return hits


def fuse(hits: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Reciprocal rank fusion of independent scoped keyword and cosine candidate lists."""
    combined: dict[str, dict[str, Any]] = {}
    for channel in ("semantic", "keyword"):
        rows = sorted(
            (h for h in hits if h.get("channel", "semantic") == channel),
            key=lambda h: (-h["similarity"], h["message_id"]),
        )
        for rank, hit in enumerate(rows, 1):
            previous = combined.get(hit["message_id"])
            if previous is None:
                previous = {**hit, "rank_score": 0.0, "matched_by": []}
            elif channel == "keyword":
                previous = {**previous, **hit}
            previous["rank_score"] += 1 / (60 + rank)
            previous["matched_by"].append(channel)
            combined[hit["message_id"]] = previous
    return sorted(combined.values(), key=lambda h: (-h["rank_score"], h["message_id"]))[:limit]
