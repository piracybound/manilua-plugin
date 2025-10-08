import json
import time
from typing import Dict, Any, Optional
import PluginUtils
from http_client import get_global_client
from config import API_BASE_URL, API_USER_ID_CACHE_TTL

logger = PluginUtils.Logger()

class APIManager:
    def __init__(self, backend_path: str):
        self.backend_path = backend_path
        self._api_key: Optional[str] = None
        self._user_id_cache: Optional[Dict[str, Any]] = None
        self._user_id_cache_time: float = 0
        self._cache_ttl: int = API_USER_ID_CACHE_TTL

    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key
        self._user_id_cache = None
        self._user_id_cache_time = 0

    def get_api_key(self) -> Optional[str]:
        return self._api_key

    def check_availability(self, appid: int, endpoint: str = "") -> Dict[str, Any]:
        try:
            client = get_global_client()
            api_key = self.get_api_key()
            result = client.get(f'{API_BASE_URL}/check-availability', {
                'appid': appid,
                'endpoint': endpoint
            }, auth_token=api_key)

            if result['success']:
                try:
                    if isinstance(result['data'], str):
                        data = json.loads(result['data'])
                    else:
                        data = result['data']

                    if 'data' in data and isinstance(data['data'], dict):
                        availability_data = data['data']
                    else:
                        availability_data = data

                    response = {
                        'success': True,
                        'available': availability_data.get('available', False),
                        'endpoint': endpoint
                    }
                    if 'debug' in availability_data:
                        response['debug'] = availability_data['debug']

                    return response
                except json.JSONDecodeError:
                    return {'success': False, 'error': 'Invalid response format'}
            else:
                return {'success': False, 'error': result['error']}

        except Exception as e:
            logger.error(f'APIManager: Error checking availability for {appid}: {e}')
            return {'success': False, 'error': str(e)}

    def fetch_available_endpoints(self) -> Dict[str, Any]:
        try:
            client = get_global_client()
            api_key = self.get_api_key()

            result = client.get(f'{API_BASE_URL}/endpoint-rate-limit', {
                'endpoint': 'all'
            }, auth_token=api_key)

            if result['success']:
                try:
                    if isinstance(result['data'], str):
                        data = json.loads(result['data'])
                    else:
                        data = result['data']
                    endpoints = []

                    if isinstance(data, dict):
                        for endpoint_name, endpoint_info in data.items():
                            if isinstance(endpoint_info, dict) and endpoint_info.get('enabled', False):
                                endpoints.append(endpoint_name.replace('/api/', ''))

                    return {
                        'success': True,
                        'endpoints': endpoints if endpoints else ['oureveryday', 'ryuu', 'manilua', 'donation']
                    }
                except json.JSONDecodeError as e:
                    logger.warn(f'APIManager: Failed to parse endpoints response: {e}')
                    return {'success': False, 'error': 'Invalid response format'}
            else:
                return {'success': False, 'error': result.get('error', 'Unknown error')}

        except Exception as e:
            logger.error(f'APIManager: Error fetching endpoints: {e}')
            return {'success': False, 'error': str(e)}

    def get_download_endpoints(self) -> list:
        try:
            result = self.fetch_available_endpoints()
            if result['success'] and result['endpoints']:
                return result['endpoints']
        except Exception as e:
            logger.warn(f'APIManager: Failed to fetch dynamic endpoints: {e}')

        fallback_endpoints = ['oureveryday', 'ryuu', 'manilua', 'donation']
        return fallback_endpoints

    def get_user_id(self, force_refresh: bool = False) -> Dict[str, Any]:
        now = time.time()

        if not force_refresh and self._user_id_cache and (now - self._user_id_cache_time) < self._cache_ttl:
            return self._user_id_cache

        result = self._fetch_user_id()

        if result.get('success'):
            self._user_id_cache = result
            self._user_id_cache_time = now

        return result

    def _fetch_user_id(self) -> Dict[str, Any]:
        try:
            client = get_global_client()
            api_key = self.get_api_key()

            if not api_key:
                return {'success': False, 'error': 'No API key available'}

            result = client.post(f'{API_BASE_URL}/validate-api-key', {'key': api_key})

            if result['success']:
                try:
                    if not result['data'] or result['data'].strip() == '':
                        logger.error('APIManager: Empty response from API')
                        return {'success': False, 'error': 'Empty response from API'}

                    data = json.loads(result['data'])

                    if data.get('isValid') and data.get('userId'):
                        return {'success': True, 'userId': data['userId']}
                    else:
                        logger.warn('APIManager: API key validation returned invalid key or no user ID')
                        return {'success': False, 'error': 'Invalid API key or no user ID'}
                except json.JSONDecodeError as e:
                    logger.error(f'APIManager: Failed to parse API validation response: {e}')
                    logger.error(f'APIManager: Raw response that failed to parse: {repr(result["data"])}')
                    return {'success': False, 'error': 'Invalid response format'}
            else:
                logger.error(f'APIManager: API key validation failed: {result.get("error", "Unknown error")}')
                return {'success': False, 'error': result['error']}

        except Exception as e:
            logger.error(f'APIManager: Error getting user ID: {e}')
            return {'success': False, 'error': str(e)}
