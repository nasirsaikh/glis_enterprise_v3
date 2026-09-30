"""Reusable prompt guidance for email and attachment extraction."""
import json



def profile_guidance(profile):
    if not profile:
        return ""
    parts = [profile.system_prompt, profile.instructions]
    if profile.field_aliases:
        parts.append("Map these source labels to their canonical field names:\n" +
                     json.dumps(profile.field_aliases, ensure_ascii=False))
    if profile.pk:
        for example in profile.examples.filter(is_active=True)[:5]:
            parts.append("Example input:\n" + example.input_text + "\nExpected JSON:\n" +
                         json.dumps(example.expected_output, ensure_ascii=False))
    return "\n\n".join(part for part in parts if part)
