"""
ML signal filter (meta-labeling) -- implements the pre-registration in
15_ml_filter_experiment.md §1 exactly. Do not change the model, features,
take rule or pass criteria here without a new, dated pre-registration.

Inputs: realistic-mode trade dumps from custom_research.py in _custom/:
  {h1,m15}_{is,val}_{I01..I08 | S01..S10}_trades.parquet
and, only with --holdout-final, the matching {h1,m15}_holdout_* dumps.

  python ml_filter.py                 # WF-IS + WF-VAL
  python ml_filter.py --holdout-final # + HOLDOUT, run once
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

HERE = Path(__file__).resolve().parent
CUSTOM = HERE / "_custom"
RISK_USD = 25.0
IND = "I01_I02_I03_I04_I05_I06_I07_I08"
SFAM = "S01_S02_S03_S04_S05_S06_S07_S08_S09_S10"
WINDOWS = {
    "WF-IS": ("2021-01-01", "2024-07-01"),
    "WF-VAL": ("2024-07-01", "2025-07-01"),
    "HOLDOUT": ("2025-07-01", "2100-01-01"),
}
N_RANDOM = 1000
NUMERIC = ["side_long", "hour", "weekday", "adx", "rsi14", "with_ema200", "ema50_over_200", "with_supertrend"]


def load(periods: list[str]) -> pd.DataFrame:
    frames = []
    for tf in ("h1", "m15"):
        for p in periods:
            for fam in (IND, SFAM):
                f = CUSTOM / f"{tf}_{p}_{fam}_trades.parquet"
                if not f.exists():
                    sys.exit(f"missing {f.name} -- run custom_research.py --period {p} for {tf.upper()} first")
                d = pd.read_parquet(f)
                d["tf"] = tf
                frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    return df.sort_values("entry_ts").reset_index(drop=True)


def features(df: pd.DataFrame) -> pd.DataFrame:
    x = pd.DataFrame(index=df.index)
    x["side_long"] = (df["side"] == "long").astype(int)
    x["hour"], x["weekday"] = df["hour"], df["weekday"]
    x["adx"], x["rsi14"] = df["adx"].astype(float), df["rsi14"].astype(float)
    for c in ("with_ema200", "ema50_over_200", "with_supertrend"):
        x[c] = df[c].astype(int)
    cats = pd.get_dummies(df[["key", "tf", "session"]].astype(str), prefix=["key", "tf", "sess"]).astype(int)
    return pd.concat([x, cats], axis=1)


def walk_forward(df: pd.DataFrame, start: str) -> pd.DataFrame:
    X, y = features(df), (df["pnl"] / RISK_USD).clip(-3, 3)
    df = df.copy()
    df["pred"] = np.nan
    months = pd.period_range(pd.Timestamp(start), df["entry_ts"].max().tz_localize(None), freq="M")
    for m in months:
        m0 = pd.Timestamp(m.start_time, tz="UTC")
        m1 = pd.Timestamp(m.end_time, tz="UTC")
        train = df["exit_ts"] < m0  # label known before the month begins
        test = (df["entry_ts"] >= m0) & (df["entry_ts"] <= m1)
        if test.sum() == 0 or train.sum() < 500:
            continue
        model = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=200,
                                              min_samples_leaf=50, random_state=0)
        model.fit(X[train], y[train])
        df.loc[test, "pred"] = model.predict(X[test])
    df["taken"] = df["pred"] > 0
    return df


def evaluate(df: pd.DataFrame, name: str, lo: str, hi: str, seed: int = 20260928) -> dict:
    w = df[(df["entry_ts"] >= pd.Timestamp(lo, tz="UTC")) & (df["entry_ts"] < pd.Timestamp(hi, tz="UTC"))
           & df["pred"].notna()].copy()
    w["month"] = w["entry_ts"].dt.strftime("%Y-%m")
    taken = w[w["taken"]]
    by_month = taken.groupby("month")["pnl"].sum()
    # Random filter: same number taken in each month, drawn uniformly.
    rng = np.random.default_rng(seed)
    groups = [(g["pnl"].to_numpy(), int(g["taken"].sum())) for _, g in w.groupby("month")]
    totals = np.array([sum(rng.choice(p, k, replace=False).sum() for p, k in groups if k) for _ in range(N_RANDOM)])
    out = {
        "window": name, "signals": len(w), "taken": len(taken),
        "take_rate%": round(100 * len(taken) / len(w), 1) if len(w) else None,
        "take_all_pnl": round(w["pnl"].sum()), "taken_pnl": round(taken["pnl"].sum()),
        "taken_per_trade": round(taken["pnl"].mean(), 2) if len(taken) else None,
        "months+%": round(100 * (by_month > 0).mean()) if len(by_month) else None,
        "rnd_p50": round(float(np.percentile(totals, 50))), "rnd_p95": round(float(np.percentile(totals, 95))),
    }
    out["PASS"] = bool(out["taken_pnl"] > 0 and out["taken_pnl"] > out["rnd_p95"] and out["taken"] >= 100
                       and (out["months+%"] or 0) >= 50)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdout-final", action="store_true")
    args = ap.parse_args()
    periods = ["is", "val"] + (["holdout"] if args.holdout_final else [])
    df = load(periods)
    print(f"{len(df):,} trades, {df['entry_ts'].min().date()} .. {df['entry_ts'].max().date()}", flush=True)
    df = walk_forward(df, "2021-01-01")
    rows = [evaluate(df, n, *WINDOWS[n]) for n in (["WF-IS", "WF-VAL"] + (["HOLDOUT"] if args.holdout_final else []))]
    for r in rows:
        print(r, flush=True)
    taken = df[df["taken"]]
    print("\ntaken by strategy (all windows):")
    print(taken.groupby("key")["pnl"].agg(["size", "sum"]).round(0).sort_values("sum").to_string())
    df.to_parquet(CUSTOM / f"ml_filter_predictions{'_holdout' if args.holdout_final else ''}.parquet")


if __name__ == "__main__":
    main()
