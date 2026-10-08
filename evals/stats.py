"""Small statistics helpers: Wilson interval, Cohen's kappa, percentiles. No extra libraries."""

from __future__ import annotations

import math


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion. Better than "p ± 1.96·se" near 0% or 100%:
    120/120 gives about (0.969, 1.0), not a meaningless (1.0, 1.0)."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def cohens_kappa(labels_a: list, labels_b: list) -> float | None:
    """Agreement between two raters beyond chance (1 = perfect, 0 = chance level). None if undefined."""
    if not labels_a or len(labels_a) != len(labels_b):
        return None
    n = len(labels_a)
    categories = set(labels_a) | set(labels_b)
    observed = sum(a == b for a, b in zip(labels_a, labels_b, strict=True)) / n
    expected = sum((labels_a.count(c) / n) * (labels_b.count(c) / n) for c in categories)
    if expected == 1:
        return None
    return (observed - expected) / (1 - expected)


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..100)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]
