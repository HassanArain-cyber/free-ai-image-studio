"""Fast backend tests; no expensive model downloads or GPU required."""
import io
import os
import tempfile
import time

os.environ["IMAGE_STUDIO_DATA"] = tempfile.mkdtemp(prefix="imageforge-tests-")
os.environ["AI_ENABLED"] = "0"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402
from app import main  # noqa: E402

client = TestClient(main.app)


def png(image):
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


def test_health_and_no_fake_ai():
    assert client.get("/api/status").json()["ai_configured"] is False
    response = client.post("/api/jobs", data={"mode": "generate", "prompt": "hello"})
    assert response.status_code == 503
    assert client.get("/api/jobs").json() == []


def test_invalid_upload_and_bad_selection():
    response = client.post("/api/jobs", data={"mode": "erase"},
                           files={"image": ("bad.png", b"junk"), "mask": ("mask.png", b"junk")})
    assert response.status_code == 422
    original = png(Image.new("RGB", (32, 32), "red"))
    empty = png(Image.new("L", (32, 32), 0))
    response = client.post("/api/jobs", data={"mode": "erase"},
                           files={"image": ("a.png", original), "mask": ("m.png", empty)})
    assert response.status_code == 422


def test_quick_edit_preserves_unselected_pixels():
    image = Image.new("RGB", (32, 24), (225, 20, 30))
    mask = Image.new("L", image.size, 0)
    for x in range(10, 20):
        for y in range(5, 15):
            mask.putpixel((x, y), 255)
    response = client.post("/api/jobs", data={"mode": "fill", "color": "#123abc"},
                           files={"image": ("a.png", png(image)), "mask": ("m.png", png(mask))})
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        result = next(job for job in client.get("/api/jobs").json() if job["id"] == job_id)
        if result["status"] in ("ready", "failed"):
            break
        time.sleep(.03)
    assert result["status"] == "ready", result.get("error")
    edited = Image.open(io.BytesIO(client.get("/api/jobs/" + job_id + "/image").content))
    assert edited.getpixel((0, 0)) == image.getpixel((0, 0))
    assert edited.getpixel((12, 8)) == (18, 58, 188)


def test_auth(monkeypatch):
    monkeypatch.setattr(main, "TOKEN", "private-key")
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs", headers={"X-App-Key": "private-key"}).status_code == 200


def test_invalid_mode():
    assert client.post("/api/jobs", data={"mode": "unknown"}).status_code == 422


def test_large_upload():
    response = client.post("/api/jobs", data={"mode": "erase"},
                           files={"image": ("a.png", b"z" * (main.MAX_UPLOAD + 1))})
    assert response.status_code == 413
