You are explaining the pedagogical order of chapters in an onboarding
tutorial for a codebase. The order below was computed from the dependency
graph between abstractions; it is already final and must not be changed.

## Final chapter order

{% for idx in chapter_order %}
{{ loop.index }}. **{{ abstractions[idx].name }}** — {{ abstractions[idx].description }}
{% endfor %}

## Your task

Write a 2–3 sentence explanation (in {{ language }}) of WHY this order helps a
newcomer onboard step-by-step — for example: "We start with the data model
because every other layer depends on it..."

Constraints:
- Output ONLY the explanation text. No JSON, no bullet points, no preamble.
- Do not suggest a different order.
- Keep it under 60 words.