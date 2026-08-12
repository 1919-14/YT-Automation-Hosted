"""
tts.py — turns a script's narration into a single audio file using
Edge-TTS (free, local, no API key).

Concatenates hook -> scenes -> ending -> cta into one continuous
narration track (natural pacing, no awkward gaps), and returns the
plain-text script used so downstream captioning can be checked
against it.
"""

import asyncio
import edge_tts

# A natural-sounding narrator voice. Full list: `edge-tts --list-voices`
DEFAULT_VOICE = "en-US-GuyNeural"

# Small pause inserted between segments so the narration doesn't feel
# rushed at scene boundaries. Edge-TTS doesn't support SSML breaks
# directly through this simple API, so we use punctuation-based pacing
# instead (a paragraph break reads as a natural pause).
SEGMENT_JOINER = "\n\n"


def build_narration_text(script):
    """Assembles the full spoken narration in order, with segment
    boundaries preserved as a list for later timestamp alignment.
    Order: hook -> intro (orientation) -> scenes -> ending -> cta."""
    hook = script["hook_line"].strip()

    # Add dramatic 1-second pause markers before & after intro_line
    if script.get("intro_line"):
        if not hook.endswith("..."):
            hook += " ..."
        intro = script["intro_line"].strip()
        if not intro.endswith("..."):
            intro += " ..."
        segments = [hook, intro]
    else:
        segments = [hook]

    for scene in script.get("scenes", []):
        segments.append(scene["narration"])
    segments.append(script["ending_line"])
    segments.append(script["cta"])

    full_text = SEGMENT_JOINER.join(segments)
    return full_text, segments


async def _synthesize(text, output_path, voice=DEFAULT_VOICE, rate="+0%"):
    for attempt in range(1, 4):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(str(output_path))
            if output_path.exists() and output_path.stat().st_size > 0:
                return
        except Exception as e:
            print(f"[tts] Synthesis attempt {attempt} failed ({e}). Retrying in 2s...")
            await asyncio.sleep(2)
    raise RuntimeError(f"Edge-TTS failed to synthesize audio after 3 attempts.")



def generate_audio(script, output_path, voice=DEFAULT_VOICE, rate="+0%"):
    """
    script: parsed script dict (from script_generator.generate_script)
    output_path: where to save the .mp3
    Returns (output_path, segments) — segments is the ordered list of
    narration chunks, needed later to map whisper timestamps back to
    scenes for visual sync.
    """
    full_text, segments = build_narration_text(script)
    asyncio.run(_synthesize(full_text, output_path, voice=voice, rate=rate))
    return output_path, segments


if __name__ == "__main__":
    # smoke test with a fake script
    fake_script = {
        "hook_line": "You should never have opened that door.",
        "scenes": [
            {"narration": "The letter was signed by someone who died forty years ago.", "visual_prompt": "old letter"},
        ],
        "ending_line": "The whispers stopped. But the door was open.",
        "cta": "Subscribe for part two.",
    }
    from pathlib import Path
    out = Path(__file__).parent.parent / "assets" / "audio" / "test.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    path, segs = generate_audio(fake_script, out)
    print(f"Saved to {path}")
    print(f"Segments: {segs}")
