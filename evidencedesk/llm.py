"""HTTP clients for two genuine local llama.cpp model servers."""

import json
from threading import Lock
import time
import requests

from .config import SETTINGS


class ModelUnavailable(RuntimeError):
    pass


class LocalModels:
    def __init__(self, settings=SETTINGS):
        self.settings = settings
        self.generation_lock = Lock()

    def health(self):
        result = {}
        for role, url in [("llm", self.settings.llm_url), ("embeddings", self.settings.embedding_url)]:
            try:
                response = requests.get(url + "/health", timeout=2)
                result[role] = response.ok
            except requests.RequestException:
                result[role] = False
        return result

    def generate_json(self, system, user, schema, max_tokens=320):
        payload = {
            "model": self.settings.model_name,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0.0, "seed": self.settings.seed,
            "max_tokens": max_tokens, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_object", "schema": schema},
        }
        started = time.perf_counter()
        try:
            # One CPU model instance; serialize calls instead of exhausting memory.
            with self.generation_lock:
                response = requests.post(
                    self.settings.llm_url + "/v1/chat/completions", json=payload,
                    timeout=self.settings.llm_timeout,
                )
            response.raise_for_status()
            body = response.json()
            text = body["choices"][0]["message"]["content"]
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("Model returned a non-object JSON value")
            return value, {"seconds": time.perf_counter() - started,
                           "usage": body.get("usage", {})}
        except (requests.RequestException, ValueError, KeyError, IndexError) as error:
            raise ModelUnavailable(
                "The local language model could not return a valid response. "
                "Check that the model server is running, then retry."
            ) from error

    def embed(self, texts):
        try:
            all_vectors = []
            for start in range(0, len(texts), 4):
                response = requests.post(
                    self.settings.embedding_url + "/v1/embeddings",
                    json={"input": texts[start:start + 4], "model": self.settings.embedding_name}, timeout=60,
                )
                response.raise_for_status()
                values = sorted(response.json()["data"], key=lambda item: item["index"])
                all_vectors.extend(item["embedding"] for item in values)
            return all_vectors
        except (requests.RequestException, ValueError, KeyError) as error:
            raise ModelUnavailable(
                "The embedding model is unavailable. Start the embedding server and retry."
            ) from error
