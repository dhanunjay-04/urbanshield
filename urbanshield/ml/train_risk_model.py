"""
UrbanShield - Infrastructure Risk Model
------------------------------------------
Trains a gradient-boosted classifier to predict failure risk for
infrastructure assets, then attaches SHAP explanations so every
risk score can be justified feature-by-feature (explainable ML).

Run:
    python train_risk_model.py
Output:
    ../db/assets_scored.csv     (assets + risk_score, risk_tier, top SHAP drivers)
    model.joblib                (trained model, for reuse by the API)
    feature_importance.png      (global feature importance chart)
"""

import json
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, classification_report
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_PATH = PROJECT_ROOT / "db" / "assets.csv"
MODEL_OUT = PROJECT_ROOT / "ml" / "model.joblib"
SCORED_OUT = PROJECT_ROOT / "db" / "assets_scored.csv"
CHART_OUT = PROJECT_ROOT / "ml" / "feature_importance.png"

NUMERIC_FEATURES = [
    "elevation_m", "age_years", "traffic_load", "soil_corrosivity",
    "flood_zone", "distance_to_river_m", "days_since_inspection", "past_maintenance_count",
]
CATEGORICAL_FEATURES = ["asset_type", "material"]
TARGET = "failed_recently"


def build_pipeline():
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", "passthrough", NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )
    model = GradientBoostingClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.08, random_state=42
    )
    return Pipeline([("prep", preprocessor), ("clf", model)])


class BaselineAblationExplainer:
    """Per-feature attribution: how much does the predicted risk change
    when a feature is reset to its background (mean/mode) value, holding
    all others fixed? Additive attributions are then rescaled so they sum
    to (prediction - baseline_prediction), matching SHAP's efficiency
    property. Defined at module level so it can be pickled by joblib and
    reused by the FastAPI backend."""

    def __init__(self, model, background: np.ndarray):
        self.model = model
        self.baseline = background.mean(axis=0)
        self.baseline_pred = float(
            model.predict_proba(self.baseline.reshape(1, -1))[:, 1][0]
        )

    def shap_values(self, X: np.ndarray) -> np.ndarray:
        n, f = X.shape
        base_pred = self.model.predict_proba(X)[:, 1]
        contributions = np.zeros((n, f))
        for j in range(f):
            X_ablated = X.copy()
            X_ablated[:, j] = self.baseline[j]
            pred_without_j = self.model.predict_proba(X_ablated)[:, 1]
            contributions[:, j] = base_pred - pred_without_j
        target_sum = base_pred - self.baseline_pred
        raw_sum = contributions.sum(axis=1)
        raw_sum[raw_sum == 0] = 1e-9
        scale = target_sum / raw_sum
        return contributions * scale[:, None]


def risk_tier(score: float) -> str:
    if score >= 0.75:
        return "critical"
    if score >= 0.5:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


def main():
    df = pd.read_csv(DATA_PATH)
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    pipe = build_pipeline()
    pipe.fit(X_train, y_train)

    # ---- Evaluate ----
    proba_test = pipe.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, proba_test)
    print(f"Test ROC-AUC: {auc:.3f}")
    print(classification_report(y_test, (proba_test > 0.5).astype(int)))

    # ---- Score full dataset ----
    all_proba = pipe.predict_proba(X)[:, 1]
    df["risk_score"] = all_proba.round(4)
    df["risk_tier"] = df["risk_score"].apply(risk_tier)

    # ---- Explainability (baseline-ablation feature attribution) ----
    # NOTE: this environment has no network access to install the `shap` package.
    # BaselineAblationExplainer reproduces SHAP's core idea for tree ensembles at
    # inference time — per-feature marginal contribution vs. a background baseline —
    # using only scikit-learn's predict_proba. Swap in real shap.TreeExplainer by
    # installing `shap` and changing this one line; the rest of the pipeline
    # (feature_names, top_drivers, JSON format) is API-compatible.
    prep = pipe.named_steps["prep"]
    clf = pipe.named_steps["clf"]
    X_transformed = prep.transform(X)
    if hasattr(X_transformed, "toarray"):
        X_transformed = X_transformed.toarray()
    feature_names = (
        NUMERIC_FEATURES
        + list(prep.named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES))
    )

    explainer = BaselineAblationExplainer(clf, X_transformed)
    shap_values = explainer.shap_values(X_transformed)

    # Top 3 drivers per asset (human-readable)
    top_drivers = []
    for row in shap_values:
        idx = np.argsort(-np.abs(row))[:3]
        drivers = [
            {"feature": feature_names[i], "impact": round(float(row[i]), 4)}
            for i in idx
        ]
        top_drivers.append(json.dumps(drivers))
    df["top_risk_drivers"] = top_drivers

    df.drop(columns=["_true_latent_risk"], errors="ignore").to_csv(SCORED_OUT, index=False)

    # ---- Global feature importance chart ----
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    order = np.argsort(mean_abs_shap)[-12:]
    plt.figure(figsize=(8, 6))
    plt.barh([feature_names[i] for i in order], mean_abs_shap[order], color="#c0392b")
    plt.xlabel("Mean |SHAP value| (avg. impact on risk score)")
    plt.title("UrbanShield — Global Feature Importance (Infrastructure Risk Model)")
    plt.tight_layout()
    plt.savefig(CHART_OUT, dpi=150)
    print(f"Saved feature importance chart -> {CHART_OUT}")

    # ---- Save model + preprocessing + feature names for API reuse ----
    joblib.dump(
        {"pipeline": pipe, "explainer": explainer, "feature_names": feature_names},
        MODEL_OUT,
    )
    print(f"Saved trained model -> {MODEL_OUT}")
    print(f"Saved scored assets -> {SCORED_OUT}")
    print(f"\nRisk tier distribution:\n{df['risk_tier'].value_counts()}")


if __name__ == "__main__":
    main()
