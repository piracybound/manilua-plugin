from typing import Optional, Dict, Any
import PluginUtils
import time
import random
from config import HTTP_TIMEOUT_DEFAULT, HTTP_MAX_RETRIES, HTTP_BASE_RETRY_DELAY, USER_AGENT

try:
    import httpx
    from httpx import HTTPStatusError, RequestError
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    HTTPStatusError = None
    RequestError = None
    HTTPX_AVAILABLE = False

try:
    from steam_verification import get_steam_verification
    STEAM_VERIFICATION_AVAILABLE = True
except ImportError:
    get_steam_verification = None
    STEAM_VERIFICATION_AVAILABLE = False

logger = PluginUtils.Logger()

class HTTPClient:
    def __init__(self, timeout: int = HTTP_TIMEOUT_DEFAULT):
        self._client = None
        self._timeout = timeout
        self._retry_count = 0

    def _retry_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        max_retries = HTTP_MAX_RETRIES
        base_delay = HTTP_BASE_RETRY_DELAY

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warn(f"HTTPClient: Retrying request to {url} (attempt {attempt + 1}/{max_retries}) after {delay:.1f}s")
                    time.sleep(delay)

                    if 'headers' in kwargs:
                        current_headers = kwargs['headers']
                        if current_headers.get('X-Steam-PID'):
                            if STEAM_VERIFICATION_AVAILABLE and get_steam_verification is not None:
                                try:
                                    verification = get_steam_verification()
                                    fresh_headers = verification.get_verification_headers()
                                    fresh_headers.update({
                                        'Accept': 'application/json',
                                        'Accept-Encoding': 'identity'
                                    })
                                    if 'Authorization' in current_headers:
                                        fresh_headers['Authorization'] = current_headers['Authorization']
                                    kwargs['headers'] = fresh_headers
                                except Exception as e:
                                    logger.warn(f"HTTPClient: Could not refresh Steam verification headers on retry: {e}")
                        else:
                            kwargs['headers'] = {
                                'Accept': 'application/json',
                                'Accept-Encoding': 'identity',
                                'User-Agent': USER_AGENT
                            }

                response = getattr(self._ensure_client(), method.lower())(url, **kwargs)
                response.raise_for_status()

                if method.upper() == 'GET':
                    return {
                        'success': True,
                        'data': response.json(),
                        'status_code': response.status_code
                    }
                else:
                    return {
                        'success': True,
                        'data': response.text,
                        'status_code': response.status_code
                    }

            except Exception as e:
                if attempt == max_retries - 1:
                    if HTTPX_AVAILABLE and HTTPStatusError is not None and isinstance(e, HTTPStatusError):
                        error_msg = f"HTTP {e.response.status_code}: {e.response.text if e.response else 'No response'}"
                        return {
                            'success': False,
                            'error': error_msg,
                            'status_code': e.response.status_code if e.response else None
                        }
                    else:
                        return {
                            'success': False,
                            'error': str(e)
                        }
                else:
                    logger.warn(f"HTTPClient: Attempt {attempt + 1} failed: {str(e)}")
                    continue

        return {
            'success': False,
            'error': 'All retry attempts failed'
        }

    def _build_headers(self, accept_type: str = 'application/json', auth_token: Optional[str] = None) -> Dict[str, str]:
        if STEAM_VERIFICATION_AVAILABLE and get_steam_verification is not None:
            try:
                verification = get_steam_verification()
                headers = verification.get_verification_headers()
                headers.update({
                    'Accept': accept_type,
                    'Accept-Encoding': 'identity'
                })
            except Exception as e:
                logger.warn(f"HTTPClient: Could not add Steam verification headers: {e}")
                headers = {
                    'Accept': accept_type,
                    'Accept-Encoding': 'identity',
                    'User-Agent': USER_AGENT
                }
        else:
            headers = {
                'Accept': accept_type,
                'Accept-Encoding': 'identity',
                'User-Agent': USER_AGENT
            }

        if auth_token:
            headers['Authorization'] = f'Bearer {auth_token}'

        return headers

    def _ensure_client(self):
        if not HTTPX_AVAILABLE:
            raise Exception("httpx library is not available. Please install httpx: pip install httpx")

        if self._client is None:
            try:
                if httpx is None:
                    raise Exception("httpx library is not available. Please install httpx: pip install httpx")
                self._client = httpx.Client(
                    timeout=self._timeout,
                    follow_redirects=True
                )
            except Exception as e:
                logger.error(f'HTTPClient: Failed to initialize HTTPX client: {e}')
                raise
        return self._client

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, auth_token: Optional[str] = None) -> Dict[str, Any]:
        headers = self._build_headers('application/json', auth_token)
        return self._retry_request('GET', url, params=params or {}, headers=headers)

    def get_binary(self, url: str, params: Optional[Dict[str, Any]] = None, auth_token: Optional[str] = None) -> Dict[str, Any]:
        try:
            client = self._ensure_client()
            headers = self._build_headers('application/octet-stream', auth_token)

            response = client.get(url, params=params or {}, headers=headers)
            response.raise_for_status()

            return {
                'success': True,
                'data': response.content,
                'status_code': response.status_code
            }
        except Exception as e:
            if HTTPX_AVAILABLE and HTTPStatusError is not None and isinstance(e, HTTPStatusError):
                error_msg = f"HTTP {e.response.status_code}: {e.response.text if e.response else 'No response'}"
                logger.error(f'HTTPClient: HTTP error for {url}: {error_msg}')
                return {
                    'success': False,
                    'error': error_msg,
                    'status_code': e.response.status_code if e.response else None
                }
            elif HTTPX_AVAILABLE and RequestError is not None and isinstance(e, RequestError):
                error_msg = f"Request error: {str(e)}"
                logger.error(f'HTTPClient: Request error for {url}: {error_msg}')
                return {
                    'success': False,
                    'error': error_msg
                }
            else:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(f'HTTPClient: Unexpected error for {url}: {error_msg}')
                return {
                    'success': False,
                    'error': error_msg
                }

    def post(self, url: str, data: Optional[Dict[str, Any]] = None, auth_token: Optional[str] = None) -> Dict[str, Any]:
        headers = self._build_headers('application/json', auth_token)
        if data:
            headers['Content-Type'] = 'application/json'
        return self._retry_request('POST', url, json=data or {}, headers=headers)

    def stream_get(self, url: str, **kwargs):
        client = self._ensure_client()
        auth_token = kwargs.pop('auth_token', None)
        params = kwargs.pop('params', None)

        headers = self._build_headers('application/octet-stream', auth_token)

        return client.stream('GET', url, params=params, headers=headers, **kwargs)

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.error(f'HTTPClient: Error closing client: {e}')
            finally:
                self._client = None


_global_client: Optional[HTTPClient] = None

def get_global_client() -> HTTPClient:
    global _global_client
    if _global_client is None:
        _global_client = HTTPClient()
    return _global_client

def close_global_client() -> None:
    global _global_client
    if _global_client is not None:
        _global_client.close()
        _global_client = None
