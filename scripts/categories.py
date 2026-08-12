"""
categories.py — per-category configuration.

Central place to define how each content category should behave:
its narrative tone, whether long-form defaults to a continuous story
or a compilation, and hook/CTA style guidance for the prompt.

Add a new category by adding one entry here — nothing else needs
to change for the generator to pick it up.
"""

CATEGORIES = {
    "horror": {
        "long_form_structure": "continuous",
        "tone": "tense, atmospheric, builds dread slowly, unsettling imagery",
        "hook_style": "an unsettling statement or question that implies something is wrong",
        "cta_style": "invite viewers to share their own scary experience, subscribe for more",
        "series_friendly": True,
    },
    "mystery": {
        "long_form_structure": "continuous",
        "tone": "intriguing, withholds information deliberately, rewards attention to detail",
        "hook_style": "poses an unanswered question or strange fact up front",
        "cta_style": "ask viewers to guess the answer/twist in comments, subscribe for the reveal",
        "series_friendly": True,
    },
    "motivational": {
        "long_form_structure": "compilation",
        "tone": "sincere, direct, avoids cliche where possible, grounded in specifics not platitudes",
        "hook_style": "a bold claim or relatable pain point stated plainly",
        "cta_style": "clear single action step, subscribe for daily motivation",
        "series_friendly": False,
    },
    "facts": {
        "long_form_structure": "compilation",
        "tone": "curious, surprising, precise, avoids sounding like a listicle",
        "hook_style": "the single most surprising fact in the set, stated as a teaser",
        "cta_style": "ask which fact surprised them most, subscribe for more",
        "series_friendly": False,
    },
}

DEFAULT_CATEGORY_CONFIG = {
    "long_form_structure": "compilation",
    "tone": "engaging, clear, appropriate to the topic",
    "hook_style": "a strong opening line that creates curiosity",
    "cta_style": "ask for engagement, subscribe for more",
    "series_friendly": False,
}


def get_category_config(category):
    return CATEGORIES.get(category, DEFAULT_CATEGORY_CONFIG)


def list_categories():
    return list(CATEGORIES.keys())
