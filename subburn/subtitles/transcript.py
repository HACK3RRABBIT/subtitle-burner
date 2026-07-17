import re


def build_transcript(segments: list[dict]) -> str:
    paragraphs = []
    current_speaker = None
    current_lines: list[str] = []
    last_end = None

    for seg in segments:
        speaker = seg.get("speaker")
        gap = (seg["start"] - last_end) if last_end is not None else 0.0
        speaker_changed = speaker is not None and speaker != current_speaker
        big_pause = speaker is None and last_end is not None and gap > 2.0

        if current_lines and (speaker_changed or big_pause):
            paragraphs.append((current_speaker, " ".join(current_lines).strip()))
            current_lines = []

        current_speaker = speaker
        current_lines.append(seg["text"].strip())
        last_end = seg["end"]

    if current_lines:
        paragraphs.append((current_speaker, " ".join(current_lines).strip()))

    lines = [f"{speaker}: {text}" if speaker else text for speaker, text in paragraphs]
    return "\n\n".join(lines)


def apply_speaker_names(raw_text: str, speakers: list[str], speaker_names: dict[str, str]) -> str:
    text = raw_text
    for generic in speakers:
        custom = speaker_names.get(generic, generic)
        text = re.sub(rf"(?m)^{re.escape(generic)}:", f"{custom}:", text)
    return text
