import time
import logging
from collections import deque
from typing import Optional

logger = logging.getLogger("GeminiRateLimiter")


class RateLimiter:
    """High-performance sliding-window rate limiter calibrated for Google's 15 RPM free tier.
    
    Provides:
    - 0-latency instant activation (first turns fire immediately with 0 wait time).
    - Dynamic pacing that counts action execution and inference time against the quota window.
    - Strict protection to ensure the 15 RPM hardware limit is never breached (capped at 14 RPM).
    """

    def __init__(self, max_rpm: int = 14, window_seconds: float = 60.0, min_spacing: float = 0.5):
        self.max_rpm = max_rpm
        self.window_seconds = window_seconds
        self.min_spacing = min_spacing
        self.request_timestamps: deque = deque()
        self.last_request_time: float = 0.0

    def wait_for_slot(self) -> float:
        """Waits only if necessary to stay safely within the 14 RPM threshold.
        Returns the duration waited in seconds (0.0 if immediate).
        """
        now = time.time()

        # 1. Purge timestamps older than window_seconds
        cutoff = now - self.window_seconds
        while self.request_timestamps and self.request_timestamps[0] <= cutoff:
            self.request_timestamps.popleft()

        wait_time = 0.0

        # 2. Check if we reached the 14-request capacity in the rolling window
        if len(self.request_timestamps) >= self.max_rpm:
            oldest = self.request_timestamps[0]
            time_until_free = (oldest + self.window_seconds) - now + 0.1
            if time_until_free > wait_time:
                wait_time = time_until_free

        # 3. Enforce minimal burst spacing between requests (e.g. 0.5s)
        if self.last_request_time > 0:
            elapsed = now - self.last_request_time
            if elapsed < self.min_spacing:
                spacing_wait = self.min_spacing - elapsed
                if spacing_wait > wait_time:
                    wait_time = spacing_wait

        # 4. Sleep if needed
        if wait_time > 0.01:
            logger.info(
                f"[RateLimiter] Pacing request ({len(self.request_timestamps)}/{self.max_rpm} RPM in 60s). "
                f"Waiting {wait_time:.2f}s..."
            )
            time.sleep(wait_time)
            now = time.time()
            # Re-purge expired entries after sleeping
            cutoff = now - self.window_seconds
            while self.request_timestamps and self.request_timestamps[0] <= cutoff:
                self.request_timestamps.popleft()

        self.request_timestamps.append(now)
        self.last_request_time = now
        return wait_time

    def record_429(self, delay: float = 20.0):
        """Pushes back the limiter if a remote 429 quota error is encountered."""
        now = time.time()
        logger.warning(f"[RateLimiter] 429 detected. Applying cooldown of {delay:.1f}s.")
        # Saturate the window so the next wait_for_slot pauses for the required duration
        while len(self.request_timestamps) < self.max_rpm:
            self.request_timestamps.appendleft(now - self.window_seconds + delay)

    @property
    def current_rpm_usage(self) -> int:
        now = time.time()
        cutoff = now - self.window_seconds
        while self.request_timestamps and self.request_timestamps[0] <= cutoff:
            self.request_timestamps.popleft()
        return len(self.request_timestamps)


# Global rate limiter instance
rate_limiter = RateLimiter(max_rpm=14, window_seconds=60.0, min_spacing=0.5)
