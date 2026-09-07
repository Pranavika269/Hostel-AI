"""
Hostel AI severity engine.

If settings.GEMINI_API_KEY is set AND the `google-generativeai` package is
installed, complaints are analyzed by Gemini. Otherwise the app transparently
falls back to a keyword/weight based rule engine so the project runs
out-of-the-box with zero external API keys.
"""
import json
import re

from django.conf import settings

SEVERITY_ORDER = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

# Keyword weight table for the rule-based fallback engine.
CRITICAL_KEYWORDS = [
    'fire', 'electrocut', 'electric shock', 'short circuit', 'gas leak',
    'harassment', 'assault', 'ragging', 'suicide', 'self harm', 'weapon',
    'food poison', 'unconscious', 'bleeding', 'sexual', 'stalk', 'threat',
    'collapse', 'burn injury', 'molest',
]
HIGH_KEYWORDS = [
    'leak', 'flood', 'no water', 'water shortage', 'stolen', 'theft', 'broken lock',
    'no electricity', 'power cut', 'insect infestation', 'rat', 'cockroach',
    'spoiled food', 'stale food', 'injury', 'fever', 'illness', 'mold', 'sewage',
    'unsafe', 'security', 'smoke',
]
MEDIUM_KEYWORDS = [
    'noisy', 'noise', 'dirty', 'unclean', 'stain', 'crack', 'fan not working',
    'light not working', 'wifi', 'internet', 'cold food', 'late delivery',
    'maintenance', 'plumbing', 'door', 'window', 'furniture',
]

CATEGORY_BASE_SCORE = {
    'FOOD': 20,
    'ROOM': 15,
    'MAINTENANCE': 12,
    'RAGGING': 45,
    'OTHER': 10,
}


def _score_to_severity(score: float) -> str:
    if score >= 75:
        return 'CRITICAL'
    if score >= 50:
        return 'HIGH'
    if score >= 25:
        return 'MEDIUM'
    return 'LOW'


def _rule_based_analysis(description: str, category: str, title: str = '') -> dict:
    text = f'{title} {description}'.lower()
    score = CATEGORY_BASE_SCORE.get(category, 10)
    matched = []

    for kw in CRITICAL_KEYWORDS:
        if kw in text:
            score += 35
            matched.append(kw)
    for kw in HIGH_KEYWORDS:
        if kw in text:
            score += 18
            matched.append(kw)
    for kw in MEDIUM_KEYWORDS:
        if kw in text:
            score += 8
            matched.append(kw)

    # Length / urgency heuristics
    if re.search(r'\b(urgent|immediately|emergency|asap|help)\b', text):
        score += 12
        matched.append('urgency language')

    exclamations = text.count('!')
    score += min(exclamations * 2, 10)

    score = max(0, min(100, score))
    severity = _score_to_severity(score)

    if matched:
        reason = ("Rule-based engine detected the following signal keywords: "
                  f"{', '.join(sorted(set(matched)))}.")
    else:
        reason = "No high-risk keywords detected; classified using category baseline."

    return {
        'severity': severity,
        'score': round(score, 1),
        'explanation': reason,
        'engine': 'rule-based',
    }


def _gemini_analysis(description: str, category: str, title: str = ''):
    """Attempt Gemini-powered analysis. Returns None if unavailable/fails."""
    api_key = getattr(settings, 'GEMINI_API_KEY', '')
    if not api_key:
        return None
    try:
        import google.generativeai as genai
    except ImportError:
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(getattr(settings, 'GEMINI_MODEL_NAME', 'gemini-1.5-flash'))
        prompt = f"""You are a hostel grievance triage assistant. Analyze this complaint and
respond ONLY with valid JSON (no markdown fences) in this exact shape:
{{"severity": "LOW|MEDIUM|HIGH|CRITICAL", "score": <0-100 number>, "explanation": "<one sentence>"}}

Category: {category}
Title: {title}
Description: {description}
"""
        response = model.generate_content(prompt)
        raw = response.text.strip()
        raw = re.sub(r'^```json|```$', '', raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        severity = str(data.get('severity', 'LOW')).upper()
        if severity not in SEVERITY_ORDER:
            severity = _score_to_severity(float(data.get('score', 0)))
        return {
            'severity': severity,
            'score': round(float(data.get('score', 0)), 1),
            'explanation': data.get('explanation', ''),
            'engine': 'gemini',
        }
    except Exception:
        return None


def analyze_complaint(description: str, category: str, title: str = '') -> dict:
    """Public entry point used by views. Tries Gemini, falls back to rules."""
    result = _gemini_analysis(description, category, title)
    if result is None:
        result = _rule_based_analysis(description, category, title)
    return result


def allocation_hours_for_severity(severity: str) -> float:
    return settings.SEVERITY_ALLOCATION_HOURS.get(severity, 72)
