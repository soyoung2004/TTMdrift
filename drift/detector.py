from drift.drift_features import *
from drift.probe_bank import PROBE_BANK
from drift.drift_config import FEATURE_WEIGHTS, DRIFT_THRESHOLD
from shared.logger import logger

def detect_persona_drift(stage: str, reply: str) -> bool:
    features = {
        "repetition": fraction_repeated_words(reply),
        "style_shited": fraction_style_shifted(reply),
        "past_tense": fraction_past_tense_verbs(reply),
        "uniqueness": fraction_unique_words(reply),
        "question_ratio": fraction_sentences_that_are_questions(reply),
    }
    score = sum(features[k] * FEATURE_WEIGHTS.get(k, 0) for k in features)
    score_drift = score > DRIFT_THRESHOLD

    _, _, judge_func = PROBE_BANK.get(stage, ("", "", lambda x: True))
    prompt_drift = not judge_func(reply)

    logger.info(f"[DRIFT DETECT] Stage: {stage}, Score: {score:.3f}, Drift: score={score_drift}, prompt={prompt_drift}, Features: {features}")
    return score_drift or prompt_drift

def run_detect_and_override(state) -> str | None:
    try:
        drifted = detect_persona_drift(state.stage, state.response)
        state.drift_trace.append(drifted)
        state.drift_trace = state.drift_trace[-5:]
        if state.drift_trace.count(True) >= 3:
            return "possible"
        return None
    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        return None
