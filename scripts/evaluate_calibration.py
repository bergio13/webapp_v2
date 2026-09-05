"""
scripts/evaluate_calibration.py — Calibration Benchmark & Stratified Evaluation CLI

Evaluates the Cinephile Cosmos calibration engine against synthetic and observed user cohorts,
stratified by:
1. User-History Size Tiers (sparse <10, moderate 10-34, rich 35+)
2. Catalogue Segments (Macro Realms: Sci-Fi, Arthouse, Noir, Animation, etc.)
Compares calibrated probabilities P(positive interaction | raw_score) against
the uncalibrated heuristic clamp(70 + 29 * net).
"""

import sys
import os
import math
import numpy as np

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.calibration_service import (
    PlattCalibrator,
    IsotonicCalibrator,
    generate_stratified_calibration_report,
    compute_brier_score,
    compute_ece,
    classify_history_tier,
    map_to_match_score,
)

MACRO_REALMS = [
    "Realm 0: Animation & Visual Fantasia",
    "Realm 1: Noir, Crime & Psychological",
    "Realm 2: Arthouse & Humanist Core",
    "Realm 3: Sci-Fi Cosmos & Speculative",
    "Realm 4: Satirical Wit & Pop Indie",
    "Realm 5: Action Frontier & Kinetic Spectacle"
]


def run_benchmark():
    print("=" * 80)
    print(" CINEPHILE COSMOS — AFFINITY CALIBRATION STRATIFIED BENCHMARK")
    print("=" * 80)

    np.random.seed(42)
    eval_records = []

    # Cohorts:
    # 1. Sparse Users (History < 10): 30 cohorts
    # 2. Moderate Users (History 10-34): 40 cohorts
    # 3. Rich Users (History 35+): 30 cohorts
    cohort_configs = [
        ("sparse", 5, 30),
        ("moderate", 22, 40),
        ("rich", 65, 30),
    ]

    for tier, avg_hist_len, num_cohorts in cohort_configs:
        for _ in range(num_cohorts):
            hist_len = max(2, int(np.random.normal(avg_hist_len, avg_hist_len * 0.2)))
            realm = np.random.choice(MACRO_REALMS)

            # True user latent standard for this realm (some love it, some are indifferent)
            realm_affinity_shift = np.random.uniform(-0.15, 0.25)

            # Generate candidate evaluations for this cohort
            for _ in range(6):
                # Raw net affinity in [0.05, 0.95]
                raw_net = float(np.clip(np.random.beta(2.5, 2.5) + realm_affinity_shift, 0.05, 0.95))

                # True underlying probability of user satisfaction follows a sigmoid with domain noise
                true_latent = 1.0 / (1.0 + math.exp(-4.2 * (raw_net - 0.48)))
                y_true = 1 if np.random.rand() < true_latent else 0

                # Train calibrator on this user's history proxy
                hist_scores = np.random.uniform(0.1, 0.9, size=hist_len)
                hist_y = (hist_scores + np.random.normal(0, 0.15, size=hist_len) > 0.48).astype(int)

                if hist_len >= 30:
                    cal = IsotonicCalibrator().fit(hist_scores, hist_y)
                else:
                    cal = PlattCalibrator().fit(hist_scores, hist_y)

                cal_prob = float(cal.predict_proba(np.array([raw_net]))[0])

                eval_records.append({
                    "y_true": y_true,
                    "calibrated_prob": cal_prob,
                    "raw_net": raw_net,
                    "history_tier": tier,
                    "history_len": hist_len,
                    "catalogue_segment": realm
                })

    report = generate_stratified_calibration_report(eval_records, n_bins=5)

    print(f"\nTotal Evaluated Interactions: {report.overall_metrics.sample_count}")
    print(f"Empirical Positive Base Rate: {report.overall_metrics.positive_rate * 100:.1f}%\n")

    print("-" * 80)
    print(" OVERALL CALIBRATION PERFORMANCE VS UNCALIBRATED HEURISTIC")
    print("-" * 80)
    print(f"  Uncalibrated Linear Heuristic clamp(70+29*net) Brier Score: {report.uncalibrated_brier:.4f}")
    print(f"  Probabilistically Calibrated P(Y=1|s) Brier Score:         {report.overall_metrics.brier_score:.4f}")
    print(f"  Brier Error Reduction:                                    {report.brier_reduction_pct:+.1f}%")
    print(f"  Overall Expected Calibration Error (ECE):                 {report.overall_metrics.expected_calibration_error:.4f}")
    print(f"  Brier Skill Score:                                        {report.overall_metrics.brier_skill_score:+.4f}")

    print("\n" + "-" * 80)
    print(" STRATIFIED BY USER-HISTORY SIZE TIER")
    print("-" * 80)
    print(f"{'History Tier':<15} | {'Samples':<8} | {'Brier Score':<12} | {'ECE':<8} | {'Avg P(Enjoy)':<14} | {'Base Rate':<10}")
    print("-" * 80)
    for tier in ["sparse", "moderate", "rich"]:
        m = report.by_history_tier.get(tier)
        if m:
            print(f"{tier.capitalize():<15} | {m.sample_count:<8} | {m.brier_score:<12.4f} | {m.expected_calibration_error:<8.4f} | {m.mean_predicted_prob * 100:<13.1f}% | {m.positive_rate * 100:<9.1f}%")

    print("\n" + "-" * 80)
    print(" STRATIFIED BY CATALOGUE MACRO REALM")
    print("-" * 80)
    print(f"{'Macro Realm':<42} | {'Samples':<8} | {'Brier Score':<12} | {'ECE':<8}")
    print("-" * 80)
    for realm, m in report.by_catalogue_segment.items():
        print(f"{realm:<42} | {m.sample_count:<8} | {m.brier_score:<12.4f} | {m.expected_calibration_error:<8.4f}")

    print("\n" + "-" * 80)
    print(" OVERALL RELIABILITY BINS (Calibration Curve Points)")
    print("-" * 80)
    print(f"{'Bin':<6} | {'Score Range':<15} | {'Count':<7} | {'Mean Forecast P':<16} | {'Actual Pos Rate':<16} | {'Gap (Abs Error)':<14}")
    print("-" * 80)
    for b in report.overall_metrics.reliability_bins:
        rng = f"[{b['range_min']:.2f}, {b['range_max']:.2f}]"
        print(f"{b['bin_index']:<6} | {rng:<15} | {b['count']:<7} | {b['confidence'] * 100:<15.1f}% | {b['accuracy'] * 100:<15.1f}% | {b['gap'] * 100:<13.1f}%")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
