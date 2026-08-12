"""
test_remote_gpu.py — Tests the Google Colab GPU Worker URL for SDXL image generation.
"""

import base64
import sys
import requests
from pathlib import Path

def test_gpu_worker(gpu_url: str):
    gpu_url = gpu_url.rstrip("/")
    headers = {"ngrok-skip-browser-warning": "true"}

    print(f"📡 Testing health endpoint at {gpu_url}/health ...")
    try:
        res = requests.get(f"{gpu_url}/health", headers=headers, timeout=15)
        print(f"✅ Health Status ({res.status_code}):", res.json())
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

    print("\n🎨 Requesting SDXL image generation from Colab GPU...")
    payload = {
        "prompts": ["surreal glowing clock face dissolving in dark space, cinematic, dramatic lighting"],
        "width": 576,
        "height": 1024,
        "num_inference_steps": 4
    }

    try:
        res = requests.post(f"{gpu_url}/generate_images", json=payload, headers=headers, timeout=120)
        print(f"Response Status Code: {res.status_code}")
        if res.status_code == 200:
            data = res.json()
            images = data.get("images", [])
            print(f"🎉 Success! Received {len(images)} generated image(s) from Colab T4 GPU!")
            out_dir = Path("output/tests")
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "colab_gpu_test.png"
            with open(out_file, "wb") as f:
                f.write(base64.b64decode(images[0]))
            print(f"🖼️ Saved test image to: {out_file.resolve()}")
            return True
        else:
            print("❌ Image generation failed:", res.text)
            return False
    except Exception as e:
        print(f"❌ Exception during generation request: {e}")
        return False

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://f8b5-34-126-189-20.ngrok-free.app"
    test_gpu_worker(url)
