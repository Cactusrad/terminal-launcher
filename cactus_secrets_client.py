"""Cactus Secrets client — read-only helper for consumer services.

Usage:
    from cactus_secrets_client import SecretsClient

    client = SecretsClient(
        url='http://localhost:9020',  # via SSH tunnel or LAN
        token=os.environ['SECRETS_TOKEN'],
    )
    twilio_sid = client.get('twilio', 'account_sid')
"""
import logging
import threading
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)


class SecretNotFoundError(KeyError):
    pass


class SecretsClient:
    """Thread-safe client with 5-minute in-memory cache."""

    def __init__(
        self,
        url: str,
        token: str,
        cache_ttl: int = 300,
        timeout: float = 3.0,
    ):
        if not url or not token:
            raise ValueError("SecretsClient requires both url and token")
        self._url = url.rstrip('/')
        self._token = token
        self._ttl = cache_ttl
        self._timeout = timeout
        self._cache: dict[tuple[str, str], tuple[str, float]] = {}
        self._lock = threading.Lock()

    def _headers(self) -> dict:
        return {'Authorization': f'Bearer {self._token}'}

    def get(self, namespace: str, key: str, default: Optional[str] = None) -> str:
        cache_key = (namespace, key)
        now = time.monotonic()

        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and (now - cached[1]) < self._ttl:
                return cached[0]

        try:
            resp = requests.get(
                f'{self._url}/secrets/{namespace}/{key}',
                headers=self._headers(),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            if default is not None:
                log.warning("SecretsClient network error for %s/%s: %s (returning default)", namespace, key, exc)
                return default
            raise

        if resp.status_code == 404:
            if default is not None:
                return default
            raise SecretNotFoundError(f'{namespace}/{key}')
        if resp.status_code != 200:
            raise RuntimeError(f'secrets server error {resp.status_code}: {resp.text[:200]}')

        value = resp.json()['value']
        with self._lock:
            self._cache[cache_key] = (value, now)
        return value

    def invalidate(self, namespace: Optional[str] = None, key: Optional[str] = None) -> None:
        with self._lock:
            if namespace is None:
                self._cache.clear()
            elif key is None:
                self._cache = {k: v for k, v in self._cache.items() if k[0] != namespace}
            else:
                self._cache.pop((namespace, key), None)
