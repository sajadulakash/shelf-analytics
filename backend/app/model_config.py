"""Active model + label configuration.

Lists the detection (YOLO) and classification (SwinV2) models available under
``models/yolo`` and ``models/swinv2``, and persists the user's choice — which
detection model, which classifier, whether to run SAHI, and which labels count
as *known* (anything else is reported as ``Unknown``). The selection is saved to
``data/model_config.json`` and remembered until reconfigured.
"""

from __future__ import annotations

import json
from pathlib import Path

from app import config

# In-memory cache, invalidated on save().
_CACHE: dict | None = None


def _is_unknown_label(label: str) -> bool:
    return str(label).strip().casefold().replace("_", "-").startswith("unknown")


# ---------- Registry ----------
def list_detection_models() -> list[str]:
    if not config.YOLO_DIR.exists():
        return []
    return sorted(p.name for p in config.YOLO_DIR.glob("*.pt"))


def list_classification_models() -> list[str]:
    if not config.SWINV2_DIR.exists():
        return []
    return sorted(
        p.name
        for p in config.SWINV2_DIR.iterdir()
        if p.is_dir() and (p / "config.json").exists()
    )


def detection_path(name: str) -> Path:
    return config.YOLO_DIR / name


def classification_dir(name: str) -> Path:
    return config.SWINV2_DIR / name


def labels_for(classifier_name: str) -> list[str]:
    """All class labels declared in a classifier's config.json, in id order."""
    cfg_path = classification_dir(classifier_name) / "config.json"
    if not cfg_path.exists():
        return []
    payload = json.loads(cfg_path.read_text(encoding="utf-8"))
    id2label = payload.get("id2label", {})
    if not isinstance(id2label, dict) or not id2label:
        return []
    ordered = sorted((int(k), str(v)) for k, v in id2label.items())
    return [label for _, label in ordered]


def selectable_labels(classifier_name: str) -> list[str]:
    """Real product labels (excludes the always-Unknown ``unknown*`` class)."""
    return [label for label in labels_for(classifier_name) if not _is_unknown_label(label)]


# ---------- Persisted config ----------
def _defaults() -> dict:
    dets = list_detection_models()
    clss = list_classification_models()
    det = dets[0] if dets else ""
    cls = clss[0] if clss else ""
    return {
        "detection_model": det,
        "classification_model": cls,
        "use_sahi": config.USE_SAHI,
        "known_labels": selectable_labels(cls) if cls else [],
    }


def load() -> dict:
    global _CACHE
    if _CACHE is not None:
        return dict(_CACHE)

    stored = {}
    if config.MODEL_CONFIG_FILE.exists():
        try:
            stored = json.loads(config.MODEL_CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            stored = {}

    cfg = _defaults()
    if isinstance(stored, dict):
        if stored.get("detection_model") in list_detection_models():
            cfg["detection_model"] = stored["detection_model"]
        if stored.get("classification_model") in list_classification_models():
            cfg["classification_model"] = stored["classification_model"]
        if isinstance(stored.get("use_sahi"), bool):
            cfg["use_sahi"] = stored["use_sahi"]
        valid = set(selectable_labels(cfg["classification_model"]))
        known = [l for l in stored.get("known_labels", []) if l in valid]
        if known:
            cfg["known_labels"] = known

    _CACHE = dict(cfg)
    return dict(cfg)


def save(update: dict) -> dict:
    global _CACHE
    current = load()

    det = update.get("detection_model") or current["detection_model"]
    cls = update.get("classification_model") or current["classification_model"]
    if det not in list_detection_models():
        raise ValueError(f"Unknown detection model: {det}")
    if cls not in list_classification_models():
        raise ValueError(f"Unknown classification model: {cls}")

    use_sahi = bool(update.get("use_sahi", current["use_sahi"]))

    valid = set(selectable_labels(cls))
    known = [l for l in update.get("known_labels", []) if l in valid]
    if not known:
        known = selectable_labels(cls)  # empty selection defaults to "all known"

    saved = {
        "detection_model": det,
        "classification_model": cls,
        "use_sahi": use_sahi,
        "known_labels": known,
    }
    config.MODEL_CONFIG_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    _CACHE = dict(saved)
    return dict(saved)


# ---------- Active accessors (used by the pipeline) ----------
def active_detection_path() -> Path:
    return detection_path(load()["detection_model"])


def active_classification_dir() -> Path:
    return classification_dir(load()["classification_model"])


def active_use_sahi() -> bool:
    return load()["use_sahi"]


def active_known_labels() -> list[str]:
    return load()["known_labels"]
