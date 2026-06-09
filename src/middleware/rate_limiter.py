"""
Small in-memory rate limiter for MVP API hardening.

This protects demo endpoints from accidental brute force or rapid replay.
It is intentionally simple; a production deployment should move counters to
Redis so limits are shared across gateway replicas.
"""

from collections import defaultdict, deque
from functools import wraps
from time import time

from flask import jsonify, request


_BUCKETS = defaultdict(deque)


def _default_key():
    return request.remote_addr or 'unknown'


def rate_limited(limit, window_seconds, key_func=None):
    """Limit requests by key within a sliding time window."""
    def decorator(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            key = key_func() if key_func else _default_key()
            bucket_key = f'{func.__module__}.{func.__name__}:{key}'
            now = time()
            bucket = _BUCKETS[bucket_key]

            while bucket and now - bucket[0] > window_seconds:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, int(window_seconds - (now - bucket[0])))
                return jsonify({
                    'error': 'Too many requests. Please try again later.',
                    'retry_after_seconds': retry_after
                }), 429

            bucket.append(now)
            return func(*args, **kwargs)
        return wrapped
    return decorator
