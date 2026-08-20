"""Analyzer protocol and optional CLIP/OpenAI adapters."""

from __future__ import annotations

import base64
import json
import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, List, Optional, Protocol, Sequence, Tuple

from .errors import AnalyzerError, AnalyzerInitializationError, ConfigurationError
from .models import AnalyzerResult


class AnalyzerProtocol(Protocol):
    """The minimal boundary required by the batch orchestrator."""

    def analyze(self, image_path: Path) -> AnalyzerResult:
        ...


def validate_score(value: Any) -> float:
    """Validate the public 0-100 score contract."""

    if isinstance(value, bool):
        raise AnalyzerError("Analyzer score must be a number from 0 to 100")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise AnalyzerError("Analyzer score must be a number from 0 to 100") from exc
    if not math.isfinite(score) or not 0 <= score <= 100:
        raise AnalyzerError("Analyzer score must be finite and between 0 and 100")
    return score


def calculate_clip_score(probabilities: Sequence[float]) -> float:
    """Apply the existing six-prompt CLIP clarity heuristic."""

    if len(probabilities) != 6:
        raise AnalyzerError("CLIP scoring requires six prompt probabilities")
    values = [float(value) for value in probabilities]
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
        raise AnalyzerError("CLIP probabilities must be finite values from 0 to 1")
    sharp, blur, high_quality, low_quality, well_composed, poorly_composed = values
    positive = (sharp * 0.4 + high_quality * 0.3 + well_composed * 0.3) * 100
    negative = (blur * 0.5 + low_quality * 0.3 + poorly_composed * 0.2) * 100
    return validate_score(max(0, min(100, positive - negative + 50)))


def _unwrap_json_code_block(content: str) -> str:
    value = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else value


def parse_openai_response(content: str) -> AnalyzerResult:
    """Parse the documented JSON response, including markdown code fences."""

    if not isinstance(content, str) or not content.strip():
        raise AnalyzerError("OpenAI response was empty")
    try:
        payload = json.loads(_unwrap_json_code_block(content))
    except (TypeError, json.JSONDecodeError) as exc:
        raise AnalyzerError("OpenAI response was not valid JSON") from exc
    if not isinstance(payload, dict) or "score" not in payload:
        raise AnalyzerError("OpenAI response must be an object containing score")
    score = validate_score(payload["score"])
    reasoning = payload.get("reasoning", "")
    if reasoning is None:
        reasoning = ""
    if not isinstance(reasoning, str):
        raise AnalyzerError("OpenAI reasoning must be a string")
    return AnalyzerResult(score=score, reasoning=reasoning)


class CLIPAnalyzer:
    """Lazy-loading local CLIP implementation."""

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32") -> None:
        try:
            import torch
            import torch.nn.functional as functional
            from PIL import Image
            from transformers import CLIPModel, CLIPProcessor
        except Exception as exc:
            raise AnalyzerInitializationError(
                "CLIP dependencies are unavailable; install torch, transformers, and pillow"
            ) from exc

        self._torch = torch
        self._functional = functional
        self._image = Image
        self.model_name = model_name
        try:
            if torch.cuda.is_available():
                self.device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
            self.model = CLIPModel.from_pretrained(model_name).to(self.device)
            self.processor = CLIPProcessor.from_pretrained(model_name)
            self.model.eval()
        except Exception as exc:
            raise AnalyzerInitializationError(
                "Could not load CLIP model %s: %s" % (model_name, exc)
            ) from exc

        self.quality_prompts = [
            "a sharp, clear, in-focus photograph with good detail",
            "a blurry, out-of-focus, motion-blurred image",
            "a high quality professional photograph",
            "a low quality, pixelated, grainy image",
            "a well-composed, visually appealing photo",
            "a poorly composed, unappealing image",
        ]

    def analyze(self, image_path: Path) -> AnalyzerResult:
        try:
            image = self._image.open(str(image_path)).convert("RGB")
            inputs = self.processor(
                text=self.quality_prompts,
                images=image,
                return_tensors="pt",
                padding=True,
            ).to(self.device)
            with self._torch.no_grad():
                outputs = self.model(**inputs)
                probabilities = self._functional.softmax(outputs.logits_per_image, dim=1)[0]
            values = [probabilities[index].item() for index in range(6)]
            score = calculate_clip_score(values)
            reasoning = (
                "Sharp: %.1f%%, Blur: %.1f%%, Quality: %.1f%%, Composition: %.1f%%"
                % (values[0] * 100, values[1] * 100, values[2] * 100, values[4] * 100)
            )
            return AnalyzerResult(score=score, reasoning=reasoning)
        except AnalyzerError:
            raise
        except Exception as exc:
            raise AnalyzerError("Could not analyze %s: %s" % (image_path.name, exc)) from exc


class OpenAIAnalyzer:
    """OpenAI vision adapter with synchronized pacing and strict parsing."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        requests_per_minute: int = 3,
        delay_between_requests: float = 20.0,
        max_retries: int = 5,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_minute <= 0 or delay_between_requests < 0 or max_retries <= 0:
            raise ConfigurationError("OpenAI request limits and retries must be positive")
        try:
            from openai import OpenAI
        except Exception as exc:
            raise AnalyzerInitializationError(
                "OpenAI dependency is unavailable; install the openai package"
            ) from exc
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise AnalyzerInitializationError("OPENAI_API_KEY is required for OpenAI analysis")
        self.client = OpenAI(api_key=self.api_key)
        self.model_name = model
        self.requests_per_minute = requests_per_minute
        self.delay_between_requests = delay_between_requests
        self.max_retries = max_retries
        self._sleep = sleep_fn
        self._request_times: List[float] = []
        self._last_request_time = 0.0
        self._rate_lock = threading.Lock()

    def _wait_for_rate_limit(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            self._request_times = [stamp for stamp in self._request_times if now - stamp < 60]
            if len(self._request_times) >= self.requests_per_minute:
                wait = 60 - (now - min(self._request_times)) + 1
                if wait > 0:
                    self._sleep(wait)
                    now = time.monotonic()
                    self._request_times = [stamp for stamp in self._request_times if now - stamp < 60]
            if self._last_request_time:
                wait = self.delay_between_requests - (now - self._last_request_time)
                if wait > 0:
                    self._sleep(wait)
                    now = time.monotonic()
            self._last_request_time = now
            self._request_times.append(now)

    @staticmethod
    def _encode_image(image_path: Path) -> str:
        with image_path.open("rb") as stream:
            return base64.b64encode(stream.read()).decode("ascii")

    def analyze(self, image_path: Path) -> AnalyzerResult:
        encoded = self._encode_image(image_path)
        request = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Analyze this image and rate its clarity/sharpness on a scale "
                                "of 0-100. Respond with a JSON object containing score and "
                                "brief reasoning."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,%s" % encoded},
                        },
                    ],
                }
            ],
            "max_tokens": 200,
            "temperature": 0.3,
        }
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                self._wait_for_rate_limit()
                response = self.client.chat.completions.create(**request)
                content = response.choices[0].message.content
                return parse_openai_response(content)
            except AnalyzerError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.max_retries:
                    self._sleep(float(2 ** attempt))
        raise AnalyzerError(
            "OpenAI analysis failed for %s after %s attempts: %s"
            % (image_path.name, self.max_retries, last_error)
        )


def create_analyzer(
    analyzer_type: str,
    *,
    api_key: Optional[str] = None,
    model: str = "gpt-4o",
    clip_model: str = "openai/clip-vit-base-patch32",
    requests_per_minute: int = 3,
    delay_between_requests: float = 20.0,
    max_retries: int = 5,
) -> Tuple[AnalyzerProtocol, str]:
    """Create an analyzer lazily and return its identity string."""

    selected = analyzer_type.lower()
    if selected == "clip":
        return CLIPAnalyzer(model_name=clip_model), clip_model
    if selected == "openai":
        return (
            OpenAIAnalyzer(
                api_key=api_key,
                model=model,
                requests_per_minute=requests_per_minute,
                delay_between_requests=delay_between_requests,
                max_retries=max_retries,
            ),
            model,
        )
    raise ConfigurationError("Unknown analyzer %r; choose 'clip' or 'openai'" % analyzer_type)
