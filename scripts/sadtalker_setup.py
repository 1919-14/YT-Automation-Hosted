"""
sadtalker_setup.py — one-time download and setup helper for SadTalker.

SadTalker generates expressive talking-head videos from a single portrait
image + narration audio.  It produces natural head motion, eye blinks, and
facial expressions driven by the audio pitch/energy.

Download sources taken directly from SadTalker's own:
  models/sadtalker/scripts/download_models.sh

Call `ensure_sadtalker()` once before running avatar_generator.
"""

import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from . import config

# ── Paths ──────────────────────────────────────────────────────────────────────
SADTALKER_DIR   = config.PROJECT_ROOT / "models" / "sadtalker"
CHECKPOINTS_DIR = SADTALKER_DIR / "checkpoints"
GFPGAN_DIR      = SADTALKER_DIR / "gfpgan" / "weights"
BFM_DIR         = CHECKPOINTS_DIR / "BFM_Fitting"

SADTALKER_REPO  = "https://github.com/OpenTalker/SadTalker.git"
GH_RELEASE      = "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc"

# ── Checkpoint files from GitHub releases ─────────────────────────────────────
CHECKPOINTS = {
    # Main unified checkpoint files (new v0.0.2-rc format)
    "SadTalker_V0.0.2_256.safetensors": f"{GH_RELEASE}/SadTalker_V0.0.2_256.safetensors",
    "SadTalker_V0.0.2_512.safetensors": f"{GH_RELEASE}/SadTalker_V0.0.2_512.safetensors",
    "mapping_00109-model.pth.tar"      : f"{GH_RELEASE}/mapping_00109-model.pth.tar",
    "mapping_00229-model.pth.tar"      : f"{GH_RELEASE}/mapping_00229-model.pth.tar",
}

# BFM zip (contains all 9 fitting .mat files)
BFM_ZIP_URL  = "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2/BFM_Fitting.zip"
BFM_ZIP_DEST = CHECKPOINTS_DIR / "BFM_Fitting.zip"

# GFPGAN + facexlib weights
GFPGAN_WEIGHTS = {
    "GFPGANv1.4.pth": (
        "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth"
    ),
    "alignment_WFLW_4HG.pth": (
        "https://github.com/xinntao/facexlib/releases/download/v0.1.0/alignment_WFLW_4HG.pth"
    ),
    "detection_Resnet50_Final.pth": (
        "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth"
    ),
    "parsing_parsenet.pth": (
        "https://github.com/xinntao/facexlib/releases/download/v0.2.2/parsing_parsenet.pth"
    ),
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _run(cmd, cwd=None):
    print(f"[sadtalker_setup] $ {' '.join(str(c) for c in cmd)}")
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None)


def _download(url, dest, label):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"[sadtalker_setup] Already present: {dest.name}")
        return
    print(f"[sadtalker_setup] Downloading {label} ...")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 YTAutomation/1.0",
            "Accept"    : "*/*",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(
                        f"\r  {pct}%  ({downloaded // (1 << 20)} MB / {total // (1 << 20)} MB)",
                        end="", flush=True
                    )
        print()
        print(f"[sadtalker_setup] Saved: {dest.name}")
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed for {label}: {e}") from e


def _pip_install(*packages):
    _run([sys.executable, "-m", "pip", "install", *packages])


# ── Public API ─────────────────────────────────────────────────────────────────

def ensure_sadtalker():
    """
    Idempotent setup — safe to call multiple times.
    On first call (takes a few minutes to download ~1.5 GB):
      1. Installs Python dependencies (face-alignment, safetensors, gfpgan)
      2. Clones the SadTalker repo into models/sadtalker/
      3. Downloads main checkpoints from GitHub releases
      4. Downloads and extracts BFM_Fitting.zip
      5. Downloads GFPGAN + facexlib face enhancer weights
    """
    # 1. Python dependencies
    try:
        import face_alignment  # noqa
    except ImportError:
        print("[sadtalker_setup] Installing face-alignment ...")
        _pip_install("face-alignment")

    try:
        import safetensors  # noqa
    except ImportError:
        _pip_install("safetensors")

    try:
        import gfpgan  # noqa
    except ImportError:
        print("[sadtalker_setup] Installing gfpgan ...")
        _pip_install("gfpgan")

    # Install remaining SadTalker runtime deps in one shot
    _pip_install(
        "kornia==0.6.8", "resampy>=0.3.1", "pydub>=0.25.1",
        "joblib>=1.1.0", "av",
    )

    # 2. Clone repo
    if not (SADTALKER_DIR / "inference.py").exists():
        SADTALKER_DIR.mkdir(parents=True, exist_ok=True)
        print("[sadtalker_setup] Cloning SadTalker repo ...")
        _run(["git", "clone", SADTALKER_REPO, str(SADTALKER_DIR)])

    # 3. Main checkpoints
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    for fname, url in CHECKPOINTS.items():
        _download(url, CHECKPOINTS_DIR / fname, fname)

    # 4. BFM Fitting files (zipped)
    if not BFM_DIR.exists() or not any(BFM_DIR.iterdir()):
        _download(BFM_ZIP_URL, BFM_ZIP_DEST, "BFM_Fitting.zip")
        print("[sadtalker_setup] Extracting BFM_Fitting.zip ...")
        with zipfile.ZipFile(BFM_ZIP_DEST, "r") as z:
            z.extractall(CHECKPOINTS_DIR)
        BFM_ZIP_DEST.unlink(missing_ok=True)
        print("[sadtalker_setup] BFM Fitting files extracted.")

    # 5. GFPGAN + facexlib enhancer weights
    GFPGAN_DIR.mkdir(parents=True, exist_ok=True)
    for fname, url in GFPGAN_WEIGHTS.items():
        _download(url, GFPGAN_DIR / fname, fname)

    # 6. Patch preprocess.py for NumPy 2.0+ compatibility (VisibleDeprecationWarning and array float cast removed)
    prep_py = SADTALKER_DIR / "src" / "face3d" / "util" / "preprocess.py"
    if prep_py.exists():
        content = prep_py.read_text(encoding="utf-8")
        patched = content.replace("np.VisibleDeprecationWarning", "DeprecationWarning")
        patched = patched.replace(
            "float((t[0] - w0/2)*s)", "float(np.squeeze((t[0] - w0/2)*s))"
        ).replace(
            "float((h0/2 - t[1])*s)", "float(np.squeeze((h0/2 - t[1])*s))"
        ).replace(
            "trans_params = np.array([w0, h0, s, t[0], t[1]])",
            "trans_params = np.array([float(w0), float(h0), float(np.squeeze(s)), float(np.squeeze(t[0])), float(np.squeeze(t[1]))], dtype=np.float32)"
        )
        if patched != content:
            prep_py.write_text(patched, encoding="utf-8")
            print("[sadtalker_setup] Patched NumPy 2.0+ compatibility in face3d preprocess.py")

    prep_py2 = SADTALKER_DIR / "src" / "utils" / "preprocess.py"
    if prep_py2.exists():
        content2 = prep_py2.read_text(encoding="utf-8")
        patched2 = content2.replace(
            "[float(item) for item in np.hsplit(trans_params, 5)]",
            "[float(np.squeeze(item)) for item in np.hsplit(trans_params, 5)]"
        )
        if patched2 != content2:
            prep_py2.write_text(patched2, encoding="utf-8")
            print("[sadtalker_setup] Patched NumPy 2.0+ compatibility in utils preprocess.py")

    # 7. Patch basicsr degradations.py for torchvision functional_tensor removal
    try:
        import basicsr
        deg_py = Path(basicsr.__file__).parent / "data" / "degradations.py"
        if deg_py.exists():
            content = deg_py.read_text(encoding="utf-8")
            old_str = "from torchvision.transforms.functional_tensor import rgb_to_grayscale"
            new_str = "from torchvision.transforms.functional import rgb_to_grayscale"
            if old_str in content:
                content = content.replace(old_str, new_str)
                deg_py.write_text(content, encoding="utf-8")
                print("[sadtalker_setup] Patched basicsr for torchvision compatibility.")
    except Exception:
        pass

    # 8. Patch SadTalker inference.py for NumPy 2.0 polyfills (np.float, np.int, np.bool)
    inf_py = SADTALKER_DIR / "inference.py"
    if inf_py.exists():
        content = inf_py.read_text(encoding="utf-8")
        if "np.float = float" not in content:
            polyfill = (
                "import numpy as np\n"
                "if not hasattr(np, 'float'): np.float = float\n"
                "if not hasattr(np, 'int'): np.int = int\n"
                "if not hasattr(np, 'bool'): np.bool = bool\n"
                "if not hasattr(np, 'typeDict'): np.typeDict = np.sctypeDict\n\n"
            )
            inf_py.write_text(polyfill + content, encoding="utf-8")
            print("[sadtalker_setup] Patched NumPy 2.0 polyfills in inference.py")

    print("[sadtalker_setup] SadTalker ready.")
    return SADTALKER_DIR


if __name__ == "__main__":
    ensure_sadtalker()
