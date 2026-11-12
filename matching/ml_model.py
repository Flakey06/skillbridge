import csv
import re
from functools import lru_cache
from pathlib import Path

from django.conf import settings


MODEL_FEATURES = (
    "job_role",
    "skills",
    "experience_years",
    "education",
    "certifications",
    "projects_count",
    "salary_expectation",
)
_MODEL = None


def _catalog_path():
    return Path(getattr(settings, "ML_SCREENING_CSV", settings.BASE_DIR / "data" / "AI_Resume_Screening.csv"))


def _model_path():
    return Path(
        getattr(
            settings,
            "ML_MODEL_PATH",
            settings.BASE_DIR / "data" / "ml_models" / "suitability_model.joblib",
        )
    )


def _normalise(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _role_from_title(title):
    title = _normalise(title)
    if any(term in title for term in ("cyber", "security", "ethical hacking")):
        return "Cybersecurity Analyst"
    if any(term in title for term in ("data scientist", "data science")):
        return "Data Scientist"
    if any(term in title for term in ("ai ", "artificial intelligence", "machine learning", "ml ")):
        return "AI Researcher"
    if any(term in title for term in ("software", "backend", "frontend", "developer", "engineer")):
        return "Software Engineer"
    return ""


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _row_features(row):
    return {
        "job_role": row.get("Job Role", ""),
        "skills": _normalise(row.get("Skills", "")),
        "experience_years": _number(row.get("Experience (Years)")),
        "education": row.get("Education", ""),
        "certifications": row.get("Certifications", ""),
        "projects_count": _number(row.get("Projects Count")),
        "salary_expectation": _number(row.get("Salary Expectation ($)")),
    }


def _labelled_rows(path):
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            decision = row.get("Recruiter Decision", "").strip()
            if decision in {"Hire", "Reject"}:
                rows.append((_row_features(row), decision))
    return rows


def _build_model():
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    categorical = ["job_role", "education", "certifications"]
    numeric = ["experience_years", "projects_count", "salary_expectation"]
    preprocessor = ColumnTransformer(
        [
            ("skills", TfidfVectorizer(token_pattern=r"(?u)\b[\w+#.-]+\b"), "skills"),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
            ("numeric", StandardScaler(), numeric),
        ]
    )
    return Pipeline(
        [
            ("features", preprocessor),
            ("classifier", LogisticRegression(max_iter=1000, random_state=42)),
        ]
    )


@lru_cache(maxsize=1)
def _train(path):
    import pandas as pd
    rows = _labelled_rows(path)
    if len(rows) < 10:
        raise ValueError("The ML screening dataset must contain at least 10 labelled rows.")

    feature_rows = pd.DataFrame([features for features, _label in rows], columns=MODEL_FEATURES)
    labels = [label for _features, label in rows]
    model = _build_model()
    model.fit(feature_rows, labels)
    return model


def evaluate_model(path=None):
    """Evaluate the baseline on a held-out stratified portion of the CSV."""
    import pandas as pd
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from sklearn.model_selection import train_test_split

    dataset_path = Path(path) if path else _catalog_path()
    rows = _labelled_rows(dataset_path)
    if len(rows) < 10:
        raise ValueError("The ML screening dataset must contain at least 10 labelled rows.")

    feature_rows = pd.DataFrame([features for features, _label in rows], columns=MODEL_FEATURES)
    labels = pd.Series([label for _features, label in rows])
    train_features, test_features, train_labels, test_labels = train_test_split(
        feature_rows,
        labels,
        test_size=0.2,
        random_state=42,
        stratify=labels,
    )
    model = _build_model()
    model.fit(train_features, train_labels)
    predictions = model.predict(test_features)
    probabilities = model.predict_proba(test_features)[:, model.classes_.tolist().index("Hire")]
    positive_rate = float((labels == "Hire").mean())
    return {
        "records": len(rows),
        "train_records": len(train_features),
        "test_records": len(test_features),
        "hire_rate": round(positive_rate, 4),
        "majority_baseline_accuracy": round(max(positive_rate, 1 - positive_rate), 4),
        "accuracy": round(accuracy_score(test_labels, predictions), 4),
        "balanced_accuracy": round(balanced_accuracy_score(test_labels, predictions), 4),
        "precision": round(precision_score(test_labels, predictions, pos_label="Hire", zero_division=0), 4),
        "recall": round(recall_score(test_labels, predictions, pos_label="Hire", zero_division=0), 4),
        "roc_auc": round(roc_auc_score((test_labels == "Hire").astype(int), probabilities), 4),
        "excluded_fields": ["AI Score (0-100)", "Name", "Resume_ID", "Recruiter Decision"],
    }


def initialise_model():
    global _MODEL
    if _MODEL is None:
        model_path = _model_path()
        if model_path.exists():
            import joblib

            _MODEL = joblib.load(model_path)
        else:
            _MODEL = train_and_persist_model()
    return _MODEL


def train_and_persist_model():
    """Train the full baseline and persist it as a Joblib artifact."""
    import joblib

    model_path = _model_path()
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model = _train(_catalog_path())
    temporary_path = model_path.with_suffix(".joblib.tmp")
    joblib.dump(model, temporary_path)
    temporary_path.replace(model_path)
    return model


def _candidate_features(candidate, job):
    from candidates.services import merge_completed_certifications

    profile = getattr(candidate, "profile", None)
    data = merge_completed_certifications(
        candidate,
        getattr(profile, "profile_data", {}) if profile else {},
    )
    candidate_profile = getattr(candidate, "candidate_profile", None)
    return {
        "job_role": _role_from_title(job.title),
        "skills": _normalise(data.get("skills") or getattr(candidate_profile, "technical_skills", "")),
        "experience_years": _number(data.get("experience_years"), _extract_years(data.get("experience"))),
        "education": data.get("education", "") or getattr(candidate_profile, "education_level", ""),
        "certifications": data.get("certifications", "") or getattr(candidate_profile, "certifications", ""),
        "projects_count": _number(data.get("projects_count")),
        "salary_expectation": _number(data.get("salary_expectation")),
    }


def _extract_years(value):
    match = re.search(r"\b(\d+)\s*(?:\+|years?|yrs?)\b", str(value or "").casefold())
    return float(match.group(1)) if match else 0.0


def predict_suitability(candidate, job):
    if _MODEL is None:
        initialise_model()
    import pandas as pd

    features = _candidate_features(candidate, job)
    feature_row = pd.DataFrame([features], columns=MODEL_FEATURES)
    probability = float(_MODEL.predict_proba(feature_row)[0][_MODEL.classes_.tolist().index("Hire")])
    score = round(probability * 100)
    if score >= 80:
        label = "High predicted suitability"
    elif score >= 60:
        label = "Moderate predicted suitability"
    else:
        label = "Lower predicted suitability"
    return {
        "score": score,
        "label": label,
        "job_role": features["job_role"] or "General role",
        "model_name": "Controlled demo classifier",
        "note": "Prediction based on the screening dataset; it is not a hiring decision.",
    }
