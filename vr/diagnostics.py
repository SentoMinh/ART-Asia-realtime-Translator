"""Opt-in aggregate VR timings; no per-frame logging or user content."""
from __future__ import annotations

from collections import Counter
import logging


class Diagnostics:
    def __init__(self):
        self._since = self._previous = None
        self._samples = {}
        self._losses = Counter()

    def sample(self, name: str, seconds: float) -> None:
        count, total, maximum = self._samples.get(name, (0, 0.0, 0.0))
        self._samples[name] = count + 1, total + seconds, max(maximum, seconds)

    def loss(self, reason: str) -> None:
        self._losses[reason] += 1

    def callback(self, now: float) -> None:
        if self._since is None:
            self._since = now
        if self._previous is not None:
            self.sample("gap", max(0.0, now - self._previous))
        self._previous = now

    def flush(self, now: float) -> None:
        if self._since is None or now - self._since < 5.0:
            return
        timings = " ".join(
            f"{name}_ms(avg/max)={total / count * 1000:.2f}/{maximum * 1000:.2f} n={count}"
            for name, (count, total, maximum) in sorted(self._samples.items()))
        logging.getLogger("engine.vr").info("VR diagnostics %s input_loss=%s", timings, dict(self._losses))
        self._samples.clear()
        self._losses.clear()
        self._since = now
