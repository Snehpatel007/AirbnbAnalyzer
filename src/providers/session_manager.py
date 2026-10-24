import re
import json
import logging
import shlex
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
import httpx
from config.settings import BASE_DIR

logger = logging.getLogger(__name__)
SESSION_FILE = BASE_DIR / "config" / "airbnb_session.json"


class AirbnbSessionManager:
    """
    Manages Airbnb web session credentials, cookies, and dynamic API keys.
    Provides:
    1. Automatic guest session bootstrapping (zero manual input needed).
    2. Parsing and importing fresh DevTools curl commands when needed.
    3. Persistent caching in config/airbnb_session.json.
    """

    DEFAULT_API_KEY = "d306zoyjsyarp7ifhu67rjxn52tv0t20"
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    def __init__(self, session_path: Optional[Path] = None):
        self.session_path = session_path or SESSION_FILE

    def load_session(self) -> Dict[str, Any]:
        """Loads cached session from disk if valid and not older than 24h."""
        if self.session_path.exists():
            try:
                with open(self.session_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                updated_at_str = data.get("updated_at")
                if updated_at_str:
                    updated_at = datetime.fromisoformat(updated_at_str)
                    if datetime.utcnow() - updated_at < timedelta(hours=24):
                        return data
            except Exception as e:
                logger.warning(f"Failed to read session file: {e}")
        return self.bootstrap_guest_session()

    def bootstrap_guest_session(self) -> Dict[str, Any]:
        """
        Visits Airbnb India homepage to automatically capture fresh guest cookies,
        datadome / bev identifiers, and the dynamic active API key.
        """
        logger.info("Bootstrapping fresh Airbnb guest session...")
        headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept-Language": "en-IN,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        }

        cookies_dict = {}
        api_key = self.DEFAULT_API_KEY

        try:
            with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as client:
                resp = client.get("https://www.airbnb.co.in")
                if resp.status_code == 200:
                    for k, v in resp.cookies.items():
                        cookies_dict[k] = v

                    # Extract public client API key from page bundle
                    key_match = re.search(r'\"key\":\"([a-zA-Z0-9_-]{30,40})\"', resp.text)
                    if key_match:
                        api_key = key_match.group(1)

                    logger.info(f"Successfully bootstrapped guest session with {len(cookies_dict)} cookies.")
                else:
                    logger.warning(f"Homepage bootstrap returned HTTP {resp.status_code}")
        except Exception as e:
            logger.error(f"Error during guest session bootstrap: {e}")

        session_data = {
            "api_key": api_key,
            "cookies": cookies_dict,
            "headers": {
                "User-Agent": self.DEFAULT_USER_AGENT,
                "Accept-Language": "en-IN,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "X-Airbnb-API-Key": api_key,
                "X-Airbnb-GraphQL-Platform": "web",
                "X-Airbnb-GraphQL-Platform-Client": "minimalist-niobe",
                "X-CSRF-Without-Token": "1",
            },
            "source": "AUTO_BOOTSTRAP",
            "updated_at": datetime.utcnow().isoformat(),
        }

        self.save_session(session_data)
        return session_data

    def save_session(self, data: Dict[str, Any]) -> None:
        """Saves session data to disk."""
        try:
            self.session_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.session_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist session to {self.session_path}: {e}")

    def update_from_curl(self, curl_cmd: str) -> Dict[str, Any]:
        """
        Parses a cURL command captured from browser DevTools, extracts all headers,
        cookies, API key, and GraphQL persisted query hash, and updates the session store.
        """
        headers: Dict[str, str] = {}
        cookies: Dict[str, str] = {}
        api_key = self.DEFAULT_API_KEY
        query_hash = None

        # Regex fallback parser in case shlex encounters unescaped symbols
        header_matches = re.findall(r"-H\s+['\"]([^'\"]+)['\"]", curl_cmd, re.IGNORECASE)
        for h in header_matches:
            if ":" in h:
                k, v = h.split(":", 1)
                k_clean = k.strip()
                v_clean = v.strip()
                headers[k_clean] = v_clean
                if k_clean.lower() == "x-airbnb-api-key":
                    api_key = v_clean

        # Cookie matches from -b or -H 'Cookie: ...'
        cookie_header = headers.get("Cookie") or headers.get("cookie")
        cookie_matches = re.findall(r"-b\s+['\"]([^'\"]+)['\"]", curl_cmd)
        cookie_str = cookie_header or (cookie_matches[0] if cookie_matches else "")
        if cookie_str:
            for pair in cookie_str.split(";"):
                if "=" in pair:
                    ck, cv = pair.strip().split("=", 1)
                    cookies[ck.strip()] = cv.strip()

        # Check for persistedQuery sha256Hash
        hash_match = re.search(r"StaysSearch/([a-f0-9]{64})", curl_cmd)
        if hash_match:
            query_hash = hash_match.group(1)
        else:
            hash_match2 = re.search(r'"sha256Hash"\s*:\s*"([a-f0-9]{64})"', curl_cmd)
            if hash_match2:
                query_hash = hash_match2.group(1)

        session_data = {
            "api_key": api_key,
            "cookies": cookies,
            "headers": headers,
            "query_hash": query_hash,
            "source": "DEVTOOLS_CURL_IMPORT",
            "updated_at": datetime.utcnow().isoformat(),
        }

        self.save_session(session_data)
        logger.info(f"Updated Airbnb session from curl with {len(cookies)} cookies and API key.")
        return session_data


session_manager = AirbnbSessionManager()
