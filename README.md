# ImageForge — Private AI Image Studio

A responsive image editor and optional AI image generator for laptop and Android browsers. **Current MVP:** working CPU editing; real generative AI requires a separate supported NVIDIA CUDA GPU. No app-added watermark or subscription.

## Working features

- Upload PNG/JPEG/WebP photos up to 12 MB and 16 megapixels.
- Brush-painted selection, unpaint, brush size and clear.
- **Brush tint:** changes only painted strokes while preserving shadows. This cannot redesign a dress or automatically select garments.
- **Fill:** replace selected pixels with a solid color.
- **Erase:** make selected pixels transparent (not background reconstruction).
- **Strict selective editing:** all pixels outside the mask are preserved.
- Save results to private SQLite-backed library; preview/download PNG and delete history.
- Responsive UI, private Codespaces preview and optional access key.
- Optional AI model adapters for SDXL generation, inpainting and exploratory image-to-image.

**Not currently guaranteed or implemented:** 100% prompt accuracy, exact clothing redesign, perfect face preservation inside the mask, automatic pose-reference control, complete object reconstruction, free always-available GPU hosting. CPU recolor is not a generative clothing replacement. The pose option is *experimental img2img*, not an exact skeleton pose system.

## Run using GitHub Codespaces (no Windows PowerShell)

1. Open the [development branch](https://github.com/HassanArain-cyber/free-ai-image-studio/tree/studio/image-editor-mvp).
2. Choose **Code → Codespaces → Create codespace on studio/image-editor-mvp**.
3. Python dependencies install automatically. The server starts on port **8000**. If it doesn't open, visit **Ports → Open in Browser**.
4. Select **Recolor**, upload a picture, **paint the clothing area**, choose a color and click **Generate result**.
5. In **Your library**, click Preview or Download. The original outside the painted selection stays unchanged.

Codespaces has limited free usage; it is not an unlimited or always-on GPU service. Keep the forwarded port **private**. Do not expose it publicly.

If the preview shows HTTP 502, use the Codespaces terminal:

~~~bash
bash .devcontainer/start.sh
~~~

## Local setup

Python 3.11+ is required:

~~~bash
python -m venv .venv
# Activate the environment, then:
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~

Open http://127.0.0.1:8000. Local CPU image editing does not need an NVIDIA GPU.

## Why brush tint gives patches

The brush selection is literal, not semantic clothing detection. Only painted pixels are changed, so broad strokes produce visible patches. This is not a generative outfit editor. For true clothing replacements, use an image inpainting model on a suitable CUDA GPU; the current Codespaces workspace is CPU-only.

## Optional AI generator

**Requires a separate capable NVIDIA CUDA GPU host.** Install CUDA-compatible PyTorch following its official installation instructions, install the packages in requirements-ai.txt, then launch the server with AI_ENABLED=1 in the environment. First use may download many gigabytes of weights. These models have **not been validated on a real GPU** in this MVP, and their availability and licenses must be checked before use.

Default models:
- Text to image: stabilityai/stable-diffusion-xl-base-1.0
- Masked inpainting: diffusers/stable-diffusion-xl-1.0-inpainting-0.1
- Pose text prompt: SDXL image-to-image; this does **not** accurately follow a reference pose.

AI inpainting preserves unselected pixels via strict composition. Within the painted area, AI may alter face/body details or ignore some instructions. For dependable unchanged facial features, keep the face outside the selection. Pose changes are particularly difficult and may require different models.

Automatic Clothes/Background mask buttons are optional. They need Torch and the Hugging Face segmentation model mattmdjaga/segformer_b2_clothes and may consume additional memory. Without them, the manual brush works.

## Test

~~~bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app
node --check web/app.js
~~~

GitHub Actions runs unit/API checks without downloading generative models. The actual AI path needs separate GPU testing.

## Code map

~~~text
app/main.py          Secure API routes and job queue
app/filters.py       Pixel-preserving CPU editor and masks
app/ai.py            Optional SDXL model integrations
app/segmentation.py  Optional AI segmentation suggestion
app/store.py         SQLite history
web/                 Mobile/desktop interface and brush
tests/               Backend and mask tests
data/                Private images and database (ignored by Git)
~~~

## Privacy

Do not upload personal photos into GitHub or commit tokens. Images remain on the server hosting this app. APP_TOKEN is optional for local development; use an access key before exposing the backend on trusted LAN networks. Raw HTTP does not encrypt the access key, and this development server is not suitable for public hosting without proper HTTPS, authentication and abuse controls.
