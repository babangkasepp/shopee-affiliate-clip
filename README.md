# 🎬 shopee-affiliate-clip

Turn a single **product photo** into a vertical **9:16 cinematic promo clip** — with optional
AI **voice-over** and an auto-synthesized **backsound that ducks under the voice** — ready to
upload to **Facebook, Reels and YouTube Shorts**.

Built for faceless affiliate content: the **real product stays 100% unchanged**, only the
scene, motion and audio are generated around it.

```
product.png  ─▶  [prep]  ─▶  [animate]  ─▶  [concat]  ─▶  [audio]  ─▶  final.mp4
              reframe to    chained i2v     join shots    VO + ducked
              9:16 scene    (Kling)                       backsound
```

---

## ✨ Features

- **2 styles** — `cinematic` (interior scenes for wall art / decor) and `handheld` (POV hand holding small gadgets).
- **Multi-shot stitching** — generates several short shots and chains the last frame of each into the next for smooth 10–15s+ videos (single image-to-video models cap at ~5s).
- **Voice-over** via ElevenLabs (multilingual — great for Indonesian).
- **Backsound without a music API** — a warm maj7 pad + optional beat/arp is synthesized with numpy/scipy, then side-chain compressed so it automatically ducks under the voice.
- **Resumable** — each stage writes a `*.progress.json`; rerun from any stage with `--from`.
- **No system ffmpeg needed** — uses the binary bundled by `imageio-ffmpeg`.

---

## 🚀 Quick start

```bash
git clone https://github.com/<you>/shopee-affiliate-clip.git
cd shopee-affiliate-clip

# 1. install (uv recommended, or plain pip)
uv venv && uv pip install -e .        # or: pip install -e .

# 2. add your API keys
cp .env.example .env                  # then edit .env

# 3. drop your product photo in examples/product.png and run
affclip --config examples/config.cinematic.json
#   (or)  python -m affclip.pipeline --config examples/config.cinematic.json
```

The finished video lands at the `out` path from your config (e.g. `out/tulip_final.mp4`).

---

## 🔑 API keys (`.env`)

| Variable | Where | Used for |
|----------|-------|----------|
| `ELEVENLABS_API_KEY` | https://elevenlabs.io | voice-over |
| `FAL_KEY` | https://fal.ai | image reframe + image-to-video |

Only need TTS? You can leave `FAL_KEY` out and supply your own pre-made shots.
Don't want a voice-over? Set `"vo_text": ""` and you only need `FAL_KEY`.

---

## ⚙️ Config reference

```jsonc
{
  "product_image": "examples/product.png",   // your product photo
  "scene_prompt":  "cozy bedroom at night…",  // "" to skip reframing (use photo as-is / handheld)
  "shots": [                                  // one entry per ~5s shot
    {"prompt": "slow push-in toward the clock, LED glow pulsing", "duration": 5},
    {"prompt": "glide across the clock face, fairy lights twinkle", "duration": 5},
    {"prompt": "slow pull-back revealing the cozy room", "duration": 5}
  ],
  "aspect_ratio": "9:16",
  "vo_text": "Kamarmu butuh ini! …",          // "" = no voice-over
  "voice": "bella",                            // bella | rachel | antoni
  "voice_id": null,                            // or paste any ElevenLabs voice ID
  "backsound": true,
  "energy": "viral",                           // viral = pad+beat+arp, calm = pad only
  "out": "out/final.mp4",
  "workdir": "out/work",

  "image_model": "fal-ai/nano-banana/edit",                 // optional override
  "video_model": "fal-ai/kling-video/v2.1/pro/image-to-video"
}
```

> **Model IDs change.** The defaults point at Gemini Flash image-edit and Kling Pro on fal.ai.
> If fal updates a version, just set `image_model` / `video_model` to the current slug from
> the [fal.ai model gallery](https://fal.ai/models).

See `examples/config.cinematic.json` and `examples/config.handheld.json`.

---

## 🧱 Architecture

| Module | Responsibility | External deps |
|--------|----------------|---------------|
| `affclip/media.py` | backsound synth, frame extraction, concat, VO+backsound mux | **none** (ffmpeg/numpy/scipy only) — fully deterministic & offline |
| `affclip/providers.py` | ElevenLabs TTS, fal.ai image edit + image-to-video | network APIs |
| `affclip/pipeline.py` | stage orchestration, resume logic, 9:16 padding | — |

The `media.py` engine (the part that makes the audio/ducking and stitching work) is
self-contained and was validated independently of any external API.

---

## ✍️ Voice-over formula

Hook (pain/desire) → benefit → price → **urgency CTA**. ~30 words ≈ 15s. Example (ID):

> *"Kamarmu butuh ini! Jam dinding bunga tulip dengan lampu LED, bikin suasana malam makin
> aesthetic dan cozy. Cuma tiga puluh empat ribuan! Klik link sekarang, keburu kehabisan!"*

## 📝 Caption template (Facebook / Reels)

```
<1-line hook>
✅ <benefit 1>
✅ <benefit 2>
✅ <benefit 3>
Harga cuma Rp__ (dari Rp__) 🔥
Klik link di bio/komen 👇
#jamdinding #dekorrumah #hiasandinding #shopeefinds #racunshopee #homedecor …
```

---

## 💸 Cost & time (rough)

A 15s clip with VO + backsound ≈ **3 image-to-video shots + 1 image edit + 1 TTS call**,
typically a few US$ and ~5–7 minutes depending on the providers. Test with a single 5s shot first.

## 🛠️ Tips

- Crop brand banners/watermarks off the product photo first — they distort during animation.
- Always include *"product stays exactly the same, no distortion"* in shot prompts (the pipeline appends this automatically).
- If a run fails mid-way, fix the config and resume: `affclip --config cfg.json --from animate`.

## 📄 License

MIT — see [LICENSE](LICENSE).
