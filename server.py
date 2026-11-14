"""
SPECTRA — AI Media Forensics Backend API
FastAPI server that:
  - Accepts image uploads and runs real inference
  - Uses Ateeqq/ai-vs-human-image-detector (HuggingFace)
  - Returns real classification results
"""

from __future__ import annotations

import io
import logging
import os
import sys
import threading
from typing import Any, Dict, List, Optional

# FastAPI / Starlette
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Image handling
try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:
    print("ERROR: Pillow is not installed. Run: pip install pillow", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_ID = "Ateeqq/ai-vs-human-image-detector"
CONFIDENCE_THRESHOLD = 0.70   # below this -> Inconclusive
MAX_UPLOAD_BYTES = 20 * 1024 * 1024   # 20 MB
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("spectra")

# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
_model_lock = threading.Lock()
_pipeline = None
_processor = None
_model_error: Optional[str] = None


def _load_model() -> None:
    global _pipeline, _processor, _model_error
    with _model_lock:
        if _pipeline is not None and _processor is not None:
            return
        try:
            log.info("Loading model %s...", MODEL_ID)
            from transformers import AutoImageProcessor, AutoModelForImageClassification

            # Use the model's declared id2label mapping instead of relying on
            # pipeline label formatting, which can vary between Transformers versions.
            _processor = AutoImageProcessor.from_pretrained(MODEL_ID)
            _pipeline = AutoModelForImageClassification.from_pretrained(MODEL_ID)
            _pipeline.eval()
            log.info("Model loaded successfully.")
        except Exception as exc:
            _pipeline = None
            _processor = None
            _model_error = f"{type(exc).__name__}: {exc}"
            log.error("Model failed to load: %s", _model_error)


def get_pipeline():
    if (_pipeline is None or _processor is None) and _model_error is None:
        _load_model()
    if _model_error:
        raise RuntimeError(f"Model unavailable: {_model_error}")
    return _pipeline, _processor


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

def _classify(image: Image.Image) -> Dict[str, Any]:
    import torch

    model, processor = get_pipeline()
    views = [image, ImageOps.mirror(image)]
    view_probabilities: List[List[float]] = []

    with torch.inference_mode():
        for view in views:
            inputs = processor(images=view, return_tensors="pt")
            outputs = model(**inputs)
            probabilities = torch.softmax(outputs.logits, dim=-1)[0].tolist()
            view_probabilities.append([float(score) for score in probabilities])

    if not view_probabilities:
        raise RuntimeError("The classifier returned no prediction views.")

    class_count = len(view_probabilities[0])
    averaged = [
        sum(view[index] for view in view_probabilities) / len(view_probabilities)
        for index in range(class_count)
    ]
    labels = getattr(model.config, "id2label", {}) or {}

    def label_for(index: int) -> str:
        return str(labels.get(index, labels.get(str(index), f"LABEL_{index}"))).strip().lower()

    raw = [
        {"label": label_for(index), "score": round(score, 6)}
        for index, score in enumerate(averaged)
    ]
    raw.sort(key=lambda item: item["score"], reverse=True)

    scores: Dict[str, float] = {}
    for item in raw:
        label = item["label"]
        if label in ("ai", "artificial", "ai-generated", "fake", "synthetic"):
            scores["ai"] = item["score"]
        elif label in ("hum", "human", "human-created", "real", "natural"):
            scores["human"] = item["score"]

    if "ai" not in scores or "human" not in scores:
        raise RuntimeError(
            "The classifier returned unexpected labels: "
            + ", ".join(item["label"] for item in raw)
        )

    ai_score_raw = scores["ai"]
    human_score_raw = scores["human"]
    top_score = max(ai_score_raw, human_score_raw)
    score_margin = abs(ai_score_raw - human_score_raw)

    # Require both a strong top score and separation from the other class.
    # This reduces brittle verdicts on ordinary images outside the training domain.
    directional = top_score >= CONFIDENCE_THRESHOLD and score_margin >= 0.20
    if directional and ai_score_raw >= human_score_raw:
        verdict = "AI-Generated"
    elif directional and human_score_raw > ai_score_raw:
        verdict = "Human-Created"
    else:
        verdict = "Inconclusive"

    ai_pct = ai_score_raw * 100.0
    human_pct = human_score_raw * 100.0

    # Derive percentages rounded to 1 decimal place, ensuring they sum to 100.0%
    ai_score = round(ai_pct, 1)
    human_score = round(100.0 - ai_score, 1)

    return {
        "verdict": verdict,
        "ai_score": ai_score,
        "human_score": human_score,
        "raw_scores": {
            "ai": ai_score_raw,
            "human": human_score_raw,
        },
        "raw_labels": raw,
        "top_score": round(top_score, 6),
        "score_margin": round(score_margin, 6),
        "inference_views": len(view_probabilities),
        "threshold_used": CONFIDENCE_THRESHOLD,
        "model_id": MODEL_ID,
        "disclaimer": (
            f"Classifier scores represent statistical model estimates from {MODEL_ID}, "
            "not conclusive forensic proof of authentic origin or manipulation. "
            "Single-model vision classifiers have documented domain-shift limitations and can produce "
            "false positives on authentic photographs or false negatives on novel generative models. "
            "This result averages original and mirrored image views and requires both a "
            f"{CONFIDENCE_THRESHOLD * 100:.0f}% top score and a 20-point class margin. "
            "Inconclusive results should be reviewed with independent evidence."
        ),
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="SPECTRA AI Media Forensics API", version="1.0.0")

allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    model_status = (
        "loaded" if _pipeline else
        ("error" if _model_error else "loading")
    )
    return {
        "status": "ok",
        "model": MODEL_ID,
        "model_status": model_status,
        "model_error": _model_error,
    }


@app.post("/api/classify")
async def classify_media(file: UploadFile = File(...)):
    image_bytes = await file.read()

    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large. Maximum {MAX_UPLOAD_BYTES // 1024 // 1024} MB.")

    fname = file.filename or "upload"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(415, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXT))}")

    try:
        raw_image = Image.open(io.BytesIO(image_bytes))
        width, height = raw_image.size
        if width * height > MAX_IMAGE_PIXELS:
            raise ValueError(f"Image dimensions exceed the {MAX_IMAGE_PIXELS:,} pixel safety limit.")
        # Correct physical orientation using EXIF before feeding into the vision model
        try:
            raw_image = ImageOps.exif_transpose(raw_image)
        except Exception:
            pass
        image = raw_image.convert("RGB")
    except Exception as exc:
        raise HTTPException(422, f"Cannot decode image: {exc}")

    try:
        result = _classify(image)
    except Exception as exc:
        log.error("Classification failure: %s", exc)
        raise HTTPException(503, f"Inference engine unavailable: {exc}")

    return JSONResponse({"status": "ok", "result": result})


@app.on_event("startup")
async def startup_event():
    log.info("SPECTRA API server starting. Triggering background model load...")
    t = threading.Thread(target=_load_model, daemon=True)
    t.start()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False, log_level="info")
