from typing import Optional, Dict, Any
import PluginUtils
from config import HTTP_TIMEOUT_DEFAULT, USER_AGENT

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

BASE_HEADERS = {
    'Accept': 'application/json',
    'X-Requested-With': 'manilua-Plugin',
    'Origin': 'https://store.steampowered.com',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
}

class HTTPClient:
    def __init__(self, timeout: int = HTTP_TIMEOUT_DEFAULT):
        self._client = None
        self._timeout = timeout
        self._cached_headers = None

    def _get_cached_headers(self) -> Dict[str, str]:
        if self._cached_headers is None:
            headers = BASE_HEADERS.copy()

            if STEAM_VERIFICATION_AVAILABLE and get_steam_verification is not None:
                try:
                    verification = get_steam_verification()
                    verification_headers = verification.get_verification_headers()
                    headers.update(verification_headers)
                except Exception as e:
                    logger.warn(f"HTTPClient: Could not add Steam verification headers: {e}")
                    headers['User-Agent'] = USER_AGENT
            else:
                logger.warn("HTTPClient: Steam verification not available, using fallback User-Agent")
                headers['User-Agent'] = USER_AGENT

            self._cached_headers = headers

        return self._cached_headers

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
        try:
            client = self._ensure_client()
            headers = self._get_cached_headers()

            if auth_token:
                headers = headers.copy()
                headers['Authorization'] = f'Bearer {auth_token}'

            response = client.get(url, params=params or {}, headers=headers)
            response.raise_for_status()

            return {
                'success': True,
                'data': response.json(),
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

    def get_binary(self, url: str, params: Optional[Dict[str, Any]] = None, auth_token: Optional[str] = None) -> Dict[str, Any]:
        try:
            client = self._ensure_client()
            headers = self._get_cached_headers()

            if auth_token:
                headers = headers.copy()
                headers['Authorization'] = f'Bearer {auth_token}'

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
        try:
            client = self._ensure_client()
            headers = self._get_cached_headers()

            if auth_token:
                headers = headers.copy()
                headers['Authorization'] = f'Bearer {auth_token}'

            if data:
                headers['Content-Type'] = 'application/json'

            response = client.post(url, json=data or {}, headers=headers)
            response.raise_for_status()

            return {
                'success': True,
                'data': response.text,
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

    def stream_get(self, url: str, **kwargs):
        client = self._ensure_client()
        auth_token = kwargs.pop('auth_token', None)
        params = kwargs.pop('params', None)

        headers = self._get_cached_headers()

        if auth_token:
            headers = headers.copy()
            headers['Authorization'] = f'Bearer {auth_token}'

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
