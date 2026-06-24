"""End-to-end orchestrator: product photo -> vertical promo clip (+ VO + backsound).

Stages (resumable via --from):
  prep     reframe/transform the product photo into a 9:16 scene (optional)
  animate  generate chained image-to-video shots
  concat   join shots into one silent video
  audio    add voice-over + ducked backsound (optional)

Usage:
  python -m affclip.pipeline --config config.json [--from prep|animate|concat|audio]
"""
from __future__ import annotations
import argparse
import json
import os
import traceback

from PIL import Image

from . import media, providers

STAGES = ["prep", "animate", "concat", "audio", "done"]


# --------------------------------------------------------------------------- #
def _log(progress_path: str, stage: str, msg: str, **extra):
    rec = {"stage": stage, "msg": msg, **extra}
    print(json.dumps(rec), flush=True)
    state = {}
    if os.path.exists(progress_path):
        try:
            state = json.load(open(progress_path))
        except Exception:
            state = {}
    state.setdefault("events", []).append(rec)
    state["last"] = rec
    json.dump(state, open(progress_path, "w"), indent=2)


def _workdir(cfg: dict) -> str:
    d = cfg.get("workdir") or os.path.dirname(cfg["out"]) or "."
    os.makedirs(d, exist_ok=True)
    return d


def _pad_to_vertical(src_png: str, out_png: str, tw: int = 1080, th: int = 1920) -> str:
    """Force an image to exact 9:16 via center-crop or edge-strip padding."""
    im = Image.open(src_png).convert("RGB")
    scale = tw / im.width
    rh = int(im.height * scale)
    im2 = im.resize((tw, rh), Image.LANCZOS)
    if rh >= th:
        top = (rh - th) // 2
        im2.crop((0, top, tw, top + th)).save(out_png)
    else:
        pad = (th - rh) // 2
        canvas = Image.new("RGB", (tw, th))
        canvas.paste(im2, (0, pad))
        canvas.paste(im2.crop((0, 0, tw, 1)).resize((tw, pad), Image.LANCZOS), (0, 0))
        canvas.paste(im2.crop((0, rh - 1, tw, rh)).resize((tw, th - pad - rh), Image.LANCZOS),
                     (0, pad + rh))
        canvas.save(out_png)
    return out_png


# --------------------------------------------------------------------------- #
def stage_prep(cfg: dict, wd: str, pp: str) -> str:
    img = cfg["product_image"]
    if not cfg.get("scene_prompt"):
        _log(pp, "prep", "no scene_prompt -> using product image as-is", start_image=img)
        return img
    prompt = (
        f"{cfg['scene_prompt']}. Keep the product from the reference image in frame. "
        "CRITICAL: keep the product 100% identical — same shape, colors, text, design and "
        "proportions. Only build the surrounding environment and lighting. Photorealistic, "
        "vertical 9:16 composition, cinematic, high detail."
    )
    raw = os.path.join(wd, "scene_raw.png")
    providers.edit_image(img, prompt, raw, model_id=cfg.get("image_model", "fal-ai/nano-banana/edit"))
    out_png = _pad_to_vertical(raw, os.path.join(wd, "scene.png"))
    _log(pp, "prep", "scene built", start_image=out_png)
    return out_png


def stage_animate(cfg: dict, wd: str, pp: str, start_image: str) -> list[str]:
    shots = cfg["shots"]
    ar = cfg.get("aspect_ratio", "9:16")
    vmodel = cfg.get("video_model", "fal-ai/kling-video/v2.1/pro/image-to-video")
    clips, cur = [], start_image
    for i, shot in enumerate(shots):
        prompt = shot["prompt"] + " Product stays exactly the same, no distortion or text changes."
        dur = int(shot.get("duration", 5))
        _log(pp, "animate", f"shot {i+1}/{len(shots)} generating", prompt=prompt[:80])
        raw = os.path.join(wd, f"shot{i+1}_raw.mp4")
        providers.image_to_video(cur, prompt, raw, duration=dur, aspect_ratio=ar, model_id=vmodel)
        clip = media.normalize_clip(raw, os.path.join(wd, f"clip{i+1}.mp4"))
        clips.append(clip)
        _log(pp, "animate", f"shot {i+1} done", clip=clip)
        if i < len(shots) - 1:
            cur = media.extract_last_frame(clip, os.path.join(wd, f"frame{i+1}.png"))
    return clips


def stage_concat(cfg: dict, wd: str, pp: str, clips: list[str]) -> str:
    silent = media.concat_clips(clips, os.path.join(wd, "video_silent.mp4"))
    _log(pp, "concat", "joined", silent=silent, dur=media.video_duration(silent))
    return silent


def stage_audio(cfg: dict, wd: str, pp: str, silent: str) -> str:
    out = cfg["out"]
    vo_wav = bg_wav = None
    if cfg.get("vo_text"):
        mp3 = providers.tts(cfg["vo_text"], os.path.join(wd, "vo.mp3"),
                            voice=cfg.get("voice", "bella"), voice_id=cfg.get("voice_id"))
        vo_wav = media.to_wav(mp3, os.path.join(wd, "vo.wav"))
        _log(pp, "audio", "VO generated")
    if cfg.get("backsound", True):
        vdur = media.video_duration(silent)
        bg_wav = media.make_backsound(vdur + 0.5, os.path.join(wd, "bg.wav"),
                                      energy=cfg.get("energy", "viral"))
    media.mux_audio(silent, out, vo_wav=vo_wav, bg_wav=bg_wav)
    _log(pp, "audio", "muxed", out=out, dur=media.video_duration(out))
    return out


# --------------------------------------------------------------------------- #
def run(cfg: dict, from_stage: str = "prep") -> None:
    wd = _workdir(cfg)
    pp = cfg["out"] + ".progress.json"
    if from_stage == "prep" and os.path.exists(pp):
        os.remove(pp)
    start = STAGES.index(from_stage)
    state = json.load(open(pp)) if os.path.exists(pp) else {}
    art = state.get("artifacts", {})
    try:
        if start <= 0:
            art["start_image"] = stage_prep(cfg, wd, pp)
        if start <= 1:
            art["clips"] = stage_animate(cfg, wd, pp, art["start_image"])
        if start <= 2:
            art["silent"] = stage_concat(cfg, wd, pp, art["clips"])
        if start <= 3:
            art["final"] = stage_audio(cfg, wd, pp, art["silent"])
        _log(pp, "done", "PIPELINE COMPLETE", out=cfg["out"])
    except Exception as e:
        _log(pp, "error", str(e), tb=traceback.format_exc()[-1200:])
        raise
    finally:
        st = json.load(open(pp))
        st["artifacts"] = art
        json.dump(st, open(pp, "w"), indent=2)


def main() -> None:
    ap = argparse.ArgumentParser(description="Shopee affiliate clip pipeline")
    ap.add_argument("--config", required=True)
    ap.add_argument("--from", dest="from_stage", default="prep", choices=STAGES[:-1])
    a = ap.parse_args()
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    run(json.load(open(a.config)), a.from_stage)


if __name__ == "__main__":
    main()
