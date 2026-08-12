"""
metadata_optimizer.py — uses LLM to generate high-CTR, algorithm-optimized
YouTube metadata (Title, SEO Description, Hashtags, Search Tags, Category ID).

Inputs:
  - Video script, category, series story bible context

Outputs:
  - JSON payload with title, description, tags, category_id, privacy_status
"""

import json
import sys
from pathlib import Path

from . import config, llm_client, memory

SYSTEM_PROMPT = """You are a top-tier YouTube Shorts algorithm expert & growth strategist.
Your task is to write metadata for a YouTube Short video that maximizes Click-Through-Rate (CTR), Audience Retention, and YouTube Search/Recommendation Indexing.

OUTPUT REQUIREMENTS (STRICT JSON ONLY):
{
  "title": "Short, punchy, high-curiosity title (UNDER 60 CHARACTERS). Include an emotional hook or mystery element.",
  "description": "Engaging 2-paragraph description. Paragraph 1 summarizes the mystery/story hook. Paragraph 2 gives a strong Call-To-Action ('Subscribe for Part 2 & drop your theory in the comments!'). End with 4 trending hashtags like #Shorts #Mystery #DarkStories #Viral.",
  "tags": ["12 to 15 targeted search tags as strings", "mystery stories", "scary short", ...],
  "category_id": "24"
}

CATEGORY ID MAPPING:
- 24 = Entertainment (default for stories/mystery)
- 27 = Education (facts/explainers)
- 1  = Film & Animation
- 28 = Science & Technology
"""


def generate_metadata(video_id: int) -> dict:
    """
    Generates AI-optimized YouTube metadata for video N.
    """
    with memory.get_conn() as conn:
        row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
        if not row:
            raise ValueError(f"Video {video_id} not found in DB.")

        video = dict(row)

    title_concept = video.get("title", f"Video {video_id}")
    category = video.get("category", "dark_stories")
    hook_line = video.get("hook_line", "")
    ending_line = video.get("ending_line", "")
    script_json = video.get("script_json")

    user_prompt = f"""VIDEO INFORMATION:
- Working Title: {title_concept}
- Category: {category}
- Hook Line: {hook_line}
- Ending Line: {ending_line}
- Full Script: {script_json if script_json else title_concept}

Generate the JSON YouTube metadata optimized for maximum algorithm reach and CTR."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    print(f"[metadata_optimizer] Requesting LLM YouTube metadata for video {video_id} ...")
    try:
        metadata = llm_client.chat_json(messages, temperature=0.7)
    except Exception as e:
        print(f"[metadata_optimizer] Failed to generate JSON response via LLM ({e}). Using fallback.")
        metadata = {
            "title": title_concept[:58],
            "description": f"{hook_line}\n\nSubscribe for more! #Shorts #{category.capitalize()}",
            "tags": [category, "shorts", "mystery", "viral"],
            "category_id": "24",
        }

    # Ensure required fields
    metadata["title"] = metadata.get("title", title_concept[:58])
    metadata["description"] = metadata.get("description", hook_line)
    metadata["tags"] = metadata.get("tags", ["shorts", "mystery"])
    metadata["category_id"] = str(metadata.get("category_id", "24"))

    print(f"[metadata_optimizer] Optimized Title: {metadata['title']}")
    print(f"[metadata_optimizer] Generated {len(metadata['tags'])} search tags & description.")

    return metadata


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LLM YouTube Metadata Optimizer")
    parser.add_argument("--video", type=int, default=1, help="Video ID")
    args = parser.parse_args()
    res = generate_metadata(args.video)
    print(json.dumps(res, indent=2))
