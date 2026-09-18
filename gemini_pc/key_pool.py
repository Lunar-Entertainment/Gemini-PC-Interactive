import os
import time
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from google import genai

logger = logging.getLogger("GeminiKeyPool")


class KeyState:
    MIN_KEY_INTERVAL: float = 4.05  # Ensures <= 14.8 RPM per key (< 15 RPM free-tier hardware cap)

    def __init__(self, key: str, index: int):
        self.key: str = key.strip()
        self.index: int = index
        self.client: Optional[genai.Client] = None
        self.cooldown_until: float = 0.0
        self.success_count: int = 0
        self.error_count: int = 0
        self.last_used: float = 0.0
        self.last_requested_at: float = 0.0

    @property
    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until

    @property
    def remaining_cooldown(self) -> float:
        rem = self.cooldown_until - time.time()
        return max(0.0, round(rem, 1))

    @property
    def seconds_since_last_request(self) -> float:
        if self.last_requested_at <= 0:
            return 999.0
        return time.time() - self.last_requested_at

    @property
    def time_until_safe(self) -> float:
        if not self.is_available:
            return self.remaining_cooldown
        elapsed = time.time() - self.last_requested_at
        return max(0.0, self.MIN_KEY_INTERVAL - elapsed)

    @property
    def masked_key(self) -> str:
        if len(self.key) <= 12:
            return "***"
        return f"{self.key[:6]}...{self.key[-4:]}"

    def get_client(self) -> genai.Client:
        if self.client is None:
            self.client = genai.Client(api_key=self.key)
        return self.client

    def mark_success(self):
        self.success_count += 1
        self.last_used = time.time()

    def mark_rate_limited(self, cooldown_seconds: float = 30.0):
        self.error_count += 1
        self.cooldown_until = time.time() + cooldown_seconds
        logger.warning(
            f"[KeyPool] Key #{self.index + 1} ({self.masked_key}) rate-limited! "
            f"Cooling down for {cooldown_seconds:.1f}s."
        )


class GeminiKeyPool:
    """Manages a pool of Google Gemini API keys with automatic round-robin rotation,
    sub-millisecond rate pacing up to 60 RPM, and instant failover upon 429 errors.
    """

    def __init__(self, keys: Optional[List[str]] = None):
        self._keys: List[KeyState] = []
        self._current_index: int = 0
        self._last_pool_request_at: float = 0.0
        if keys:
            self.set_keys(keys)

    def set_keys(self, raw_keys: List[str]):
        """Sets or replaces the active key pool."""
        cleaned = []
        seen = set()
        for k in raw_keys:
            for part in re.split(r"[\r\n,]+", k):
                val = part.strip().strip('"').strip("'")
                if val and val not in seen and not val.startswith("#"):
                    seen.add(val)
                    cleaned.append(val)

        self._keys = [KeyState(k, i) for i, k in enumerate(cleaned)]
        self._current_index = 0
        for k in self._keys:
            try:
                _ = k.get_client()
            except Exception:
                pass
        logger.info(f"[KeyPool] Initialized with {len(self._keys)} active key(s).")

    def has_keys(self) -> bool:
        return len(self._keys) > 0

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    @property
    def available_keys_count(self) -> int:
        return sum(1 for k in self._keys if k.is_available)

    def get_active_client(self) -> Tuple[genai.Client, int, str]:
        """Returns (genai.Client, key_index, masked_key) to achieve up to 60 RPM throughput.
        
        Paces requests smoothly across all available keys (target: ~1.02s per request across 4 keys),
        strictly ensuring no individual key exceeds 15 RPM.
        """
        if not self._keys:
            raise RuntimeError("No Google Gemini API keys configured in the pool.")

        available = [k for k in self._keys if k.is_available]
        if not available:
            earliest_key = min(self._keys, key=lambda k: k.cooldown_until)
            wait_sec = earliest_key.remaining_cooldown
            logger.warning(
                f"[KeyPool] All {len(self._keys)} keys cooling down. "
                f"Waiting {wait_sec:.1f}s for Key #{earliest_key.index + 1}..."
            )
            if wait_sec > 0:
                time.sleep(wait_sec + 0.2)
            earliest_key.cooldown_until = 0.0
            available = [earliest_key]

        # 1. Select the key in round-robin sequence among available keys
        num_keys = len(self._keys)
        candidate = None
        for offset in range(num_keys):
            idx = (self._current_index + offset) % num_keys
            k = self._keys[idx]
            if k.is_available:
                candidate = k
                self._current_index = (idx + 1) % num_keys
                break

        if candidate is None:
            candidate = available[0]

        client = candidate.get_client()

        # 2. Target aggregate interval across the pool (strictly capped at 60 RPM: >= 1.02s)
        pool_interval = max(4.10 / max(len(available), 1), 1.02)
        elapsed_pool = time.time() - self._last_pool_request_at
        if elapsed_pool < pool_interval:
            time.sleep(pool_interval - elapsed_pool)

        # 3. Enforce per-key safety interval (guarantees <= 14.8 RPM per key: >= 4.05s)
        wait_needed = candidate.time_until_safe
        if wait_needed > 0.01:
            time.sleep(wait_needed)

        now = time.time()
        self._last_pool_request_at = now
        candidate.last_requested_at = now

        return client, candidate.index, candidate.masked_key

    def mark_key_rate_limited(self, index: int, delay_seconds: float = 30.0):
        """Marks a key as rate-limited with a cooldown."""
        if 0 <= index < len(self._keys):
            self._keys[index].mark_rate_limited(delay_seconds)

    def mark_key_success(self, index: int):
        """Records a successful call on the key."""
        if 0 <= index < len(self._keys):
            self._keys[index].mark_success()

    def get_status_summary(self) -> List[Dict[str, Any]]:
        """Returns summary info for all keys in the pool."""
        return [
            {
                "index": k.index + 1,
                "masked": k.masked_key,
                "is_available": k.is_available,
                "remaining_cooldown": k.remaining_cooldown,
                "success_count": k.success_count,
                "error_count": k.error_count,
            }
            for k in self._keys
        ]


# Global key pool instance
key_pool = GeminiKeyPool()
