"""Resume–job text relevance predicted by TF-IDF and Ridge regression."""

import csv
from functools import lru_cache
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "job_resume_fit.csv"
MAX_DATASET_ROWS = 20000


@lru_cache(maxsize=1)
def _trained_model(dataset_mtime):
   try:
       from sklearn.feature_extraction.text import TfidfVectorizer
       from sklearn.linear_model import Ridge
       from sklearn.pipeline import make_pipeline
   except ImportError:
       return None

   texts = []
   labels = []
   try:
       with DATASET_PATH.open(newline="", encoding="utf-8") as dataset:
           for row in csv.DictReader(dataset):
               target = row.get("ai_match_score", "").strip()
               resume = row.get("resume_text", "").strip()
               job = row.get("job_text", "").strip()
               if not target or not resume or not job:
                   continue
               texts.append(f"resume: {resume} job: {job}")
               labels.append(float(target))
               if len(texts) >= MAX_DATASET_ROWS:
                   break
   except (OSError, UnicodeError, ValueError):
       return None
   if len(texts) < 10:
       return None
   model = make_pipeline(
       TfidfVectorizer(
           max_features=30000,
           ngram_range=(1, 2),
           min_df=2,
           sublinear_tf=True,
       ),
       Ridge(alpha=2.0),
   )
   model.fit(texts, labels)
   return model, len(texts)


def predict_ai_compatibility(resume_text, job_text, fallback_score=None):
   """Predict text relevance. The legacy fallback argument is intentionally ignored."""
   try:
       dataset_mtime = DATASET_PATH.stat().st_mtime_ns
   except OSError:
       dataset_mtime = 0
   trained = _trained_model(dataset_mtime)
   if trained is None:
       return None, {
           "mode": "unavailable",
           "reason": "Resume–Job Relevance is unavailable because its model could not be loaded or trained.",
       }
   model, example_count = trained
   prediction = max(
       0,
       min(100, round(float(model.predict([f"resume: {resume_text} job: {job_text}"])[0]))),
   )
   return prediction, {
       "mode": "dataset",
       "reason": f"Trained from {example_count:,} dataset rows using resume and job text.",
   }
