"""ImageForge API: validated uploads, one-worker jobs, and protected private files."""
import io
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageColor, ImageOps, UnidentifiedImageError

from . import ai, filters, segmentation, store

ROOT = Path(__file__).resolve().parent.parent
TOKEN = os.getenv("APP_TOKEN", "")
POOL = ThreadPoolExecutor(max_workers=1)
MAX_UPLOAD = 12 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000
store.initialize()

app = FastAPI(title="ImageForge", version="0.1.0")


def authorize(request: Request):
    if TOKEN and not secrets.compare_digest(request.headers.get("X-App-Key", ""), TOKEN):
        raise HTTPException(401, "Invalid studio access key")


def summary(row):
    return {key: value for key, value in row.items() if key != "output"}


def picture(raw, grayscale=False):
    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.verify()
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > 16_000_000:
                raise HTTPException(413, "Maximum image size is 16 megapixels.")
            source = ImageOps.exif_transpose(source)
            return source.convert("L" if grayscale else "RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Invalid or unsupported image.") from exc


async def read_upload(upload: UploadFile | None, *, grayscale=False):
    if upload is None:
        return None
    raw = await upload.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Image exceeds 12 MB.")
    return picture(raw, grayscale=grayscale)


def execute(job_id, mode, prompt, negative, seed, steps, strength, color, dims):
    store.update(job_id, "running")
    source = store.MEDIA / (job_id + "_source.png")
    selection = store.MEDIA / (job_id + "_selection.png")
    target = store.MEDIA / (job_id + ".png")
    try:
        image = Image.open(source).convert("RGB") if source.exists() else None
        mask = Image.open(selection).convert("L") if selection.exists() else None
        if mode in ("recolor", "fill", "erase"):
            result = getattr(filters, mode)(image, mask, color) if mode != "erase" else filters.erase(image, mask)
        else:
            result = ai.run(mode, prompt, negative, seed, steps, strength, image, mask, *dims)
        result.save(target, format="PNG", optimize=True)
        store.update(job_id, "ready", output=str(target))
    except Exception as exc:
        target.unlink(missing_ok=True)
        store.update(job_id, "failed", error=str(exc)[:700])
    finally:
        source.unlink(missing_ok=True)
        selection.unlink(missing_ok=True)


@app.get("/api/status")
def status():
    return {"ai_configured": os.getenv("AI_ENABLED", "0") == "1",
            "cpu_tools": ["recolor", "fill", "erase"],
            "ai_modes": ["generate", "edit", "pose"]}


@app.get("/api/jobs", dependencies=[Depends(authorize)])
def jobs():
    return [summary(job) for job in store.recent()]


@app.post("/api/mask", dependencies=[Depends(authorize)])
async def suggest_mask(target: str = Form(...), image: UploadFile = File(...)):
    source = await read_upload(image)
    try:
        output = segmentation.suggest_mask(source, target)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(503, str(exc)) from exc
    buffer = io.BytesIO()
    output.save(buffer, format="PNG")
    return Response(buffer.getvalue(), media_type="image/png")


@app.post("/api/jobs", status_code=202, dependencies=[Depends(authorize)])
async def submit(
    mode: str = Form(...), prompt: str = Form(""), negative: str = Form("blurry, distorted, low quality"),
    seed: int = Form(42), steps: int = Form(25), strength: float = Form(0.55),
    width: int = Form(768), height: int = Form(768), color: str = Form("#7067f6"),
    image: UploadFile | None = File(None), mask: UploadFile | None = File(None),
):
    valid = {"generate", "edit", "pose", "recolor", "fill", "erase"}
    if mode not in valid:
        raise HTTPException(422, "Unknown editing mode.")
    if len(prompt) > 3000 or len(negative) > 1500:
        raise HTTPException(422, "Prompt is too long.")
    if mode in ("generate", "edit", "pose") and not prompt.strip():
        raise HTTPException(422, "A prompt is required.")
    if mode in ("generate", "edit", "pose") and os.getenv("AI_ENABLED", "0") != "1":
        raise HTTPException(503, "AI model is not configured. CPU editing is available now; see README for GPU setup.")
    if not 1 <= steps <= 50 or not 0.1 <= strength <= 1.0:
        raise HTTPException(422, "Invalid sampling parameters.")
    if width % 8 or height % 8 or not 256 <= width <= 1024 or not 256 <= height <= 1024:
        raise HTTPException(422, "Dimensions must be 256–1024, divisible by 8.")
    if mode in ("recolor", "fill"):
        try:
            ImageColor.getrgb(color)
        except ValueError as exc:
            raise HTTPException(422, "Choose a valid color.") from exc
    source = await read_upload(image)
    selection = await read_upload(mask, grayscale=True)
    if mode == "generate" and (source is not None or selection is not None):
        raise HTTPException(422, "Text-to-image accepts no source or selection.")
    if mode != "generate" and source is None:
        raise HTTPException(422, "Upload the original image.")
    if mode in ("edit", "recolor", "fill", "erase") and selection is None:
        raise HTTPException(422, "Paint or automatically select an editing region.")
    if selection is not None and source is not None:
        if selection.getbbox() is None:
            raise HTTPException(422, "The editing selection is empty.")
        if selection.size != source.size:
            raise HTTPException(422, "Selection and original image sizes differ.")
    job_id = uuid4().hex
    if source is not None:
        source.save(store.MEDIA / (job_id + "_source.png"))
    if selection is not None:
        selection.save(store.MEDIA / (job_id + "_selection.png"))
    store.create(job_id, mode, prompt.strip())
    POOL.submit(execute, job_id, mode, prompt.strip(), negative, seed, steps, strength, color, (width, height))
    return {"id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}/image", dependencies=[Depends(authorize)])
def output(job_id: str):
    job = store.get(job_id)
    if not job or job["status"] != "ready" or not job["output"]:
        raise HTTPException(404, "Image not ready.")
    return FileResponse(job["output"], media_type="image/png", filename=f"imageforge-{job_id[:8]}.png",
                        headers={"Cache-Control": "private, no-store"})


@app.delete("/api/jobs/{job_id}", dependencies=[Depends(authorize)])
def delete(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Image not found.")
    if job["status"] in ("queued", "running"):
        raise HTTPException(409, "Cannot delete while processing.")
    if job["output"]:
        Path(job["output"]).unlink(missing_ok=True)
    store.delete(job_id)
    return {"deleted": True}


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="studio")
