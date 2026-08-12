"""
sdxl_generator.py — generates background images for each shot using
SDXL-Turbo via the Hugging Face diffusers library.

Loaded lazily (first call triggers model download ~6 GB one-time).
Designed to run on the local RTX 4050 with float16 precision.

Usage:
    from scripts import sdxl_generator
    paths = sdxl_generator.generate_shots(shots, video_id=5, format="short")
"""

from pathlib import Path

from . import config

_pipeline = None  # lazy global


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def _get_pipeline():
    """Lazy-load SDXL-Turbo. Only imports diffusers/torch on first call."""
    global _pipeline
    if _pipeline is None:
        import torch
        from diffusers import AutoPipelineForText2Image

        # Workaround: disable cuDNN to avoid 'Could not load symbol
        # cudnnGetLibConfig' crash on PyTorch 2.5.1+cu121 / cuDNN 9.1.
        # SDXL-Turbo inference doesn't benefit meaningfully from cuDNN.
        torch.backends.cudnn.enabled = False

        import warnings
        warnings.filterwarnings("ignore", category=FutureWarning, module="diffusers")
        warnings.filterwarnings("ignore", category=UserWarning, module="diffusers")

        model_id = "stabilityai/sdxl-turbo"
        use_cuda = torch.cuda.is_available()
        device = "cuda" if use_cuda else "cpu"
        dtype = torch.float16 if use_cuda else torch.float32

        print(f"[sdxl] Loading model {model_id} on {device.upper()}...")
        kwargs = {"torch_dtype": dtype}
        if use_cuda:
            kwargs["variant"] = "fp16"

        _pipeline = AutoPipelineForText2Image.from_pretrained(
            model_id,
            **kwargs,
        )
        if use_cuda:
            # Enable sequential CPU offloading + VAE tiling to drop VRAM footprint to ~1.8 GB (30% of RTX 4050 capacity)
            _pipeline.enable_sequential_cpu_offload()
            _pipeline.vae.enable_tiling()
            _pipeline.vae.enable_slicing()
            _pipeline.enable_attention_slicing()
            try:
                _pipeline.enable_xformers_memory_efficient_attention()
            except Exception:
                pass
        else:
            _pipeline = _pipeline.to(device)
        print(f"[sdxl] Model ready on {device.upper()} (Sequential CPU offloading & VAE tiling enabled).")
    return _pipeline


def unload_model():
    """Unloads SDXL pipeline from GPU VRAM and clears CUDA memory."""
    global _pipeline
    if _pipeline is not None:
        del _pipeline
        _pipeline = None
        config.cleanup_vram()
        print("[sdxl] SDXL model unloaded from VRAM.")


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

# 9:16 portrait for Shorts, 16:9 landscape for long-form
_RESOLUTIONS = {
    "short":    (576, 1024),   # width × height (divisible by 64)
    "long":     (1024, 576),
}


def _get_resolution(format_):
    return _RESOLUTIONS.get(format_, _RESOLUTIONS["short"])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_shot(prompt, out_path, format_="short", num_inference_steps=4):
    """
    Generate a single image for one shot (skips if out_path already exists).
    """
    out_path = Path(out_path)
    if out_path.exists() and out_path.stat().st_size > 0:
        print(f"[sdxl] Image already exists, reusing: {out_path.name}")
        return out_path

    pipe = _get_pipeline()
    w, h = _get_resolution(format_)

    image = pipe(
        prompt=prompt,
        num_inference_steps=num_inference_steps,
        guidance_scale=0.0,   # SDXL-Turbo requires guidance_scale=0
        width=w,
        height=h,
    ).images[0]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(out_path), format="PNG")
    return out_path


def generate_shots(shots, video_id, format_="short", num_inference_steps=4):
    """
    Generate background images for a list of shots from the visual plan with progress bar.
    """
    from tqdm import tqdm

    out_dir = config.ASSETS_DIR / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    import gc
    import torch

    results = []
    print(f"[sdxl] Generating {len(shots)} background visual shot(s) ...")
    for shot in tqdm(shots, desc="[sdxl] Generating shots"):
        filename = f"video_{video_id}_bg_{shot['shot_id']}.png"
        out_path = out_dir / filename
        generate_shot(shot["bg_prompt"], out_path, format_=format_,
                      num_inference_steps=num_inference_steps)
        results.append({
            "shot_id": shot["shot_id"],
            "asset_path": str(out_path),
            "asset_type": "image",
        })
        # Flush VRAM allocator cache after each shot to prevent memory accumulation across shots
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

    # Unload model to free GPU VRAM after generating shots
    unload_model()
    return results


if __name__ == "__main__":
    # Quick single-image test
    test_prompt = "surreal glowing clock face dissolving in dark space, cinematic, dramatic lighting"
    out = config.ASSETS_DIR / "images" / "sdxl_test.png"
    print(f"[sdxl] Generating test image → {out}")
    generate_shot(test_prompt, out, format_="short", num_inference_steps=4)
    print("[sdxl] Done.")
