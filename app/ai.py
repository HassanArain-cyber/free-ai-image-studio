"""Optional real Diffusers inference on an external NVIDIA CUDA GPU (no fake outputs)."""
import gc
import os

from PIL import Image

from .filters import preserve_unmasked

MODEL_TEXT = os.getenv("IMAGE_MODEL_TEXT", "stabilityai/stable-diffusion-xl-base-1.0")
MODEL_EDIT = os.getenv("IMAGE_MODEL_EDIT", "diffusers/stable-diffusion-xl-1.0-inpainting-0.1")


def require_gpu():
    if os.getenv("AI_ENABLED", "0") != "1":
        raise RuntimeError("AI engine is disabled. Enable it only on a supported NVIDIA CUDA GPU.")
    try:
        import torch
        from diffusers import AutoPipelineForText2Image, AutoPipelineForImage2Image, AutoPipelineForInpainting
    except ImportError as exc:
        raise RuntimeError("GPU libraries missing. Install requirements-ai.txt and CUDA PyTorch.") from exc
    if not torch.cuda.is_available():
        raise RuntimeError("No CUDA GPU detected. Shared Intel graphics memory cannot run this pipeline.")
    return torch, (AutoPipelineForText2Image, AutoPipelineForImage2Image, AutoPipelineForInpainting)


def compatible_size(image: Image.Image):
    """Keep GPU workloads bounded while retaining the original for strict compositing."""
    width, height = image.size
    factor = min(1.0, 1024 / max(width, height))
    return max(256, round(width * factor / 8) * 8), max(256, round(height * factor / 8) * 8)


def run(mode, prompt, negative, seed, steps, strength, original=None, mask=None, width=768, height=768):
    torch, kinds = require_gpu()
    pipe = None
    try:
        model = MODEL_EDIT if mode == "edit" else MODEL_TEXT
        cls = {"generate": kinds[0], "pose": kinds[1], "edit": kinds[2]}[mode]
        opts = {"torch_dtype": torch.float16, "use_safetensors": True}
        if mode == "edit":
            opts["variant"] = "fp16"
        pipe = cls.from_pretrained(model, **opts)
        pipe.enable_model_cpu_offload()
        if hasattr(pipe, "enable_vae_tiling"):
            pipe.enable_vae_tiling()
        if hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
        params = dict(
            prompt=prompt, negative_prompt=negative, num_inference_steps=steps,
            guidance_scale=7.0, generator=torch.Generator("cpu").manual_seed(seed),
        )
        if mode == "generate":
            params.update(width=width, height=height)
        else:
            if original is None:
                raise ValueError("Reference image is required.")
            size = compatible_size(original)
            params["image"] = original.convert("RGB").resize(size, Image.Resampling.LANCZOS)
            params["strength"] = strength
            if mode == "edit":
                if mask is None:
                    raise ValueError("Edit mask is required.")
                params["mask_image"] = mask_binary_for_model(mask, size)
                params["prompt"] = prompt + ", natural lighting, match the original image style and surroundings"
        output = pipe(**params).images[0].convert("RGB")
        # Only edit-selected pixels are replaced. The original remains byte-exact elsewhere.
        if mode == "edit":
            return preserve_unmasked(original, output, mask)
        return output
    finally:
        del pipe
        gc.collect()
        torch.cuda.empty_cache()


def mask_binary_for_model(mask: Image.Image, size):
    from .filters import mask_binary
    return mask_binary(mask, size)
