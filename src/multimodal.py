from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava")
LOCAL_WHISPER_MODEL = os.getenv("LOCAL_WHISPER_MODEL", "base")


def extract_image_text(file_path: str) -> str:
    """
    Extract business-relevant text from image files.

    Model routing:
    - OCR is best for scans, labels, certificates, and document photos.
    - A vision-language model is best for visual context and mixed image/text.
    """
    sections = []

    ocr_text = extract_image_with_ocr(file_path)
    if ocr_text.strip():
        sections.append(f"[OCR_TEXT]\n{ocr_text.strip()}")

    vlm_text = describe_image_with_ollama(file_path)
    if vlm_text.strip():
        sections.append(f"[VISION_LANGUAGE_MODEL_DESCRIPTION]\n{vlm_text.strip()}")

    if not sections:
        return (
            f"[IMAGE_EXTRACTION_UNAVAILABLE: {Path(file_path).name}] "
            "Install Tesseract/pytesseract for OCR or run an Ollama vision model "
            "such as llava for image understanding."
        )

    return "\n\n".join(sections)


def extract_image_with_ocr(file_path: str) -> str:
    """
    OCR path for scans, labels, certificates, and other text-heavy images.

    Supported local backends:
    - pytesseract + Pillow, if installed.
    - tesseract CLI, if available on PATH.
    """
    try:
        from PIL import Image
        import pytesseract

        return pytesseract.image_to_string(Image.open(file_path))
    except Exception:
        pass

    if shutil.which("tesseract"):
        try:
            result = subprocess.run(
                ["tesseract", file_path, "stdout", "--psm", "6"],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    return ""


def describe_image_with_ollama(file_path: str) -> str:
    """
    Vision-language path for images that require visual understanding.

    Default model is llava. Pull it with:
        ollama pull llava
    """
    image_path = Path(file_path)
    if not image_path.exists():
        return ""

    prompt = """
You are extracting supply-chain compliance information from an image.
Describe only business-relevant facts visible in the image.

Focus on:
- shipment IDs, SKUs, ports, carriers, dates, document titles
- country of origin labels or certificates
- customs, CBP, tariff, hazmat, TSCA, UFLPA, or forced labor indicators
- packaging labels, dangerous goods marks, lithium battery marks, UN numbers
- missing, blurred, inconsistent, or unreadable fields

Return concise plain text, not JSON.
""".strip()

    payload = {
        "model": OLLAMA_VISION_MODEL,
        "prompt": prompt,
        "images": [base64.b64encode(image_path.read_bytes()).decode("ascii")],
        "stream": False,
        "options": {
            "temperature": 0.1,
        },
    }

    request = Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError):
        return ""

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""

    return data.get("response", "").strip()


def transcribe_audio(file_path: str) -> str:
    """
    Convert audio to text for downstream RAG.

    Local backend priority:
    1. faster-whisper Python package
    2. openai-whisper Python package / whisper CLI
    3. whisper.cpp CLI if available as whisper-cpp or main
    """
    transcript = _transcribe_with_faster_whisper(file_path)
    if transcript:
        return transcript

    transcript = _transcribe_with_openai_whisper(file_path)
    if transcript:
        return transcript

    transcript = _transcribe_with_whisper_cli(file_path)
    if transcript:
        return transcript

    return (
        f"[AUDIO_TRANSCRIPTION_UNAVAILABLE: {Path(file_path).name}] "
        "Install faster-whisper, openai-whisper, or whisper.cpp to transcribe "
        "broker calls, voicemail, and carrier audio updates before RAG analysis."
    )


def _transcribe_with_faster_whisper(file_path: str) -> str:
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return ""

    try:
        model = WhisperModel(LOCAL_WHISPER_MODEL, device="auto", compute_type="auto")
        segments, _info = model.transcribe(file_path, beam_size=1)
        return " ".join(segment.text.strip() for segment in segments).strip()
    except Exception:
        return ""


def _transcribe_with_openai_whisper(file_path: str) -> str:
    try:
        import whisper
    except Exception:
        return ""

    try:
        model = whisper.load_model(LOCAL_WHISPER_MODEL)
        result: dict[str, Any] = model.transcribe(file_path)
        return str(result.get("text", "")).strip()
    except Exception:
        return ""


def _transcribe_with_whisper_cli(file_path: str) -> str:
    whisper_cmd = shutil.which("whisper")
    if whisper_cmd:
        try:
            result = subprocess.run(
                [whisper_cmd, file_path, "--model", LOCAL_WHISPER_MODEL, "--output_format", "txt", "--output_dir", "/tmp"],
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    whisper_cpp = shutil.which("whisper-cpp") or shutil.which("main")
    if whisper_cpp:
        return (
            f"[WHISPER_CPP_AVAILABLE: {Path(file_path).name}] "
            "Configure the whisper.cpp model path before transcription."
        )

    return ""
