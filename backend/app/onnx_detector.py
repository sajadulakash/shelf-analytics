"""DETR-style ONNX detectors (RF-DETR and models exported the same way).

A model of this kind is a folder under ``models/yolo/`` named after the model,
holding one ``.onnx`` file and the ``model_info.json`` written by the export::

    models/yolo/rfdetr_2xl_v4/
        product_detector.onnx
        model_info.json

``model_config`` decides which folders qualify; this module runs them. The
inference follows the export's own ``onnx_predictor.py`` step for step, so the
app reproduces the boxes the model was scored with:

* the whole image is stretched to the model's square input with Lanczos (no
  padding, no tiling - SAHI does not apply: the model was trained and
  evaluated on whole images at this size),
* pixels are scaled to 0-1 and normalised with the export's mean/std,
* the outputs are ``dets`` (normalised cx, cy, w, h per query) and ``labels``
  (class logits per query); sigmoid scores are ranked over queries x classes
  and the top ``num_queries`` above the threshold are kept. DETR models make
  one prediction per object, so there is no NMS step.

Only onnxruntime, numpy and Pillow are needed. No code is ever loaded from a
model folder - only the ``.onnx`` weights and the JSON settings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app import config

logger = logging.getLogger(__name__)

# The export's predictor uses these output names; a model without them is not
# one this module knows how to decode.
REQUIRED_OUTPUTS = ("dets", "labels")


@dataclass
class Box:
    x1: float
    y1: float
    x2: float
    y2: float
    score: float
    class_id: int
    class_name: str


def _providers() -> list[str]:
    """CUDA first when asked for and available; CPU otherwise.

    Only exact-fp32 providers are used, as in the export's predictor: TensorRT
    and other accelerators change the numerics, so they are never picked
    automatically.
    """
    import onnxruntime as ort

    available = ort.get_available_providers()
    wanted = ["CPUExecutionProvider"]
    if config.ONNX_DETECTION_DEVICE.startswith("cuda"):
        wanted.insert(0, "CUDAExecutionProvider")
    return [p for p in wanted if p in available]


def _session_options():
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.log_severity_level = 3  # errors only; the CUDA provider is chatty
    return opts


def _preload_cuda_libraries() -> None:
    """Let onnxruntime find the CUDA/cuDNN libraries torch already ships.

    The backend env has them as pip ``nvidia-*`` packages rather than a system
    CUDA install; without this, onnxruntime would quietly run on the CPU.
    """
    import onnxruntime as ort

    preload = getattr(ort, "preload_dlls", None)
    if preload is None:
        return
    try:
        preload(cuda=True, cudnn=True, msvc=False)
    except Exception as e:  # noqa: BLE001 - CPU still works; the warning below says so
        logger.debug("onnxruntime.preload_dlls failed: %s", e)


class DetrOnnxDetector:
    """One loaded DETR-style ONNX model. Build it from ``model_config.detection_info``."""

    def __init__(self, info: dict):
        import onnxruntime as ort

        self.name = info["name"]
        self.size = info.get("input_size")  # None: read from the .onnx file below
        self.mean = np.asarray(info["mean"], np.float32)
        self.std = np.asarray(info["std"], np.float32)
        self.class_names = list(info["classes"])
        self.threshold = float(info["confidence_threshold"])

        providers = _providers()
        if "CUDAExecutionProvider" in providers:
            _preload_cuda_libraries()
        self.session = ort.InferenceSession(
            str(info["weights"]), _session_options(), providers=providers
        )
        active = self.session.get_providers()
        if config.ONNX_DETECTION_DEVICE.startswith("cuda") and "CUDAExecutionProvider" not in active:
            logger.warning(
                "Detection model %s is running on the CPU: CUDA is not available to onnxruntime "
                "(is onnxruntime-gpu installed?). Expect it to be much slower.",
                self.name,
            )
        logger.info("Loaded ONNX detection model %s on %s", self.name, active[0])

        inputs = self.session.get_inputs()
        outputs = {o.name: o for o in self.session.get_outputs()}
        missing = [n for n in REQUIRED_OUTPUTS if n not in outputs]
        if len(inputs) != 1 or missing:
            raise ValueError(
                f"{self.name}: the ONNX file does not look like an RF-DETR export "
                f"(expects one input and outputs {', '.join(REQUIRED_OUTPUTS)}; "
                f"got outputs {', '.join(outputs) or 'none'})."
            )
        self.input_name = inputs[0].name
        self.output_names = list(REQUIRED_OUTPUTS)

        # The file's own input size wins over a stale model_info.json.
        shape = inputs[0].shape
        fixed = len(shape) == 4 and isinstance(shape[2], int) and shape[2] > 0 and shape[2] == shape[3]
        if fixed and shape[2] != self.size:
            if self.size is not None:
                logger.warning(
                    "%s: model_info.json says input %s but the ONNX file expects %s; using %s.",
                    self.name, self.size, shape[2], shape[2],
                )
            self.size = shape[2]
        if self.size is None:
            raise ValueError(
                f"{self.name}: the input size is not fixed in the ONNX file, so model_info.json "
                'must give it as "input": {"shape": [1, 3, N, N]}.'
            )

        label_dim = outputs["labels"].shape[-1]
        if isinstance(label_dim, int) and label_dim < len(self.class_names):
            raise ValueError(
                f"{self.name}: model_info.json lists {len(self.class_names)} classes but the "
                f"model only outputs {label_dim} class scores."
            )

    def preprocess(self, image: Image.Image) -> np.ndarray:
        image = image.convert("RGB")
        if image.size != (self.size, self.size):
            # Same stretch resize (no padding) that built the training set.
            image = image.resize((self.size, self.size), Image.Resampling.LANCZOS)
        x = (np.asarray(image, np.float32) / 255.0 - self.mean) / self.std
        return x.transpose(2, 0, 1)[None]

    def predict(self, image: Image.Image, threshold: float | None = None) -> list[Box]:
        """Detect on an already upright RGB image; boxes are in its pixel space."""
        threshold = self.threshold if threshold is None else threshold
        w, h = image.size
        dets, logits = self.session.run(self.output_names, {self.input_name: self.preprocess(image)})

        prob = 1.0 / (1.0 + np.exp(-logits[0]))                    # (queries, classes)
        flat = prob.reshape(-1)
        order = np.argsort(-flat, kind="stable")[: dets.shape[1]]  # top-k over queries x classes
        order = order[flat[order] > threshold]
        query, class_id = order // prob.shape[1], order % prob.shape[1]
        keep = class_id < len(self.class_names)                    # extra logit columns are not classes
        query, class_id, scores = query[keep], class_id[keep], flat[order][keep]

        cx, cy, bw, bh = dets[0][query].T                          # normalised cx, cy, w, h
        boxes = np.stack([(cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h], 1)
        boxes = np.clip(boxes, 0, [w, h, w, h])

        return [
            Box(float(b[0]), float(b[1]), float(b[2]), float(b[3]), float(s), int(c), self.class_names[c])
            for b, s, c in zip(boxes, scores, class_id)
        ]


_CACHE: dict[tuple[str, str], DetrOnnxDetector] = {}


def get_detector(info: dict) -> DetrOnnxDetector:
    """Load once per model folder; a changed model_info.json or .onnx reloads it."""
    key = (str(info["folder"]), info["fingerprint_stamp"])
    detector = _CACHE.get(key)
    if detector is None:
        for old in [k for k in _CACHE if k[0] == key[0]]:
            del _CACHE[old]
        if not Path(info["weights"]).exists():
            raise FileNotFoundError(f"Detection model not found: {info['weights']}")
        detector = DetrOnnxDetector(info)
        _CACHE[key] = detector
    return detector
