"""External generation providers (image edit, image-to-video, text-to-speech).

Standalone implementations using public APIs so the pipeline runs on your own
machine with your own keys. Model IDs are configurable (they change often) — set
them in config.json or via env. See README for current recommended IDs.

Required environment variables (.env):
  ELEVENLABS_API_KEY   -> https://elevenlabs.io  (text-to-speech)
  FAL_KEY              -> https://fal.ai          (image edit + image-to-video)
"""
from __future__ import annotations
import os
import requests

# --------------------------------------------------------------------------- #
# Text to speech (ElevenLabs)
# --------------------------------------------------------------------------- #
# A few stock voice IDs; override with cfg["voice_id"].
ELEVEN_VOICES = {
    "bella": "EXAVITQu4vr4xnSDxMaL",
    "rachel": "21m00Tcm4TlvDq8ikWAM",
    "antoni": "ErXwobaYiN019PkySvjV",
}


def tts(text: str, out_mp3: str, voice: str = "bella", voice_id: str | None = None,
        model_id: str = "eleven_multilingual_v2") -> str:
    """Generate a voice-over MP3 with ElevenLabs."""
    key = os.environ["ELEVENLABS_API_KEY"]
    vid = voice_id or ELEVEN_VOICES.get(voice, ELEVEN_VOICES["bella"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    r = requests.post(
        url,
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        params={"output_format": "mp3_44100_128"},
        json={
            "text": text,
            "model_id": model_id,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.3},
        },
        timeout=120,
    )
    r.raise_for_status()
    with open(out_mp3, "wb") as f:
        f.write(r.content)
    return out_mp3


# --------------------------------------------------------------------------- #
# fal.ai (image edit + image-to-video)
# --------------------------------------------------------------------------- #
def _fal():
    import fal_client  # lazy import so TTS-only runs don't need it
    if "FAL_KEY" not in os.environ:
        raise RuntimeError("FAL_KEY not set")
    return fal_client


def edit_image(image_path: str, prompt: str, out_path: str,
               model_id: str = "fal-ai/nano-banana/edit") -> str:
    """Edit/reframe a product photo into a scene while keeping the product identical.

    Default model is Gemini Flash image edit ('nano-banana') on fal.ai. Override via
    cfg["image_model"].
    """
    fal_client = _fal()
    img_url = fal_client.upload_file(image_path)
    result = fal_client.subscribe(
        model_id,
        arguments={"prompt": prompt, "image_urls": [img_url], "num_images": 1},
    )
    images = result.get("images") or result.get("image")
    url = images[0]["url"] if isinstance(images, list) else images["url"]
    _download(url, out_path)
    return out_path


def image_to_video(image_path: str, prompt: str, out_path: str,
                   duration: int = 5, aspect_ratio: str = "9:16",
                   model_id: str = "fal-ai/kling-video/v2.1/pro/image-to-video") -> str:
    """Animate a still image into a short clip (Kling on fal.ai). Override via cfg['video_model']."""
    fal_client = _fal()
    img_url = fal_client.upload_file(image_path)
    result = fal_client.subscribe(
        model_id,
        arguments={
            "prompt": prompt,
            "image_url": img_url,
            "duration": str(duration),
            "aspect_ratio": aspect_ratio,
        },
    )
    video = result.get("video") or {}
    url = video.get("url") if isinstance(video, dict) else video
    _download(url, out_path)
    return out_path


def _download(url: str, out_path: str) -> str:
    r = requests.get(url, stream=True, timeout=300)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 16):
            f.write(chunk)
    return out_path
