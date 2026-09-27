"""Rule-based preference extractor.

This is the non-AI fallback, and the only extractor that runs unless the
llm_preference_extract flag is on. Even then, if no local model is configured,
calls fall back here. Nothing is shown to a CNA until a nurse approves it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class PreferenceSuggestion:
    code: str
    params: dict
    source_excerpt: str
    category: str


_RULES: list[tuple[str, str, str, dict]] = [
    (r"\bright side\b|\blado derecho\b|\bkanang (?:tagiliran|side)\b", "turning", "pref.turn.side_preferred", {"side": "right"}),
    (r"\bleft side\b|\blado izquierdo\b|\bkaliwang tagiliran\b", "turning", "pref.turn.side_preferred", {"side": "left"}),
    (r"pillow between (?:her |his |their )?knees|almohada entre las rodillas|unan sa pagitan", "turning", "pref.turn.pillow_knees", {}),
    (r"float (?:her |his |their )?heels|eleve los talones|iangat ang mga sakong", "turning", "pref.turn.float_heels", {}),
    (r"\b2 people\b|\btwo people\b|\btwo-person\b|2 personas|2 tao", "turning", "pref.turn.two_person", {}),
    (r"left hip (?:is )?tender|cadera izquierda|kaliwang balakang", "turning", "pref.turn.avoid_area", {"area": "left_hip"}),
    (r"right hip (?:is )?tender|cadera derecha|kanang balakang", "turning", "pref.turn.avoid_area", {"area": "right_hip"}),
    (r"say (?:her|his|their) name|diga su nombre|tawagin ang kanyang pangalan", "comfort", "pref.comfort.say_name_first", {}),
    (r"light(?:s)? off|luz apagada|nakapatay ang ilaw", "comfort", "pref.comfort.light_off", {}),
    (r"usually (?:needs a )?change around (\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", "continence", "pref.continence.usual_time", {}),
]


def extract_preferences(text: str) -> list[PreferenceSuggestion]:
    """Keyword and pattern rules. Each suggestion keeps the source sentence."""
    if not text or not text.strip():
        return []
    sentences = re.split(r"(?<=[.!;])\s+|\n+", text.strip())
    found: list[PreferenceSuggestion] = []
    seen: set[tuple] = set()
    for sentence in sentences:
        lowered = sentence.lower()
        for pattern, category, code, params in _RULES:
            match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if not match:
                continue
            use_params = dict(params)
            if code == "pref.continence.usual_time":
                use_params = {"time": match.group(1)}
            key = (code, tuple(sorted(use_params.items())))
            if key in seen:
                continue
            seen.add(key)
            found.append(
                PreferenceSuggestion(
                    code=code,
                    params=use_params,
                    source_excerpt=sentence.strip(),
                    category=category,
                )
            )
    return found


def extract_with_fallback(text: str, *, llm_enabled: bool) -> tuple[list[PreferenceSuggestion], str]:
    """Language-model extraction is optional and off by default.

    No network call and no generative model runs here. When the flag is on and
    no on-site model is configured, the rule extractor is the fallback.
    """
    if llm_enabled:
        return extract_preferences(text), "rule_fallback"
    return extract_preferences(text), "rules"
