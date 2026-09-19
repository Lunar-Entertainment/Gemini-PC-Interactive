import time
import logging
from collections import deque
from typing import Optional, Callable

logger = logging.getLogger("GeminiRateLimiter")


class RateLimiter:
    """High-performance smooth-pacing rate limiter calibrated for Google's 15 RPM free tier.
    
    Provides:
    - 0-latency instant activation on new tasks (turn 1 fires immediately with 0s wait).
    - Smooth 3.8s inter-request pacing: prevents burst saturation and eliminates 50s freezes.
    - Responsive abort checking: stops waiting within 50ms when agent stop is requested.
    - Strict protection to ensure Google's 15 RPM free-tier limit is never breached.
    """

    def __init__(self, max_rpm: int = 14, window_seconds: float = 60.0, min_spacing: float = 3.8):
        self.max_rpm = max_rpm
        self.window_seconds = window_seconds
        self.min_spacing = min_spacing
        self.request_timestamps: deque = deque()
        self.last_request_time: float = 0.0
        self.cooldown_until: float = 0.0

    def on_new_goal(self):
        """Clears transient pacing and cooldowns when starting a new goal for instant activation."""
        self.cooldown_until = 0.0
        self.last_request_time = 0.0
        now = time.time()
        cutoff = now - self.window_seconds
        while self.request_timestamps and self.request_timestamps[0] <= cutoff:
            self.request_timestamps.popleft()

    def reset_transient_cooldown(self):
        """Cancels any pending 429 sleep or cooldown immediately."""
        self.cooldown_until = 0.0

    def wait_for_slot(self, abort_check: Optional[Callable[[], bool]] = None) -> float:
        """Waits only if necessary to stay safely within the 15 RPM threshold.
        Interrupts immediately if abort_check() returns True.
        Returns the duration waited in seconds.
        """
        if abort_check and abort_check():
            return 0.0

        now = time.time()

        # 1. Check transient 429 cooldown
        if self.cooldown_until > now:
            wait_time = self.cooldown_until - now
        else:
            # 2. Purge timestamps older than window_seconds
            cutoff = now - self.window_seconds
            while self.request_timestamps and self.request_timestamps[0] <= cutoff:
                self.request_timestamps.popleft()

            wait_time = 0.0

            # 3. Check rolling capacity
            if len(self.request_timestamps) >= self.max_rpm:
                oldest = self.request_timestamps[0]
                time_until_free = (oldest + self.window_seconds) - now + 0.1
                if time_until_free > wait_time:
                    wait_time = time_until_free

            # 4. Smooth minimum spacing between requests (3.8s prevents 50s end-of-window freezes)
            if self.last_request_time > 0:
                elapsed = now - self.last_request_time
                if elapsed < self.min_spacing:
                    spacing_wait = self.min_spacing - elapsed
                    if spacing_wait > wait_time:
                        wait_time = spacing_wait

        # 5. Sleep smoothly in 50ms slices checking for abort
        if wait_time > 0.01:
            slept = 0.0
            step_slice = 0.05
            while slept < wait_time:
                if abort_check and abort_check():
                    return slept
                time.sleep(min(step_slice, wait_time - slept))
                slept += step_slice

            now = time.time()
            cutoff = now - self.window_seconds
            while self.request_timestamps and self.request_timestamps[0] <= cutoff:
                self.request_timestamps.popleft()

        self.request_timestamps.append(now)
        self.last_request_time = now
        return wait_time

    def record_429(self, delay: float = 15.0):
        """Applies a temporary cooldown if a remote 429 quota error is encountered."""
        now = time.time()
        self.cooldown_until = now + min(max(delay, 5.0), 30.0)
        logger.warning(f"[RateLimiter] 429 received. Cooldown set to {self.cooldown_until - now:.1f}s.")

    @property
    def current_rpm_usage(self) -> int:
        now = time.time()
        cutoff = now - self.window_seconds
        while self.request_timestamps and self.request_timestamps[0] <= cutoff:
            self.request_timestamps.popleft()
        return len(self.request_timestamps)


# Global rate limiter instance
rate_limiter = RateLimiter(max_rpm=14, window_seconds=60.0, min_spacing=3.8)
