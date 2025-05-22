import re
from collections import Counter
from nltk import pos_tag, word_tokenize
from drift.utils import get_sia

STYLE_SHIFT_PATTERNS = ["짜증", "됐어", "죽겠어", "어쩌라고", "몰라"]

def fraction_repeated_words(text):
    words = re.findall(r'\b\w+\b', text.lower())
    counts = Counter(words)
    return sum(1 for c in counts.values() if c >= 2) / len(words) if words else 0

def fraction_style_shifted(text):
    words = re.findall(r'\b\w+\b', text.lower())
    teen = sum(1 for w in words if w in {"ㅋㅋ", "ㅎㅎ", "ㅠㅠ", "ㅜㅜ"})
    aggressive = sum(1 for pat in STYLE_SHIFT_PATTERNS if pat in text)
    return (teen + aggressive) / len(words) if words else 0

def fraction_past_tense_verbs(text):
    tags = pos_tag(word_tokenize(text))
    verbs = [t for _, t in tags if t.startswith("VB")]
    past = [t for t in verbs if t in ("VBD", "VBN")]
    return len(past) / len(verbs) if verbs else 0

def fraction_unique_words(text):
    words = re.findall(r'\b\w+\b', text.lower())
    counts = Counter(words)
    return sum(1 for c in counts.values() if c == 1) / len(words) if words else 0

def fraction_sentences_that_are_questions(text):
    sentences = re.split(r'[.!?]', text)
    return sum(1 for s in sentences if '?' in s) / len(sentences) if sentences else 0
