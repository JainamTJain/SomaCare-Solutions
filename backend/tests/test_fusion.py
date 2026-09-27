"""Camera fusion: an infrared baby monitor above the gate can reset a timer."""

from turnwise.config import EngineConfig
from turnwise.engine.fusion import BedMovement, VisionChange, classify_reposition, resets_timer


def test_uncertain_vision_never_resets():
    cfg = EngineConfig()
    result = classify_reposition(VisionChange(0.4), None, cfg, has_vision=True)
    assert result == "uncertain"
    assert resets_timer(result, cfg) is False


def test_uncovered_confidence_is_likely_and_still_unvalidated():
    cfg = EngineConfig()
    result = classify_reposition(VisionChange(0.91), None, cfg, has_vision=True, cover="none")
    assert result == "likely"
    assert resets_timer(result, cfg) is True


def test_a_confident_blanket_reading_does_not_reset():
    cfg = EngineConfig()
    result = classify_reposition(VisionChange(0.99), None, cfg, has_vision=True, cover="blanket")
    assert result == "uncertain"
    assert resets_timer(result, cfg) is False
    sheet = classify_reposition(VisionChange(0.99), None, cfg, has_vision=True, cover="sheet")
    assert sheet == "uncertain"


def test_bed_only_stays_uncertain_until_a_rule_is_validated():
    cfg = EngineConfig(bed_rule_validated=False, has_vision=False)
    result = classify_reposition(None, BedMovement(0.9, 30), cfg, has_vision=False)
    assert result == "uncertain"
    assert resets_timer(result, cfg) is False
