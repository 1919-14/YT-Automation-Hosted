"""
captions.py — runs faster-whisper on generated narration audio to get
word-level timestamps, then maps those words back to which script
segment (hook/scene/ending/cta) they belong to.

This mapping is what lets the visuals stage know exactly when to
switch images/clips (sync to actual spoken timing, not estimated
TTS duration), and what lets the assembly stage burn in animated
per-word captions.
"""

import os
import sys
from pathlib import Path

# On Windows, pip-installed nvidia-cublas-cu12 / nvidia-cudnn-cu12 place their
# DLLs under site-packages\nvidia\<pkg>\bin — NOT on the default DLL search
# path. CTranslate2 (faster-whisper's backend) resolves cublas64_12.dll and
# cudnn64_9.dll at *import time*, so this patch must run before the import.
# We update both os.add_dll_directory AND os.environ["PATH"] because
# CTranslate2's internal loader checks PATH directly.
if sys.platform == "win32":
    import site
    _extra = []
    for sp in site.getsitepackages():
        nvidia_dir = Path(sp) / "nvidia"
        if nvidia_dir.is_dir():
            for pkg_dir in nvidia_dir.iterdir():
                bin_dir = pkg_dir / "bin"
                if bin_dir.is_dir():
                    os.add_dll_directory(str(bin_dir))
                    _extra.append(str(bin_dir))
    if _extra:
        os.environ["PATH"] = os.pathsep.join(_extra) + os.pathsep + os.environ.get("PATH", "")

from faster_whisper import WhisperModel

from . import config

_model = None
_device_in_use = None


def get_model(device="cuda"):
    global _model, _device_in_use
    if _model is None or _device_in_use != device:
        compute_type = "float16" if device == "cuda" else "int8"
        _model = WhisperModel(config.WHISPER_MODEL_SIZE, device=device, compute_type=compute_type)
        _device_in_use = device
    return _model


def unload_model():
    """Unloads Whisper model from memory."""
    global _model, _device_in_use
    if _model is not None:
        del _model
        _model = None
        _device_in_use = None
        config.cleanup_vram()
        print("[captions] Whisper model unloaded from memory.")


def transcribe_with_timestamps(audio_path, device=None):
    """Returns a flat list of {"word": str, "start": float, "end": float}
    across the whole audio file, in order.

    device: "cuda", "cpu", or None (auto). Defaults to CPU for now —
    Windows + faster-whisper's CUDA DLL discovery is a known pain point
    (pip-installed nvidia-cublas-cu12 doesn't always land on the DLL
    search path automatically). CPU is plenty fast for short-form audio;
    revisit GPU once the CUDA path issue is sorted, since it matters
    more for long-form (15 min) transcription."""
    device = device or config.WHISPER_DEVICE

    if device == "cuda":
        try:
            model = get_model(device="cuda")
            segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
            segments = list(segments)
        except Exception as e:
            print(f"[captions] CUDA transcription failed ({e}). Falling back to CPU.")
            model = get_model(device="cpu")
            segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
            segments = list(segments)
    else:
        model = get_model(device="cpu")
        segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
        segments = list(segments)

    words = []
    for segment in segments:
        for word in segment.words:
            words.append({
                "word": word.word.strip(),
                "start": word.start,
                "end": word.end,
            })
    return words


def _normalize(text):
    """Lowercase, strip punctuation, for fuzzy matching whisper's
    transcription against the original script text (whisper may
    transcribe punctuation/casing slightly differently)."""
    return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).split()


def map_words_to_segments(words, segments_text):
    """
    words: output of transcribe_with_timestamps() — flat list across
           the whole audio
    segments_text: the ordered list of narration strings from
                    tts.build_narration_text() (hook, scene1, scene2, ..., ending, cta)

    Returns a list matching segments_text, each entry:
    {"text": str, "start": float, "end": float, "words": [...]}

    Matching is done by walking through the flat whisper word list and
    consuming words to fill each segment's expected word count in order
    — reliable because narration is synthesized in this exact sequence,
    so word order is guaranteed even if whisper's exact transcription
    text differs slightly from the original.
    """
    result = []
    word_idx = 0
    total_expected = sum(len(_normalize(t)) for t in segments_text)

    if len(words) != total_expected:
        drift = len(words) - total_expected
        print(
            f"[captions] WARNING: whisper transcribed {len(words)} words, "
            f"script expected {total_expected} (drift: {drift:+d}). "
            f"Segment boundaries below may be slightly off — spot check "
            f"the last 1-2 segments especially, since drift accumulates."
        )

    for seg_text in segments_text:
        expected_word_count = len(_normalize(seg_text))
        seg_words = words[word_idx: word_idx + expected_word_count]
        word_idx += expected_word_count

        if not seg_words:
            result.append({"text": seg_text, "start": None, "end": None, "words": []})
            continue

        result.append({
            "text": seg_text,
            "start": seg_words[0]["start"],
            "end": seg_words[-1]["end"],
            "words": seg_words,
        })

    return result


if __name__ == "__main__":
    import sys
    audio_path = Path(__file__).parent.parent / "assets" / "audio" / "test.mp3"
    if not audio_path.exists():
        print(f"No test audio at {audio_path} — run tts.py first.")
        sys.exit(1)

    words = transcribe_with_timestamps(audio_path)
    print(f"Transcribed {len(words)} words.")
    for w in words[:10]:
        print(w)
