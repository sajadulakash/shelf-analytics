"""Active model + label configuration.

Lists the detection (YOLO) and classification (SwinV2) models available under
``models/yolo`` and ``models/swinv2``, and persists the user's choice — which
detection model, which classifier, whether to run SAHI, and which labels count
as *known* (anything else is reported as ``Unknown``). The selection is saved to
``data/model_config.json`` and remembered until reconfigured.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app import config

# In-memory cache, invalidated on save().
_CACHE: dict | None = None
# Derived identity of the active setup (see active_config_key).
_KEY_CACHE: str | None = None


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
    global _CACHE, _KEY_CACHE
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
    _KEY_CACHE = None
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


# ---------- Identity of the active setup ----------
# The Data Dump pipeline skips an image it has already processed, but "already
# processed" only means something if the setup is provably the same one. A model
# *name* is not enough: retraining and overwriting best.pt would keep the name
# and silently serve stale labels. So the key below covers the weights' actual
# contents plus every setting that changes what gets written to the database.


def _fingerprint_cache() -> dict:
    path = config.MODEL_FINGERPRINT_FILE
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_fingerprint_cache(cache: dict) -> None:
    try:
        config.MODEL_FINGERPRINT_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass  # the cache is an optimisation; losing it only costs a re-hash


def _file_fingerprint(path: Path, cache: dict) -> str:
    """Content hash of one file, cached against its size + mtime.

    Hashing the bytes (rather than trusting size/mtime alone) means a model
    that is merely re-copied or re-downloaded keeps its identity, while a
    genuinely different file always gets a new one.
    """
    if not path.exists():
        return "missing"
    stat = path.stat()
    key = str(path)
    stamp = [stat.st_size, stat.st_mtime_ns]
    hit = cache.get(key)
    if isinstance(hit, dict) and hit.get("stamp") == stamp and hit.get("sha256"):
        return hit["sha256"]

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    sha = digest.hexdigest()
    cache[key] = {"stamp": stamp, "sha256": sha}
    return sha


def _dir_fingerprint(model_dir: Path, cache: dict) -> str:
    """Content hash of the files in a classifier dir that affect its output."""
    parts = [
        _file_fingerprint(model_dir / name, cache)
        for name in ("config.json", "model.safetensors", "preprocessor_config.json")
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def active_config_key() -> str:
    """Stable id for "this exact inference setup".

    Two runs share a key only if the same weights, the same detection mode and
    the same thresholds/labels would produce the same rows. Change any of them
    and previously processed images stop matching, so they are re-inferred
    instead of being wrongly skipped.
    """
    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE

    cfg = load()
    cache = _fingerprint_cache()
    before = json.dumps(cache, sort_keys=True)

    parts: dict = {
        "detection_model": cfg["detection_model"],
        "detection_fp": _file_fingerprint(active_detection_path(), cache),
        "classification_model": cfg["classification_model"],
        "classification_fp": _dir_fingerprint(active_classification_dir(), cache),
        "use_sahi": bool(cfg["use_sahi"]),
        "detection_conf": config.DATA_DUMP_DETECTION_CONF,
        "classifier_threshold": config.SWINV2_CONFIDENCE_THRESHOLD,
        "known_labels": sorted(cfg["known_labels"]),
    }
    if cfg["use_sahi"]:
        # Slicing parameters change the detections themselves, so they are part
        # of the identity only when slicing is actually on.
        parts["sahi"] = {
            "slice": [config.SAHI_SLICE_WIDTH, config.SAHI_SLICE_HEIGHT],
            "overlap": config.SAHI_OVERLAP_RATIO,
            "conf": config.SAHI_CONFIDENCE_THRESHOLD,
            "postprocess": config.SAHI_POSTPROCESS_TYPE,
            "metric": config.SAHI_MATCH_METRIC,
            "threshold": config.SAHI_MATCH_THRESHOLD,
        }

    if json.dumps(cache, sort_keys=True) != before:
        _save_fingerprint_cache(cache)

    blob = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    _KEY_CACHE = hashlib.sha256(blob.encode()).hexdigest()[:32]
    return _KEY_CACHE


def active_config_summary() -> dict:
    """Human-readable version of what the config key stands for."""
    cfg = load()
    return {
        "config_key": active_config_key(),
        "detection_model": cfg["detection_model"],
        "classification_model": cfg["classification_model"],
        "use_sahi": bool(cfg["use_sahi"]),
        "classifier_threshold": config.SWINV2_CONFIDENCE_THRESHOLD,
        "known_label_count": len(cfg["known_labels"]),
    }
