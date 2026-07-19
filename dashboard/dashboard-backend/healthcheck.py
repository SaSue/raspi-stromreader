#!/usr/bin/env python3
"""Docker health check for the dashboard backend."""

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


HEALTH_URL = os.getenv(
    "BACKEND_HEALTH_URL", "http://127.0.0.1:5000/api/dashboard"
)
TIMEOUT_SECONDS = float(os.getenv("BACKEND_HEALTH_TIMEOUT_SECONDS", "5"))


def check_health(url=HEALTH_URL):
    try:
        with urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                return False, f"backend returned HTTP {response.status}"
            payload = json.load(response)

        if not isinstance(payload, dict) or "timestamp" not in payload:
            return False, "backend returned an unexpected response"
        if payload.get("error"):
            return False, f"backend error: {payload['error']}"
        return True, "backend API is responding"
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
        return False, f"backend check failed: {error}"


def main():
    healthy, message = check_health()
    print(message)
    return 0 if healthy else 1


if __name__ == "__main__":
    sys.exit(main())
