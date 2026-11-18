"""Local, versioned derivations. No source bytes or normalized message bodies are rewritten."""

import asyncio
import csv
import fcntl
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import sys
import tempfile
import unicodedata
import warnings
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session
from wdh_domain.models import Attachment, ProcessingPolicy
from wdh_storage.cas import ContentStore

from wdh_api.config import Settings

KINDS = ("ocr", "asr", "embedding", "llm")
IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
AUDIO_MIMES = {"audio/wav", "audio/ogg", "audio/flac", "audio/mpeg"}


class ModelBusy(RuntimeError):
    pass


@contextmanager
def model_slot(directory: Path, kind: str) -> Any:
    """Coordinate CPU/RAM-heavy LLMs across API and worker processes sharing storage."""
    if kind != "llm":
        yield
        return
    descriptor = os.open(directory / "llm.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ModelBusy("LOCAL_MODEL_BUSY") from exc
        yield
    finally:
        os.close(descriptor)


def ocr_directory(settings: Settings) -> Path:
    private = settings.data_root / "models/tesseract"
    if settings.ocr_data_dir == Path("/usr/share/tesseract-ocr/5/tessdata") and private.is_dir():
        return private
    return settings.ocr_data_dir


def folded(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value)


def enabled(session: Session, settings: Settings, workspace: str, kind: str) -> bool:
    policy = session.scalar(
        select(ProcessingPolicy).where(ProcessingPolicy.workspace_id == workspace)
    )
    if policy and kind in policy.enabled:
        return policy.enabled[kind]
    return bool(
        getattr(settings, "enable_" + ("embeddings" if kind == "embedding" else kind), False)
    )


async def _execute(arguments: list[str], directory: Path | None, timeout: int) -> bytes:
    """Fixed argv, no shell; bounded output/time and a minimal child environment."""
    process = await asyncio.create_subprocess_exec(
        *arguments,
        cwd=directory,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "OMP_THREAD_LIMIT": "2",
            "LD_LIBRARY_PATH": str(Path(arguments[0]).resolve().parent),
        },
        start_new_session=True,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def read(stream: asyncio.StreamReader | None, maximum: int) -> bytes:
        if stream is None:
            raise ValueError("PROVIDER_STREAM_UNAVAILABLE")
        data = bytearray()
        while chunk := await stream.read(65536):
            data.extend(chunk)
            if len(data) > maximum:
                raise ValueError("PROVIDER_OUTPUT_LIMIT")
        return bytes(data)

    tasks = [
        asyncio.create_task(read(process.stdout, 4_194_304)),
        asyncio.create_task(read(process.stderr, 65536)),
    ]
    try:
        output, _ = await asyncio.wait_for(asyncio.gather(*tasks), timeout)
        await asyncio.wait_for(process.wait(), 5)
        if process.returncode:
            raise ValueError("PROVIDER_INPUT_REJECTED")
        return output
    except TimeoutError as exc:
        raise ValueError("PROVIDER_TIMEOUT") from exc
    finally:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def execute(arguments: list[str], directory: Path | None = None, timeout: int = 5) -> bytes:
    return asyncio.run(_execute(arguments, directory, timeout))


@lru_cache(maxsize=256)
def asset_sha(path: str, size: int, modified: int, inode: int) -> str:
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def file_sha(path: Path) -> str:
    stat = path.stat()
    return asset_sha(str(path.absolute()), stat.st_size, stat.st_mtime_ns, stat.st_ino)


@lru_cache(maxsize=4)
def engine_version(binary: str) -> str:
    lines = execute([binary, "--version"]).decode("utf-8", "replace").splitlines()
    return lines[0][:80] if lines else "native/" + file_sha(Path(binary))[:16]


def capability(settings: Settings, kind: str) -> dict[str, Any]:
    if kind in {"embedding", "llm"}:
        return gguf_capability(settings, kind)
    if kind == "asr":
        return asr_capability(settings)
    if kind != "ocr":
        raise ValueError("UNSUPPORTED_PROCESSOR")
    binary = shutil.which("tesseract")
    languages = settings.ocr_languages.split("+")
    models = [ocr_directory(settings) / (language + ".traineddata") for language in languages]
    if not binary:
        return {"available": False, "reason": "ENGINE_NOT_INSTALLED", "provider_version": ""}
    if not all(model.is_file() and not model.is_symlink() for model in models):
        return {"available": False, "reason": "MODEL_NOT_INSTALLED", "provider_version": ""}
    try:
        digest = hashlib.sha256("".join(file_sha(model) for model in models).encode()).hexdigest()
        version = engine_version(binary).replace("tesseract ", "tesseract/")
    except (OSError, ValueError):
        return {"available": False, "reason": "ENGINE_UNAVAILABLE", "provider_version": ""}
    return {
        "available": True,
        "reason": None,
        "provider_version": f"{version}/models:{digest[:16]}/v1",
        "languages": languages,
    }


def ocr(
    settings: Settings, store: ContentStore, attachment: Attachment
) -> tuple[str, dict[str, Any]]:
    if attachment.availability != "available" or not attachment.sha256:
        raise ValueError("ATTACHMENT_MISSING")
    if (attachment.byte_size or 0) > settings.processing_max_bytes:
        raise ValueError("PROCESSING_SIZE_LIMIT")
    if attachment.mime_type not in IMAGE_MIMES:
        raise ValueError("UNSUPPORTED_IMAGE_FORMAT")
    binary = shutil.which("tesseract")
    if not binary or not capability(settings, "ocr")["available"]:
        raise ValueError("PROVIDER_UNAVAILABLE")
    directory = settings.data_root / "processing-tmp"
    ContentStore._directory(directory.absolute())
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        target = Path(temporary) / "image.png"
        try:
            with store.open(attachment.sha256) as source, warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(source) as image:
                    width, height = image.size
                    if width * height > settings.processing_max_pixels:
                        raise ValueError("IMAGE_PIXEL_LIMIT")
                    if getattr(image, "n_frames", 1) != 1:
                        raise ValueError("ANIMATED_IMAGE_UNSUPPORTED")
                    image.convert("RGB").save(target, "PNG")
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            raise ValueError("INVALID_IMAGE") from exc
        output = execute(
            [
                binary,
                str(target),
                "stdout",
                "--tessdata-dir",
                str(ocr_directory(settings)),
                "-l",
                settings.ocr_languages,
                "--psm",
                "6",
                "-c",
                "tessedit_create_tsv=1",
                "-c",
                "tessedit_create_txt=0",
            ],
            Path(temporary),
            settings.processing_timeout_seconds,
        )
    words: list[dict[str, Any]] = []
    lines: dict[str, list[str]] = {}
    reader = csv.DictReader(io.StringIO(output.decode("utf-8")), delimiter="\t")
    if not reader.fieldnames or "level" not in reader.fieldnames:
        raise ValueError("INVALID_OCR_RESPONSE")
    for row in reader:
        if row["level"] != "5" or not row.get("text", "").strip():
            continue
        text = row["text"].strip()
        bbox = [int(row[key]) for key in ("left", "top", "width", "height")]
        if min(bbox) < 0 or bbox[0] + bbox[2] > width or bbox[1] + bbox[3] > height:
            raise ValueError("INVALID_OCR_COORDINATES")
        confidence = float(row["conf"])
        if not 0 <= confidence <= 100:
            raise ValueError("INVALID_OCR_CONFIDENCE")
        words.append({"text": text, "bbox": bbox, "confidence_raw": confidence})
        line = ":".join(row[key] for key in ("page_num", "block_num", "par_num", "line_num"))
        lines.setdefault(line, []).append(text)
    text = "\n".join(" ".join(words) for words in lines.values())
    if len(text) > 100_000:
        raise ValueError("PROVIDER_OUTPUT_LIMIT")
    return text, {
        "words": words,
        "width": width,
        "height": height,
        "coordinate_space": "decoded-original-pixels",
        "languages": settings.ocr_languages,
        "confidence_note": "Algorithm score; not a guarantee of factual accuracy.",
    }


def asr_directory(settings: Settings) -> Path:
    return settings.asr_model_dir or settings.data_root / "models" / "asr"


def asr_capability(settings: Settings) -> dict[str, Any]:
    from wdh_api.models import catalog

    if not importlib.util.find_spec("sherpa_onnx") or not importlib.util.find_spec("soundfile"):
        return {"available": False, "reason": "ENGINE_NOT_INSTALLED", "provider_version": ""}
    root = asr_directory(settings)
    paths = [
        root / name
        for name in ("tiny-encoder.int8.onnx", "tiny-decoder.int8.onnx", "tiny-tokens.txt")
    ]
    if not all(path.is_file() and not path.is_symlink() for path in paths):
        return {"available": False, "reason": "MODEL_NOT_INSTALLED", "provider_version": ""}
    expected = {item["name"]: item["sha256"] for item in catalog()["asr"]["files"]}
    if any(file_sha(path) != expected[path.name] for path in paths):
        return {"available": False, "reason": "MODEL_HASH_MISMATCH", "provider_version": ""}
    digest = hashlib.sha256("".join(file_sha(path) for path in paths).encode()).hexdigest()
    version = importlib.metadata.version("sherpa-onnx")
    return {
        "available": True,
        "reason": None,
        "provider_version": (
            f"sherpa-whisper/{version}/models:{digest[:16]}/lang:{settings.asr_language}/v1"
        ),
        "languages": ["zh", "en", "auto"],
    }


def asr(
    settings: Settings, store: ContentStore, attachment: Attachment
) -> tuple[str, dict[str, Any]]:
    if not attachment.sha256 or attachment.availability != "available":
        raise ValueError("ATTACHMENT_MISSING")
    if attachment.mime_type not in AUDIO_MIMES:
        raise ValueError("UNSUPPORTED_AUDIO_CODEC")
    if (attachment.byte_size or 0) > settings.processing_max_bytes:
        raise ValueError("PROCESSING_SIZE_LIMIT")
    if not asr_capability(settings)["available"]:
        raise ValueError("PROVIDER_UNAVAILABLE")
    # Verify source integrity before allowing the isolated model process to open it read-only.
    with store.open(attachment.sha256):
        pass
    directory = settings.data_root / "processing-tmp"
    ContentStore._directory(directory.absolute())
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        request = Path(temporary) / "request.json"
        request.write_text(
            json.dumps(
                {
                    "source": str(store._path(attachment.sha256)),
                    "model_directory": str(asr_directory(settings).resolve()),
                    "language": settings.asr_language,
                    "max_seconds": settings.asr_max_seconds,
                }
            )
        )
        output = execute(
            [sys.executable, "-m", "wdh_api.local_inference", "asr", str(request)],
            Path(temporary),
            settings.processing_timeout_seconds,
        )
    result = json.loads(output)
    if result.get("error"):
        raise ValueError(result["error"])
    if not isinstance(result.get("text"), str) or not isinstance(result.get("details"), dict):
        raise ValueError("INVALID_ASR_RESPONSE")
    return result["text"], result["details"]


def server_path(settings: Settings) -> Path:
    if settings.local_model_server:
        return settings.local_model_server
    embedded = Path("/opt/wdh-runtime/runtime/llama-server")
    return embedded if embedded.is_file() else settings.data_root / "models/runtime/llama-server"


def gguf_file(settings: Settings, kind: str) -> Path:
    from wdh_api.models import catalog

    configured = settings.embedding_model_file if kind == "embedding" else settings.llm_model_file
    return configured or settings.data_root / "models" / kind / catalog()[kind]["files"][0]["name"]


def gguf_capability(settings: Settings, kind: str) -> dict[str, Any]:
    from wdh_api.models import catalog

    binary, model = server_path(settings), gguf_file(settings, kind)
    if not binary.is_file() or not importlib.util.find_spec("httpx"):
        return {"available": False, "reason": "ENGINE_NOT_INSTALLED", "provider_version": ""}
    if not model.is_file():
        return {"available": False, "reason": "MODEL_NOT_INSTALLED", "provider_version": ""}
    digest = file_sha(model)
    if digest != catalog()[kind]["files"][0]["sha256"]:
        return {"available": False, "reason": "MODEL_HASH_MISMATCH", "provider_version": ""}
    runtime_files = [binary, *sorted(binary.parent.glob("*.so*"))]
    engine = hashlib.sha256(
        "".join(file_sha(path) for path in runtime_files if path.is_file()).encode()
    ).hexdigest()[:16]
    version = f"gguf-cpu/{engine}/{kind}/{digest[:16]}/v1"
    if kind == "llm":
        version += f"/tokens:{settings.llm_max_tokens}"
    return {
        "available": True,
        "reason": None,
        "provider_version": version,
        "model": catalog()[kind]["version"],
    }


def native_request(settings: Settings, kind: str, data: dict[str, Any]) -> dict[str, Any]:
    if not gguf_capability(settings, kind)["available"]:
        raise ValueError("PROVIDER_UNAVAILABLE")
    directory = settings.data_root / "processing-tmp"
    ContentStore._directory(directory.absolute())
    with model_slot(directory, kind), tempfile.TemporaryDirectory(dir=directory) as temporary:
        request = Path(temporary) / "request.json"
        request.write_text(
            json.dumps(
                {
                    **data,
                    "server": str(server_path(settings).absolute()),
                    "model": str(gguf_file(settings, kind).absolute()),
                },
                ensure_ascii=False,
            )
        )
        output = execute(
            [sys.executable, "-m", "wdh_api.local_inference", kind, str(request)],
            Path(temporary),
            settings.processing_timeout_seconds,
        )
    result: dict[str, Any] = json.loads(output)
    if result.get("error"):
        raise ValueError(result["error"])
    return result
