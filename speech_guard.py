"""Bound decoding and locate the scripted ending using timestamped ASR words."""
import math
import re
import unicodedata
from difflib import SequenceMatcher


def spoken_text(text):
    return re.sub(r"\[S\d+\]", "", str(text or ""), flags=re.I).strip()


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKC", spoken_text(text)).casefold()
                   if c.isalnum())


def estimate_seconds(text):
    text = spoken_text(text)
    chinese = len(re.findall(r"[\u3400-\u9fff]", text))
    words = len(re.findall(r"[a-zA-Z]+|\d+", text))
    pauses = len(re.findall(r"[。！？!?；;，,]", text))
    return max(2.0, chinese / 4.3 + words / 2.6 + pauses * 0.12)


def generation_budget(text, requested=0):
    # 12.5 codec frames/s, plus delayed codebooks. Leave room for slow speech,
    # but never let a short script inherit the old 2000-step (~160s) default.
    automatic = max(96, math.ceil((estimate_seconds(text) * 1.55 + 2) * 12.5) + 16)
    limit = min(8192, automatic)
    return min(limit, max(32, int(requested))) if int(requested) > 0 else limit


def script_endpoint(text, words):
    """Match only a prefix, not an unrelated later occurrence of the script.

    ASR can make minor character errors. Require high whole-script similarity,
    + an intact start and ending. Fail closed if the spoken script is incomplete.
    Returned end time points to the last matching ASR word, not the segment end.
    """
    expected = normalized(text)
    if not expected:
        return {"ok": False, "reason": "台词为空"}
    heard = ""
    candidates = []
    for word in words:
        value = normalized(word.get("word", ""))
        if not value:
            continue
        heard += value
        if len(heard) >= len(expected) * 0.80:
            score = SequenceMatcher(None, expected, heard, autojunk=False).ratio()
            anchor = min(6, len(expected))
            start = SequenceMatcher(None, expected[:anchor], heard[:anchor]).ratio()
            end = SequenceMatcher(None, expected[-anchor:], heard[-anchor:]).ratio()
            if score >= 0.86 and start >= 0.80 and end >= 0.80:
                candidates.append((score, float(word["end"])))
        if len(heard) > len(expected) * 1.25 + 8:
            break
    if not candidates:
        return {"ok": False, "reason": "未能确认台词完整且与录音一致"}
    # Prefer the earliest endpoint at the best score; do not retain repeats.
    score, end = max(candidates, key=lambda item: (item[0], -item[1]))
    next_start = next((float(w["start"]) for w in words if float(w["end"]) > end + .02), end + .18)
    return {"ok": True, "end": end, "cut_at": max(end, min(end + .18, next_start)), "score": round(score, 4)}
