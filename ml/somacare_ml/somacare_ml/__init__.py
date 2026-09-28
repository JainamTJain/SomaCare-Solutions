"""SomaCare predictive analysis. Pure Python, no LLM calls, no network access.

Modules
  turn          confirms position changes from noisy per-frame readings, never resets a timer when unsure
  safety_sim    error-injection simulation: is the system safe when the position model is wrong?
  continence    discrete-time hazard model of wetness, with a simulator and gates
  patterns      descriptive patterns (clusters by time of day and meals), with sample sizes and tests
  position      overhead position classifier features, synthetic scenes, training and inference
"""
__version__ = "0.1.0"
