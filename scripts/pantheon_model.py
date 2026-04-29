"""Fit a model to predict Pantheon's spawn decisions, after filtering
out trivially blocked turns (cd>0, can't afford, at unit cap)."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.tree import DecisionTreeClassifier, export_text

CSV = Path("pantheon_spawn.csv")


def load() -> list[dict]:
    rows = []
    with CSV.open() as f:
        for r in csv.DictReader(f):
            row = {
                "replay": r["replay"],
                "turn": int(r["turn"]),
                "ti": int(r["ti"]),
                "scale_milli": int(r["scale_milli"]),
                "builder_cost": int(r["builder_cost"]),
                "cd": int(r["cd"]),
                "rounds_since_spawn": int(r["rounds_since_spawn"]),
                "spawned_count": int(r["spawned_count"]),
                "live_units": int(r["live_units"]),
                "live_harvesters": int(r["live_harvesters"]),
                "income_recent": float(r["income_recent"]),
                "delivery_rate_16": float(r["delivery_rate_16"]),
                "delivery_rate_100": float(r["delivery_rate_100"]),
                "ti_collected": int(r["ti_collected"]),
                "spawned": r["spawned"] == "True",
            }
            row["units_no_harv"] = row["live_units"] - row["live_harvesters"]
            row["ti_minus_cost"] = row["ti"] - row["builder_cost"]
            row["ti_div_cost"] = (
                row["ti"] / row["builder_cost"] if row["builder_cost"] else 0
            )
            row["deliv_x_round"] = row["delivery_rate_16"] * row["rounds_since_spawn"]
            rows.append(row)
    return rows


def candidates(rows: list[dict]) -> list[dict]:
    """Free-decision turns: cd=0, can afford, below unit cap, past initial 4."""
    out = []
    for r in rows:
        if r["spawned_count"] < 4:
            continue
        if r["cd"] != 0:
            continue
        if r["ti"] < r["builder_cost"]:
            continue
        if r["units_no_harv"] >= 50:
            continue
        out.append(r)
    return out


def basic_stats(rows: list[dict]) -> None:
    pos = [r for r in rows if r["spawned"]]
    neg = [r for r in rows if not r["spawned"]]
    print(
        f"\n=== FREE-DECISION CANDIDATES: {len(rows)}  spawn={len(pos)}  noop={len(neg)} ==="
    )

    def stats(name: str, vals: list[float]) -> None:
        if not vals:
            return
        a = np.array(vals)
        print(
            f"  {name:24s}  min={a.min():7.2f}  med={np.median(a):7.2f}  "
            f"mean={a.mean():7.2f}  max={a.max():7.2f}"
        )

    print("\nSpawn rows:")
    for f in (
        "ti",
        "builder_cost",
        "ti_minus_cost",
        "ti_div_cost",
        "rounds_since_spawn",
        "income_recent",
        "delivery_rate_16",
        "delivery_rate_100",
        "units_no_harv",
        "live_harvesters",
        "scale_milli",
        "turn",
    ):
        stats(f, [r[f] for r in pos])

    print("\nNo-spawn rows:")
    for f in (
        "ti",
        "builder_cost",
        "ti_minus_cost",
        "ti_div_cost",
        "rounds_since_spawn",
        "income_recent",
        "delivery_rate_16",
        "delivery_rate_100",
        "units_no_harv",
        "live_harvesters",
        "scale_milli",
        "turn",
    ):
        stats(f, [r[f] for r in neg])


def test_period_rule(rows: list[dict]) -> None:
    """Rule: spawn iff rounds_since_spawn >= K (and free-decision)."""
    print("\n=== PERIOD RULE: spawn iff rounds_since_spawn >= K ===")
    pos = [r for r in rows if r["spawned"]]
    neg = [r for r in rows if not r["spawned"]]
    if not pos:
        return
    for k in range(1, 16):
        tp = sum(1 for r in pos if r["rounds_since_spawn"] >= k)
        fp = sum(1 for r in neg if r["rounds_since_spawn"] >= k)
        fn = len(pos) - tp
        tn = len(neg) - fp
        prec = tp / (tp + fp) if (tp + fp) else 0
        rec = tp / (tp + fn) if (tp + fn) else 0
        acc = (tp + tn) / len(rows)
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
        print(
            f"  K={k:3d}  tp={tp:3d}/{len(pos)} fp={fp:4d}/{len(neg)}  "
            f"prec={prec:.3f} rec={rec:.3f} f1={f1:.3f} acc={acc:.3f}"
        )


def fit_models(rows: list[dict]) -> None:
    feats = [
        "turn",
        "ti",
        "builder_cost",
        "ti_minus_cost",
        "ti_div_cost",
        "scale_milli",
        "units_no_harv",
        "live_harvesters",
        "rounds_since_spawn",
        "income_recent",
        "delivery_rate_16",
        "delivery_rate_100",
        "deliv_x_round",
    ]
    X = np.array([[r[f] for f in feats] for r in rows], dtype=float)
    y = np.array([r["spawned"] for r in rows], dtype=int)

    print("\n=== LOGISTIC REGRESSION (class-weighted) ===")
    lr = LogisticRegression(class_weight="balanced", max_iter=5000, C=1.0)
    lr.fit(X, y)
    pred = lr.predict(X)
    print(classification_report(y, pred, target_names=["no_spawn", "spawn"], digits=3))
    print("Confusion matrix [[TN FP][FN TP]]:")
    print(confusion_matrix(y, pred))
    coefs = sorted(zip(feats, lr.coef_[0], strict=False), key=lambda x: -abs(x[1]))
    print("Coefs (sorted by |w|):")
    for f, w in coefs:
        print(f"  {f:24s}  {w:+.4e}")
    print(f"Intercept: {lr.intercept_[0]:+.4f}")

    print("\n=== DECISION TREE (depth=4, class-weighted) ===")
    dt = DecisionTreeClassifier(
        max_depth=4, class_weight="balanced", min_samples_leaf=15
    )
    dt.fit(X, y)
    pred = dt.predict(X)
    print(classification_report(y, pred, target_names=["no_spawn", "spawn"], digits=3))
    print(export_text(dt, feature_names=feats))

    print("\n=== DECISION TREE (depth=2) ===")
    dt2 = DecisionTreeClassifier(
        max_depth=2, class_weight="balanced", min_samples_leaf=20
    )
    dt2.fit(X, y)
    pred2 = dt2.predict(X)
    print(classification_report(y, pred2, target_names=["no_spawn", "spawn"], digits=3))
    print(export_text(dt2, feature_names=feats))


def test_compound_rules(rows: list[dict]) -> None:
    """Test a few human-interpretable compound rules."""
    print("\n=== HUMAN-INTERPRETABLE RULES ===")
    pos = [r for r in rows if r["spawned"]]
    neg = [r for r in rows if not r["spawned"]]

    rules = [
        ("ti >= 3*cost", lambda r: r["ti"] >= 3 * r["builder_cost"]),
        ("ti >= 4*cost", lambda r: r["ti"] >= 4 * r["builder_cost"]),
        (
            "ti >= 4*cost AND rounds_since>=5",
            lambda r: r["ti"] >= 4 * r["builder_cost"] and r["rounds_since_spawn"] >= 5,
        ),
        (
            "ti >= 3*cost AND rounds_since>=5",
            lambda r: r["ti"] >= 3 * r["builder_cost"] and r["rounds_since_spawn"] >= 5,
        ),
        (
            "ti >= 3*cost AND rounds_since>=10",
            lambda r: (
                r["ti"] >= 3 * r["builder_cost"] and r["rounds_since_spawn"] >= 10
            ),
        ),
        ("ti - cost >= 400", lambda r: r["ti"] - r["builder_cost"] >= 400),
        (
            "ti - cost >= 300 AND rounds_since>=5",
            lambda r: (
                r["ti"] - r["builder_cost"] >= 300 and r["rounds_since_spawn"] >= 5
            ),
        ),
    ]
    for name, fn in rules:
        tp = sum(1 for r in pos if fn(r))
        fp = sum(1 for r in neg if fn(r))
        fn_ct = len(pos) - tp
        tn = len(neg) - fp
        prec = tp / (tp + fp) if (tp + fp) else 0
        rec = tp / (tp + fn_ct) if (tp + fn_ct) else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
        (tp + tn) / len(rows)
        print(
            f"  {name:50s}  prec={prec:.3f} rec={rec:.3f} f1={f1:.3f}  tp={tp}/{len(pos)} fp={fp}"
        )


def grid_search_compound(rows: list[dict]) -> None:
    """Grid-search 'ti >= K*cost AND rounds_since >= D' to find the best."""
    print("\n=== GRID SEARCH:  ti >= K*cost AND rounds_since >= D ===")
    pos = [r for r in rows if r["spawned"]]
    neg = [r for r in rows if not r["spawned"]]
    best = (0.0, 0, 0.0, 0, 0, 0, 0)
    for k10 in range(15, 70):
        k = k10 / 10
        for d in range(1, 16):
            tp = sum(
                1
                for r in pos
                if r["ti"] >= k * r["builder_cost"] and r["rounds_since_spawn"] >= d
            )
            fp = sum(
                1
                for r in neg
                if r["ti"] >= k * r["builder_cost"] and r["rounds_since_spawn"] >= d
            )
            fn_ct = len(pos) - tp
            len(neg) - fp
            prec = tp / (tp + fp) if (tp + fp) else 0
            rec = tp / (tp + fn_ct) if (tp + fn_ct) else 0
            f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
            if f1 > best[0]:
                best = (f1, tp, prec, rec, fp, k, d)
    f1, tp, prec, rec, fp, k, d = best
    print(f"  best: ti >= {k:.1f}*cost AND rounds_since >= {d}")
    print(
        f"        f1={f1:.3f} prec={prec:.3f} rec={rec:.3f} tp={tp}/{len(pos)} fp={fp}/{len(neg)}"
    )


def main() -> None:
    rows = load()
    cand = candidates(rows)
    basic_stats(cand)
    test_period_rule(cand)
    test_compound_rules(cand)
    grid_search_compound(cand)
    fit_models(cand)


if __name__ == "__main__":
    main()
