"""Bounded child process for optional CPU models. It receives no database credentials."""

import argparse
import asyncio
import importlib
import json
import math
import secrets
import socket
from pathlib import Path
from typing import Any


def transcribe(request: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    sherpa_onnx = importlib.import_module("sherpa_onnx")
    sf = importlib.import_module("soundfile")

    root = Path(request["model_directory"])
    try:
        audio = sf.SoundFile(request["source"], mode="r")
    except (RuntimeError, OSError) as exc:
        raise ValueError("UNSUPPORTED_AUDIO_CODEC") from exc
    with audio:
        rate, channels = audio.samplerate, audio.channels
        duration = len(audio) / rate if rate else 0
        if audio.format not in {"WAV", "WAVEX", "FLAC", "OGG", "MP3"}:
            raise ValueError("UNSUPPORTED_AUDIO_CODEC")
        if not 8000 <= rate <= 96000 or not 1 <= channels <= 2:
            raise ValueError("UNSUPPORTED_AUDIO_PARAMETERS")
        if not 0 < duration <= request["max_seconds"]:
            raise ValueError("AUDIO_DURATION_LIMIT")
        recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=str(root / "tiny-encoder.int8.onnx"),
            decoder=str(root / "tiny-decoder.int8.onnx"),
            tokens=str(root / "tiny-tokens.txt"),
            language="" if request["language"] == "auto" else request["language"],
            num_threads=2,
            enable_segment_timestamps=True,
        )
        segments: list[dict[str, Any]] = []
        languages: set[str] = set()
        offset, clipped = 0.0, False
        while len(samples := audio.read(20 * rate, dtype="float32", always_2d=True)):
            samples = samples.mean(axis=1)
            if not np.isfinite(samples).all():
                raise ValueError("INVALID_AUDIO_SAMPLES")
            seconds = len(samples) / rate
            if np.sqrt(np.mean(samples**2)) < 0.0001:
                offset += seconds
                continue
            stream = recognizer.create_stream()
            stream.accept_waveform(rate, samples)
            recognizer.decode_stream(stream)
            result = stream.result
            if result.lang:
                languages.add(result.lang)
            texts = list(result.segment_texts)
            starts = list(result.segment_timestamps)
            durations = list(result.segment_durations)
            if result.text.strip() and not texts:
                # The whole submitted window is the only observed interval; no invented word timing.
                texts, starts, durations = [result.text], [0.0], [seconds]
            if len(texts) != len(starts) or len(texts) != len(durations):
                raise ValueError("INVALID_ASR_TIMESTAMPS")
            for text, start, length in zip(texts, starts, durations, strict=True):
                if not np.isfinite(start) or not np.isfinite(length) or start < 0 or length < 0:
                    raise ValueError("INVALID_ASR_TIMESTAMPS")
                end = min(seconds, start + length)
                clipped = clipped or start + length > seconds
                start = min(start, seconds)
                if text.strip() and end > start:
                    segments.append(
                        {
                            "start": round(offset + start, 3),
                            "end": round(offset + end, 3),
                            "text": text.strip(),
                        }
                    )
            offset += seconds
    text = "\n".join(segment["text"] for segment in segments)
    if len(text) > 100_000:
        raise ValueError("PROVIDER_OUTPUT_LIMIT")
    return {
        "text": text,
        "details": {
            "segments": segments,
            "duration_seconds": duration,
            "sample_rate": rate,
            "channels": channels,
            "languages": sorted(languages),
            "timestamp_granularity": "segment",
            "timestamps_clipped_to_audio": clipped,
            "uncertain": True,
            "confidence_note": "Machine transcription requires source audio review.",
        },
    }


async def gguf(request: dict[str, Any], kind: str) -> dict[str, Any]:
    import httpx

    binary = Path(request["server"])
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_urlsafe(32)
    arguments = [
        str(binary),
        "-m",
        request["model"],
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--alias",
        "wdh-local",
        "--api-key",
        token,
        "-t",
        "2",
        "-ngl",
        "0",
        "--no-webui",
        "--log-disable",
        "-np",
        "1",
    ]
    if kind == "embedding":
        arguments += ["--embedding", "--pooling", "cls", "-c", "512", "-b", "512", "-ub", "512"]
    else:
        arguments += ["-c", "4096", "-b", "256", "-ub", "256"]
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        env={
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LD_LIBRARY_PATH": str(binary.parent),
            "LANG": "C.UTF-8",
            "OMP_NUM_THREADS": "2",
        },
    )
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            trust_env=False,
            timeout=110,
            headers={"Authorization": "Bearer " + token},
        ) as client:
            for _ in range(200):
                if process.returncode is not None:
                    raise ValueError("LOCAL_ENGINE_UNAVAILABLE")
                try:
                    health = await client.get("/health", timeout=1)
                    if health.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise ValueError("LOCAL_MODEL_NOT_READY")
            if kind == "embedding":
                response = await client.post(
                    "/v1/embeddings",
                    json={
                        "model": "wdh-local",
                        "input": request["texts"],
                        "encoding_format": "float",
                        "truncate": False,
                    },
                )
                response.raise_for_status()
                records = sorted(response.json()["data"], key=lambda row: row["index"])
                if len(records) != len(request["texts"]):
                    raise ValueError("INVALID_EMBEDDING_COUNT")
                vectors = []
                for row in records:
                    vector = [float(x) for x in row["embedding"]]
                    if len(vector) != 512 or not all(math.isfinite(x) for x in vector):
                        raise ValueError("INVALID_EMBEDDING_DIMENSIONS")
                    length = math.sqrt(sum(x * x for x in vector))
                    if length <= 0:
                        raise ValueError("INVALID_EMBEDDING_NORM")
                    vectors.append([x / length for x in vector])
                return {"vectors": vectors}
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "wdh-local",
                    "messages": request["messages"],
                    "max_tokens": request["max_tokens"],
                    "temperature": 0,
                    "seed": 42,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "source_evidence",
                            "strict": True,
                            "schema": request["schema"],
                        },
                    },
                },
            )
            response.raise_for_status()
            return {"output": json.loads(response.json()["choices"][0]["message"]["content"])}
    except httpx.HTTPError as exc:
        raise ValueError("LOCAL_MODEL_REQUEST_FAILED") from exc
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 3)
            except TimeoutError:
                process.kill()
                await process.wait()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["asr", "embedding", "llm"])
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    try:
        if args.request.stat().st_size > 1_048_576:
            raise ValueError("PROCESSING_REQUEST_LIMIT")
        data = json.loads(args.request.read_text())
        result = transcribe(data) if args.kind == "asr" else asyncio.run(gguf(data, args.kind))
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        code = str(exc)
        if not code or len(code) > 80 or not all(c.isupper() or c == "_" for c in code):
            code = "LOCAL_MODEL_FAILED"
        result = {"error": code}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
