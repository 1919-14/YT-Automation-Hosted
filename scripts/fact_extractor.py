"""
fact_extractor.py — after a script is generated for a series episode,
extract structured facts from it to merge into series_state.

This is the other half of the hallucination guard: instead of feeding
raw scripts back into future prompts, we distill each episode down to
compact facts once, immediately after writing it, while the model
still has full context of what it just wrote.
"""

from . import llm_client


EXTRACTION_SCHEMA_INSTRUCTIONS = """Respond with ONLY valid JSON matching this schema, no markdown fences:

{
  "new_canon_facts": ["short factual statements established in this episode, e.g. 'The attic door is locked from the inside'"],
  "character_updates": {"character name": {"role": "...", "status": "alive/dead/missing/unknown/etc", "notes": "short note"}},
  "unresolved_threads": ["threads that remain open AFTER this episode — supersedes the previous list entirely, include carried-over ones still open plus any new ones"],
  "episode_summary": "2-3 sentence summary of what happened in this episode, for future reference"
}

Only include facts that are clearly established or stated in the script — do not infer beyond what's written."""


def extract_facts(script, is_conclusion=False):
    """
    script: the parsed script dict from script_generator.generate_script()
    is_conclusion: if True, expects unresolved_threads to come back empty
    Returns the parsed extraction JSON dict.
    """
    narration_text = "\n".join(scene["narration"] for scene in script.get("scenes", []))
    full_text = f"{script.get('hook_line', '')}\n{narration_text}\n{script.get('ending_line', '')}"

    conclusion_note = (
        "\nThis episode was written to CONCLUDE the series — unresolved_threads should come back empty unless something was clearly left open."
        if is_conclusion else ""
    )

    prompt = f"""Extract structured story facts from this episode script for a continuing series.

--- SCRIPT ---
{full_text}
--- END SCRIPT ---
{conclusion_note}

{EXTRACTION_SCHEMA_INSTRUCTIONS}"""

    return llm_client.chat_json([{"role": "user", "content": prompt}], temperature=0.3)


if __name__ == "__main__":
    fake_script = {
        "hook_line": "You should never have opened that door.",
        "scenes": [
            {"narration": "Mara found the letter tucked beneath the floorboard, addressed to no one.", "visual_prompt": "old letter under floorboard"},
            {"narration": "It was signed by someone who had died forty years ago in this very house.", "visual_prompt": "faded signature"},
        ],
        "ending_line": "The whispers stopped. But the front door was open, and she was sure she'd locked it.",
    }
    result = extract_facts(fake_script)
    import json
    print(json.dumps(result, indent=2))
