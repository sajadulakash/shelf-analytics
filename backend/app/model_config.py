"""Active model + label configuration.

Lists the detection and classification (SwinV2) models available under
``models/yolo`` and ``models/swinv2``, and persists the user's choice — which
detection model, which classifier, whether to run SAHI, and which labels count
as *known* (anything else is reported as ``Unknown``). The selection is saved to
``data/model_config.json`` and remembered until reconfigured.

A detection model in ``models/yolo`` is either

* a YOLO ``.pt`` file dropped straight into the folder, run with ultralytics
  (optionally sliced with SAHI), or
* a folder named after the model holding one ``.onnx`` file and the export's
  ``model_info.json`` - an RF-DETR style transformer detector, run with
  ``onnx_detector`` on the whole image (SAHI never applies to it).

A folder that is not a complete model is left off the list and reported by
``detection_problems()`` so the page can say why.
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
# (config_key, model_id) resolved from the registry.
_MODEL_ID_CACHE: tuple[str, str] | None = None


def _is_unknown_label(label: str) -> bool:
    return str(label).strip().casefold().replace("_", "-").startswith("unknown")


# ---------- Registry: detection models ----------
YOLO_FRAMEWORK = "yolo"
DETR_ONNX_FRAMEWORK = "rfdetr-onnx"
FRAMEWORK_LABELS = {YOLO_FRAMEWORK: "YOLO", DETR_ONNX_FRAMEWORK: "RF-DETR"}
MODEL_INFO_FILE = "model_info.json"
# model_info.json "framework" values decoded by onnx_detector. Exports without
# the key are recognised by their outputs (dets + labels) instead.
_DETR_FRAMEWORK_NAMES = {"rfdetr", "rf-detr", "rfdetr-onnx", "rf-detr-onnx", "lw-detr", "detr", "detr-onnx"}
_DETR_OUTPUTS = ("dets", "labels")
_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD = [0.229, 0.224, 0.225]


def _yolo_info(path: Path) -> dict:
    return {
        "name": path.name,
        "framework": YOLO_FRAMEWORK,
        "supports_sahi": True,
        "weights": path,
        "confidence_threshold": None,  # the app's own YOLO/SAHI settings apply
    }


def _three_numbers(value, default: list[float]) -> list[float] | None:
    if value is None:
        return default
    if isinstance(value, list) and len(value) == 3 and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in value
    ):
        return [float(v) for v in value]
    return None


def _stamp(path: Path) -> str:
    st = path.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def _onnx_folder_info(folder: Path) -> tuple[dict | None, str | None]:
    """Read one model folder. Returns (info, None), (None, problem) or (None, None) if unrelated."""
    info_path = folder / MODEL_INFO_FILE
    onnx_files = sorted(p for p in folder.glob("*.onnx") if p.is_file())
    if not info_path.is_file():
        # A folder with neither file is not meant to be a model (e.g. a backup dir).
        return None, (f"{MODEL_INFO_FILE} is missing next to the .onnx file" if onnx_files else None)

    try:
        meta = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"{MODEL_INFO_FILE} could not be read ({e})"
    if not isinstance(meta, dict):
        return None, f"{MODEL_INFO_FILE} must be a JSON object"

    named = meta.get("onnx_file")
    if named:
        if not isinstance(named, str) or Path(named).name != named or not named.endswith(".onnx"):
            return None, '"onnx_file" must be the name of a .onnx file inside the folder'
        weights = folder / named
        if not weights.is_file():
            return None, f"{named} (named in {MODEL_INFO_FILE}) is not in the folder"
    elif not onnx_files:
        return None, "no .onnx file in the folder"
    elif len(onnx_files) > 1:
        return None, f'{len(onnx_files)} .onnx files and {MODEL_INFO_FILE} does not name one ("onnx_file")'
    else:
        weights = onnx_files[0]

    framework = str(meta.get("framework") or "").strip().lower()
    outputs = meta.get("outputs")
    if framework:
        if framework not in _DETR_FRAMEWORK_NAMES:
            return None, f'framework "{meta.get("framework")}" is not supported (RF-DETR style ONNX exports are)'
    elif not (isinstance(outputs, dict) and all(k in outputs for k in _DETR_OUTPUTS)):
        return None, (
            f"{MODEL_INFO_FILE} does not say what kind of model this is: expected the RF-DETR "
            'export\'s "outputs" (dets, labels) or a "framework" entry'
        )

    spec = meta.get("input") if isinstance(meta.get("input"), dict) else {}
    shape = spec.get("shape")
    input_size = None  # None: taken from the .onnx file when it is loaded
    if shape is not None:
        if not (
            isinstance(shape, list) and len(shape) == 4
            and all(isinstance(v, int) and v > 0 for v in shape[1:])
            and shape[1] == 3 and shape[2] == shape[3]
        ):
            return None, 'input "shape" must look like [1, 3, N, N]'
        input_size = shape[2]
    mean = _three_numbers(spec.get("mean"), _IMAGENET_MEAN)
    std = _three_numbers(spec.get("std"), _IMAGENET_STD)
    if mean is None or std is None or not all(v > 0 for v in std):
        return None, 'input "mean" and "std" must each be 3 numbers'

    classes = meta.get("classes")
    if not (isinstance(classes, list) and classes and all(isinstance(c, str) and c.strip() for c in classes)):
        return None, f'{MODEL_INFO_FILE} needs a "classes" list of class names'

    threshold = meta.get("recommended_confidence_threshold")
    if threshold is None and isinstance(meta.get("metrics"), dict):
        threshold = meta["metrics"].get("recommended_confidence_threshold")
    source = "model_info.json"
    if threshold is None:
        threshold, source = config.ONNX_DETECTION_DEFAULT_CONF, "default"
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 < threshold < 1:
        return None, '"recommended_confidence_threshold" must be a number between 0 and 1'

    return {
        "name": folder.name,
        "framework": DETR_ONNX_FRAMEWORK,
        "supports_sahi": False,
        "folder": folder,
        "weights": weights,
        "info_file": info_path,
        "display_name": str(meta.get("model") or "").strip() or None,
        "input_size": input_size,
        "mean": mean,
        "std": std,
        "classes": [c.strip() for c in classes],
        "confidence_threshold": round(float(threshold), 4),
        "threshold_source": source,
        "fingerprint_stamp": f"{_stamp(weights)}|{_stamp(info_path)}",
    }, None


def _scan_detection_models() -> tuple[dict[str, dict], list[dict]]:
    models: dict[str, dict] = {}
    problems: list[dict] = []
    if not config.YOLO_DIR.exists():
        return models, problems
    for path in sorted(config.YOLO_DIR.iterdir()):
        if path.name.startswith((".", "__")):
            continue
        if path.is_file() and path.suffix == ".pt":
            models[path.name] = _yolo_info(path)
        elif path.is_file() and path.suffix == ".onnx":
            problems.append({
                "name": path.name,
                "problem": f"an ONNX model needs its own folder with its {MODEL_INFO_FILE}, "
                           f"e.g. {path.stem}/{path.name}",
            })
        elif path.is_dir():
            info, problem = _onnx_folder_info(path)
            if info:
                models[path.name] = info
            elif problem:
                problems.append({"name": path.name, "problem": problem})
    return models, problems


def list_detection_models() -> list[str]:
    return sorted(_scan_detection_models()[0])


def detection_info(name: str) -> dict | None:
    """Everything the pipeline needs about one detection model, or None."""
    return _scan_detection_models()[0].get(name)


def detection_models() -> list[dict]:
    """JSON-safe description of each detection model, for the configuration page."""
    out = []
    for name, info in sorted(_scan_detection_models()[0].items()):
        out.append({
            "name": name,
            "framework": info["framework"],
            "framework_label": FRAMEWORK_LABELS[info["framework"]],
            "supports_sahi": info["supports_sahi"],
            "display_name": info.get("display_name"),
            "input_size": info.get("input_size"),
            "classes": info.get("classes"),
            "confidence_threshold": info.get("confidence_threshold"),
            "threshold_source": info.get("threshold_source"),
        })
    return out


def detection_problems() -> list[dict]:
    """Things in models/yolo that look like a model but cannot be used, and why."""
    return _scan_detection_models()[1]


def _supports_sahi(name: str) -> bool:
    info = detection_info(name)
    return info is None or info["supports_sahi"]


# ---------- Registry: classification models ----------


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
        "model_id": config.DEFAULT_MODEL_ID,
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
        if str(stored.get("model_id", "")).strip():
            cfg["model_id"] = str(stored["model_id"]).strip()
        valid = set(selectable_labels(cfg["classification_model"]))
        known = [l for l in stored.get("known_labels", []) if l in valid]
        if known:
            cfg["known_labels"] = known

    if not _supports_sahi(cfg["detection_model"]):
        cfg["use_sahi"] = False  # whole-image models (RF-DETR) are never sliced

    _CACHE = dict(cfg)
    return dict(cfg)


def save(update: dict) -> dict:
    global _CACHE, _KEY_CACHE, _MODEL_ID_CACHE
    current = load()

    det = update.get("detection_model") or current["detection_model"]
    cls = update.get("classification_model") or current["classification_model"]
    if det not in list_detection_models():
        raise ValueError(f"Unknown detection model: {det}")
    if cls not in list_classification_models():
        raise ValueError(f"Unknown classification model: {cls}")

    use_sahi = bool(update.get("use_sahi", current["use_sahi"])) and _supports_sahi(det)

    valid = set(selectable_labels(cls))
    known = [l for l in update.get("known_labels", []) if l in valid]
    if not known:
        known = selectable_labels(cls)  # empty selection defaults to "all known"

    saved = {
        "detection_model": det,
        "classification_model": cls,
        "use_sahi": use_sahi,
        "known_labels": known,
        "model_id": str(update.get("model_id") or current["model_id"]).strip()
        or config.DEFAULT_MODEL_ID,
    }
    config.MODEL_CONFIG_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    _CACHE = dict(saved)
    _KEY_CACHE = None
    _MODEL_ID_CACHE = None
    return dict(saved)


# ---------- Active accessors (used by the pipeline) ----------
def active_detection_path() -> Path:
    return detection_path(load()["detection_model"])


def active_detection_info() -> dict:
    """The selected detection model. A missing one is treated as a YOLO file, so
    loading it fails with the usual "model not found" error."""
    name = load()["detection_model"]
    return detection_info(name) or _yolo_info(detection_path(name))


def active_classification_dir() -> Path:
    return classification_dir(load()["classification_model"])


def active_use_sahi() -> bool:
    return load()["use_sahi"]


def active_known_labels() -> list[str]:
    return load()["known_labels"]


def active_model_id() -> str:
    """The label stamped on every detection row and carried to the remote.

    Resolved from the ``model_registry`` table, which maps each unique inference
    setup (``config_key``) to one model_id. A setup registers itself the first
    time it is used, so a model change produces a new model_id automatically
    rather than silently reusing the old one.
    """
    global _MODEL_ID_CACHE
    key = active_config_key()
    if _MODEL_ID_CACHE and _MODEL_ID_CACHE[0] == key:
        return _MODEL_ID_CACHE[1]

    from app import db  # imported here: model_config is used in DB-less contexts too

    cfg = load()
    det = active_detection_info()
    details = {
        "detection_model": cfg["detection_model"],
        "classification_model": cfg["classification_model"],
        "use_sahi": bool(cfg["use_sahi"]),
        "detection_conf": det["confidence_threshold"] or config.DATA_DUMP_DETECTION_CONF,
        "classifier_threshold": config.SWINV2_CONFIDENCE_THRESHOLD,
        "known_label_count": len(cfg["known_labels"]),
    }
    try:
        model_id = db.register_model(key, details, config.DEFAULT_MODEL_ID)
    except Exception:  # noqa: BLE001 - never block inference on the registry
        return cfg.get("model_id") or config.DEFAULT_MODEL_ID

    _MODEL_ID_CACHE = (key, model_id)
    return model_id


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


def _detection_fingerprint(info: dict, cache: dict) -> str:
    if info["framework"] == YOLO_FRAMEWORK:
        return _file_fingerprint(info["weights"], cache)
    # The JSON is part of the model: its threshold, size and normalisation change the boxes.
    parts = [_file_fingerprint(info["weights"], cache), _file_fingerprint(info["info_file"], cache)]
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
    det = active_detection_info()
    cache = _fingerprint_cache()
    before = json.dumps(cache, sort_keys=True)

    parts: dict = {
        "detection_model": cfg["detection_model"],
        "detection_fp": _detection_fingerprint(det, cache),
        "classification_model": cfg["classification_model"],
        "classification_fp": _dir_fingerprint(active_classification_dir(), cache),
        "use_sahi": bool(cfg["use_sahi"]),
        "detection_conf": config.DATA_DUMP_DETECTION_CONF,
        "classifier_threshold": config.SWINV2_CONFIDENCE_THRESHOLD,
        "known_labels": sorted(cfg["known_labels"]),
        "model_id": cfg.get("model_id") or config.DEFAULT_MODEL_ID,
    }
    if det["framework"] != YOLO_FRAMEWORK:
        # Added only for non-YOLO models, so existing YOLO setups keep their key
        # (and their already processed images are not re-inferred).
        parts["detection_framework"] = det["framework"]
        parts["detection_conf"] = det["confidence_threshold"]
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
    det = active_detection_info()
    return {
        "config_key": active_config_key(),
        "detection_model": cfg["detection_model"],
        "detection_framework": det["framework"],
        "detection_conf": det["confidence_threshold"],
        "classification_model": cfg["classification_model"],
        "use_sahi": bool(cfg["use_sahi"]),
        "classifier_threshold": config.SWINV2_CONFIDENCE_THRESHOLD,
        "known_label_count": len(cfg["known_labels"]),
        "model_id": active_model_id(),
    }
