"""Multi-seed benchmark orchestration with bootstrap confidence intervals.

A single benchmark run gives one number per (case, condition). That number
is noisy enough that small deltas can flip on rerun. This module runs each
(case, condition) cell N times across varied seeds and temperatures, then
reports mean +/- stdev with 95% bootstrap confidence intervals.

The on-disk LLM cache (managed by LLMClient) makes reruns of the same
(prompt, temperature, seed) tuple free, so iteration is cheap once the
first pass is complete.
"""

from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


DEFAULT_SEED_SCHEDULE: list[tuple[int, float]] = [
    (1, 0.0),
    (2, 0.2),
    (3, 0.2),
    (4, 0.5),
    (5, 0.5),
]


@dataclass
class CellScores:
    """Raw and aggregated scores for one (case, condition) cell."""

    case_id: str
    condition: str  # "generic" | "skilled" | "reviewstem"
    raw_scores: list[float] = field(default_factory=list)
    raw_calls: list[int] = field(default_factory=list)
    raw_detected: list[bool] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return statistics.fmean(self.raw_scores) if self.raw_scores else 0.0

    @property
    def stdev(self) -> float:
        return statistics.pstdev(self.raw_scores) if len(self.raw_scores) >= 2 else 0.0

    @property
    def mean_calls(self) -> float:
        return statistics.fmean(self.raw_calls) if self.raw_calls else 0.0

    @property
    def detect_rate(self) -> float:
        if not self.raw_detected:
            return 0.0
        return sum(1 for d in self.raw_detected if d) / len(self.raw_detected)


def bootstrap_ci(
    samples: Sequence[float],
    confidence: float = 0.95,
    n_resamples: int = 2000,
    rng_seed: int = 12345,
) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean.

    Returns (low, high). Resampling is deterministic given rng_seed so
    the same input always produces the same CI.
    """
    if not samples:
        return 0.0, 0.0
    if len(samples) == 1:
        return samples[0], samples[0]

    rng = random.Random(rng_seed)
    n = len(samples)
    means = []
    for _ in range(n_resamples):
        resample = [samples[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(resample))
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    lo = means[int(alpha * n_resamples)]
    hi = means[int((1.0 - alpha) * n_resamples) - 1]
    return lo, hi


def is_significant(a: CellScores, b: CellScores) -> bool:
    """True if a's 95% bootstrap CI does NOT overlap b's CI."""
    a_lo, a_hi = bootstrap_ci(a.raw_scores)
    b_lo, b_hi = bootstrap_ci(b.raw_scores)
    return a_lo > b_hi or b_lo > a_hi


@dataclass
class MultiSeedResult:
    """Aggregated results across all seeds for one case."""

    case_id: str
    title: str
    requires_context: bool
    generic: CellScores
    skilled: CellScores
    reviewstem: CellScores

    def to_dict(self) -> dict:
        def cell_to_dict(c: CellScores) -> dict:
            lo, hi = bootstrap_ci(c.raw_scores)
            return {
                "mean": round(c.mean, 3),
                "stdev": round(c.stdev, 3),
                "ci_low": round(lo, 3),
                "ci_high": round(hi, 3),
                "mean_calls": round(c.mean_calls, 1),
                "detect_rate": round(c.detect_rate, 3),
                "n_samples": len(c.raw_scores),
            }

        return {
            "case_id": self.case_id,
            "title": self.title,
            "requires_context": self.requires_context,
            "generic": cell_to_dict(self.generic),
            "skilled": cell_to_dict(self.skilled),
            "reviewstem": cell_to_dict(self.reviewstem),
            "delta_mean": round(self.reviewstem.mean - self.generic.mean, 3),
            "reviewstem_vs_generic_significant": is_significant(self.reviewstem, self.generic),
            "reviewstem_vs_skilled_significant": is_significant(self.reviewstem, self.skilled),
        }


def parse_seed_schedule(spec: str) -> list[tuple[int, float]]:
    """Parse a CLI/env spec like '1:0.0,2:0.2,3:0.5' into [(seed, temp), ...]."""
    schedule: list[tuple[int, float]] = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if ":" not in raw:
            raise ValueError(f"Bad seed schedule entry: {raw!r} (expected seed:temp)")
        seed_str, temp_str = raw.split(":", 1)
        schedule.append((int(seed_str), float(temp_str)))
    if not schedule:
        raise ValueError("Empty seed schedule")
    return schedule


def write_multi_seed_outputs(results: list[MultiSeedResult], output_dir: Path) -> tuple[Path, Path]:
    """Write JSON + Markdown summary of multi-seed benchmark results."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = [r.to_dict() for r in results]
    json_path = output_dir / "benchmark_multiseed.json"
    md_path = output_dir / "benchmark_multiseed.md"

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(_format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def _format_markdown(payload: list[dict]) -> str:
    n = payload[0]["generic"]["n_samples"] if payload else 0
    lines = [
        f"# ReviewStem Multi-Seed Benchmark (N={n} per cell)",
        "",
        "Each cell is **mean +/- stdev** with the 95% bootstrap CI in brackets.",
        "*sig?* compares ReviewStem against the generic baseline; \"yes\" means",
        "the 95% bootstrap CIs do not overlap.",
        "",
        "| Case | Generic | Generic+Skills | ReviewStem | delta_mean | sig? | mean calls G/S/RS |",
        "| --- | --- | --- | --- | ---: | :---: | ---: |",
    ]
    for row in payload:
        g, s, rs = row["generic"], row["skilled"], row["reviewstem"]

        def fmt(c: dict) -> str:
            return f"{c['mean']:.2f} +/- {c['stdev']:.2f} [{c['ci_low']:.2f}, {c['ci_high']:.2f}]"

        sig = "yes" if row["reviewstem_vs_generic_significant"] else "no"
        calls = f"{g['mean_calls']:.0f}/{s['mean_calls']:.0f}/{rs['mean_calls']:.0f}"
        lines.append(
            f"| {row['case_id']} | {fmt(g)} | {fmt(s)} | {fmt(rs)} | {row['delta_mean']:+.2f} | {sig} | {calls} |"
        )

    # Aggregate row
    if payload:
        g_mean = statistics.fmean(row["generic"]["mean"] for row in payload)
        s_mean = statistics.fmean(row["skilled"]["mean"] for row in payload)
        rs_mean = statistics.fmean(row["reviewstem"]["mean"] for row in payload)
        delta = rs_mean - g_mean
        n_sig = sum(1 for r in payload if r["reviewstem_vs_generic_significant"])
        lines.append(
            f"| **mean** | **{g_mean:.3f}** | **{s_mean:.3f}** | **{rs_mean:.3f}** | **{delta:+.3f}** | {n_sig}/{len(payload)} sig | |"
        )

    lines.extend(
        [
            "",
            "## How to read this",
            "",
            "- **mean** is the average score across N seeds per (case, condition).",
            "- **stdev** is the population standard deviation across those seeds.",
            "- **CI** is the 95% percentile bootstrap confidence interval of the mean,",
            "  computed from 2000 resamples with a fixed RNG seed for reproducibility.",
            "- **sig?** = `yes` iff ReviewStem's CI does not overlap the generic baseline's CI.",
            "  Cases marked `no` are within the noise floor of the benchmark and should not",
            "  be claimed as wins.",
        ]
    )
    return "\n".join(lines) + "\n"
