"""
script_generator.py — turns a decision_engine decision into an actual
structured script (hook, scenes, ending, CTA).

For series continuations, the prompt is grounded ONLY in extracted
canon facts / characters / unresolved threads / last summary — never
raw past scripts. This is the hallucination guard: the model reasons
over compact structured facts instead of re-deriving continuity from
prose it has to re-interpret each time.
"""

import re

from . import llm_client
from .categories import get_category_config


from spellchecker import SpellChecker

_spell = SpellChecker()


def _try_split_fused_word(word):
    """Given a word not found in the dictionary, try splitting it at
    every position into two parts and see if both halves are real
    dictionary words. Returns the spaced version if a clean split is
    found, else returns the original word unchanged.
    Only attempts this for words long enough that a glitch is likely
    (short words are usually just uncommon terms, not fusions)."""
    if len(word) < 8:
        return word
    lower = word.lower()
    for i in range(3, len(lower) - 2):
        left, right = lower[:i], lower[i:]
        if left in _spell and right in _spell:
            # preserve original casing pattern roughly by just returning
            # lowercase split — narration casing doesn't matter for TTS
            return f"{left} {right}"
    return word


def _fix_missing_spaces(text):
    """Repairs missing-space glitches some models produce inside long
    JSON string values. Two passes:
    1. Regex: lowercase->uppercase boundary (e.g. 'hasPerfectly' -> 'has Perfectly')
    2. Dictionary: any remaining unknown long word gets tried against
       the spellchecker dictionary for a clean two-word split
       (e.g. 'ripplesradiate' -> 'ripples radiate')."""
    if not isinstance(text, str):
        return text

    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)

    words = text.split(" ")
    fixed_words = []
    for w in words:
        # strip leading/trailing punctuation for the dictionary check
        core = re.sub(r'^[^a-zA-Z]+|[^a-zA-Z]+$', '', w)
        if core and core.lower() not in _spell and len(core) >= 8:
            split = _try_split_fused_word(core)
            if split != core:
                w = w.replace(core, split)
        fixed_words.append(w)
    return " ".join(fixed_words)


def _flag_suspicious_words(text, max_len=11):
    """Final safety net: after the fix pass, flag any remaining unknown
    long words for manual review (a genuine glitch the splitter couldn't
    resolve, or an unusual proper noun/term — either way worth a glance
    before this goes to TTS)."""
    words = re.findall(r'[a-zA-Z]+', text)
    return [w for w in words if len(w) > max_len and w.lower() not in _spell]


def _fix_script_spacing(script):
    """Applies _fix_missing_spaces to every string field in a script dict."""
    for key in ("title", "hook_line", "intro_line", "ending_line", "cta", "youtube_description"):
        if key in script:
            script[key] = _fix_missing_spaces(script[key])
    for scene in script.get("scenes", []):
        if "narration" in scene:
            scene["narration"] = _fix_missing_spaces(scene["narration"])
        if "visual_prompt" in scene:
            scene["visual_prompt"] = _fix_missing_spaces(scene["visual_prompt"])
    if "tags" in script:
        script["tags"] = [_fix_missing_spaces(t) for t in script["tags"]]
    return script


# Channel name injected into every script intro
CHANNEL_NAME = "Night Loom"

SCRIPT_SCHEMA_INSTRUCTIONS = f"""Write every string value in normal, fully spaced prose — double-check that no words have been run together before outputting. This matters: text will be read aloud by a voice engine, so missing spaces will be audible as errors.

IMPORTANT: "hook_line" is the very first sentence spoken in the video, spoken ONCE. The narration inside "scenes" continues directly AFTER the hook — do NOT repeat the hook_line text (or a close paraphrase of it) as part of the first scene's narration. The first scene should pick up where the hook leaves off, not restate it.

CHANNEL BRANDING: The "intro_line" field MUST include the channel name "{CHANNEL_NAME}" naturally and conversationally. Good examples: "Welcome to {CHANNEL_NAME}, where tonight's mystery begins." / "Here at {CHANNEL_NAME}, we dig into the stories nobody talks about." / "You're watching {CHANNEL_NAME} — and this one kept me up all night." Vary the phrasing each time — never repeat the same formula twice.

Respond with ONLY valid JSON matching this exact schema, no markdown fences, no explanation outside the JSON:

{{
  "title": "YouTube video title, under 100 chars, no clickbait beyond what the story earns",
  "hook_line": "the first spoken line — must grab attention in the first 3 seconds, a bold statement or question, NOT an explanation of the video",
  "intro_line": "ONE short spoken sentence right after the hook, MUST naturally mention the channel name '{CHANNEL_NAME}' (e.g. 'Welcome to {CHANNEL_NAME}...' / 'Here on {CHANNEL_NAME}...' / 'You're watching {CHANNEL_NAME}...'). Natural spoken tone, not a formal announcement.",
  "scenes": [
    {{"narration": "spoken text for this scene/segment", "visual_prompt": "short description of what should be shown visually during this line"}}
  ],
  "ending_line": "the final spoken line before the CTA — should land emotionally or satisfyingly",
  "cta": "a short call-to-action line, spoken, natural, not salesy",
  "youtube_description": "2-3 sentence description for the YouTube upload, includes a soft CTA to subscribe",
  "tags": ["5-8 relevant youtube tags as short strings"]
}}

For compilation format, "scenes" holds one entry per segment/fact/mini-story, each with its own micro-hook baked into the narration.
For continuous format, "scenes" holds the narrative beats in order (setup, rising tension/development, climax, resolution)."""


def _build_new_content_prompt(category, format_, cat_config, is_short):
    length_note = (
        "This is a SHORT video: 45-75 seconds total spoken narration. Keep scenes to 3-6 tight beats."
        if is_short else
        "This is a LONG-FORM video: approximately 15 minutes of spoken narration (roughly 2000-2400 words total across all scenes)."
    )

    structure_note = (
        "Structure: a single continuous story with rising tension across scenes — setup, development, climax, resolution."
        if cat_config["long_form_structure"] == "continuous" or is_short else
        "Structure: a compilation of 8-12 distinct short segments (facts/stories/points), each self-contained with its own micro-hook, loosely tied by theme."
    )

    return f"""You are a professional YouTube storyteller scriptwriter for a channel that covers many categories under one narrator persona.

Category: {category}
Tone for this category: {cat_config['tone']}
Hook style: {cat_config['hook_style']}
CTA style: {cat_config['cta_style']}
{length_note}
{structure_note}

Write a complete, original, compelling script. Avoid cliche phrasing.
The hook must work in the first 3 seconds even for a distracted viewer.
The ending should feel earned, not abrupt.

For "intro_line": this is a standalone video (not part of a series), so keep it very brief — one natural sentence that signals the type of story coming (e.g. "this is a true mystery story" / "here's what changed everything for me") without sounding like a formal announcement. It should not repeat the hook's content.

{SCRIPT_SCHEMA_INSTRUCTIONS}"""


def _build_continuation_prompt(series, cat_config, is_short, conclude=False):
    action_note = (
        "This episode must RESOLVE the unresolved threads listed below and bring the series to a satisfying conclusion. Do not introduce new unresolved threads."
        if conclude else
        "This episode should ADVANCE the story — deepen at least one unresolved thread, and it's fine to introduce at most one new small thread, but do not contradict any canon fact below."
    )

    length_note = (
        "This is a SHORT episode: 45-75 seconds of spoken narration."
        if is_short else
        "This is a LONG-FORM episode: approximately 15 minutes of spoken narration (roughly 2000-2400 words)."
    )

    return f"""You are a professional YouTube storyteller scriptwriter continuing an ongoing series.

Series: "{series['series_name']}" (category: {series['category']})
This is part {series['current_part'] + 1}.
Tone for this category: {cat_config['tone']}

--- STORY BIBLE (treat as absolute canon — do not contradict any of this) ---
Canon facts:
{chr(10).join('- ' + f for f in series['canon_facts']) or '(none yet)'}

Characters:
{series['characters'] or '(none established yet)'}

Unresolved threads:
{chr(10).join('- ' + t for t in series['unresolved_threads']) or '(none)'}

Summary of the most recent episode:
{series['last_episode_summary'] or '(this is the first episode)'}
--- END STORY BIBLE ---

{action_note}
{length_note}

For "intro_line": this IS a series continuation. Explicitly welcome back returning viewers and name the series and part number naturally (e.g. "Welcome back to The Hollow House, part {series['current_part'] + 1}" or a more natural phrasing in your own voice) — do not skip this, it's how viewers know they're watching a continuation. Keep it to one sentence, then let the hook's re-orientation (if any) and the story continue.

Open the hook itself with something that also briefly re-orients returning viewers to where the story left off (without a clunky "previously on" recap — weave it in naturally, working together with the intro_line).

{SCRIPT_SCHEMA_INSTRUCTIONS}"""


def _dedupe_hook_from_first_scene(script):
    """Safety net for the case where the model repeats hook_line as (or
    inside) the first scene's narration despite the prompt instruction.
    If scene 1's narration starts with text nearly identical to the hook,
    strip that portion out so it isn't spoken twice in a row."""
    scenes = script.get("scenes", [])
    hook = script.get("hook_line", "").strip()
    if not scenes or not hook:
        return script

    first_narration = scenes[0].get("narration", "").strip()
    hook_norm = _fix_missing_spaces(hook).lower().rstrip(".!?")
    first_norm = first_narration.lower()

    if first_norm.startswith(hook_norm):
        remainder = first_narration[len(hook):].strip()
        if remainder:
            scenes[0]["narration"] = remainder
        else:
            # the entire first scene WAS just the hook — drop it rather
            # than leave an empty narration line
            scenes.pop(0)
        script["scenes"] = scenes
        print("[script_generator] Detected and removed hook_line duplicated as scene 1 narration.")

    return script


def generate_script(decision, series=None, is_short=True):
    """
    decision: output of decision_engine.decide_next_video()
    series: full series dict (from memory.get_series) if action involves a series, else None
    is_short: True for short-form, False for long-form
    Returns the parsed script JSON dict.
    """
    action = decision["action"]

    if action == "new_content":
        category = decision["category"]
        cat_config = get_category_config(category)
        prompt = _build_new_content_prompt(category, decision.get("format"), cat_config, is_short)

    elif action == "continue_series":
        if series is None:
            raise ValueError("series dict required for continue_series")
        cat_config = get_category_config(series["category"])
        prompt = _build_continuation_prompt(series, cat_config, is_short, conclude=False)

    elif action == "conclude_series":
        if series is None:
            raise ValueError("series dict required for conclude_series")
        cat_config = get_category_config(series["category"])
        prompt = _build_continuation_prompt(series, cat_config, is_short, conclude=True)

    else:
        raise ValueError(f"Unknown decision action: {action}")

    script = llm_client.chat_json(
        [{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    script = _dedupe_hook_from_first_scene(script)
    script = _fix_script_spacing(script)

    # Flag (don't silently fix) any remaining suspicious fused words so
    # you can catch them before they reach TTS.
    all_text = " ".join(
        [script.get("hook_line", ""), script.get("ending_line", "")]
        + [s.get("narration", "") for s in script.get("scenes", [])]
    )
    suspicious = _flag_suspicious_words(all_text)
    if suspicious:
        print(f"[script_generator] WARNING: possible missing-space glitches: {suspicious}")

    return script


if __name__ == "__main__":
    # smoke test: standalone facts short
    fake_decision = {"action": "new_content", "series_id": None, "category": "facts"}
    script = generate_script(fake_decision, is_short=True)
    import json
    print(json.dumps(script, indent=2))
