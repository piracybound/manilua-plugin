import os
import zipfile
import threading
from typing import Dict, Any, List, Optional
import PluginUtils
from http_client import get_global_client
from steam_utils import get_stplug_in_path
from api_manager import APIManager
from config import API_BASE_URL, HTTP_CHUNK_SIZE, DOWNLOAD_PROGRESS_UPDATE_INTERVAL

try:
    import httpx
    from httpx import HTTPStatusError
    HTTPX_AVAILABLE = True
except ImportError:
    httpx = None
    HTTPStatusError = None
    HTTPX_AVAILABLE = False

logger = PluginUtils.Logger()

class maniluaManager:
    def __init__(self, backend_path: str, api_manager: APIManager):
        self.backend_path = backend_path
        self.api_manager = api_manager
        self._download_state: Dict[int, Dict[str, Any]] = {}
        self._download_lock = threading.Lock()
        self._api_key = None

    def set_api_key(self, api_key: str):
        self._api_key = api_key

    def get_api_key(self):
        return self._api_key

    def _set_download_state(self, appid: int, update: Dict[str, Any]) -> None:
        with self._download_lock:
            state = self._download_state.get(appid, {})
            state.update(update)
            self._download_state[appid] = state

    def _get_download_state(self, appid: int) -> Dict[str, Any]:
        with self._download_lock:
            return self._download_state.get(appid, {}).copy()

    def get_download_status(self, appid: int) -> Dict[str, Any]:
        state = self._get_download_state(appid)
        return {'success': True, 'state': state}

    def _download_from_manilua_backend(self, appid: int, endpoint: str = "") -> None:
        try:
            self._set_download_state(appid, {
                'status': 'checking',
                'bytesRead': 0,
                'totalBytes': 0,
                'endpoint': endpoint
            })

            client = get_global_client()
            if not client:
                raise Exception("Failed to get HTTP client")

        except Exception as e:
            logger.error(f"Fatal error in download setup: {e}")
            self._set_download_state(appid, {
                'status': 'failed',
                'error': f'Setup failed: {str(e)}'
            })
            return

        try:
            download_url = f'{API_BASE_URL}/game/{appid}'

            api_key = self.get_api_key()
            params = {'appid': appid}

            temp_zip_path = os.path.join(self.backend_path, f"temp_{appid}.zip")
            bytes_read = 0
            last_state_update_ts = 0.0

            try:
                with client.stream_get(download_url, params=params, auth_token=api_key) as resp:
                    if not resp.is_success:
                        if resp.status_code == 401:
                            raise Exception("API key authentication failed")
                        elif resp.status_code == 404:
                            raise Exception(f"Game {appid} not found")
                        else:
                            raise Exception(f"HTTP {resp.status_code}: {resp.reason_phrase}")

                    try:
                        total = int(resp.headers.get('Content-Length', '0'))
                    except Exception as e:
                        logger.warn(f"Could not parse Content-Length header: {e}")
                        total = 0

                    content_type = resp.headers.get('content-type', '').lower()
                    if 'application/json' in content_type:
                        error_text = resp.read().decode('utf-8')
                        logger.error(f"Received JSON error response: {error_text}")
                        if resp.status_code == 401 or 'authentication' in error_text.lower():
                            raise Exception("API key authentication failed")
                        else:
                            raise Exception(f"Server error: {error_text}")

                    self._set_download_state(appid, {
                        'status': 'downloading',
                        'bytesRead': 0,
                        'totalBytes': total
                    })

                    with open(temp_zip_path, 'wb', buffering=HTTP_CHUNK_SIZE) as f:
                        for chunk in resp.iter_bytes(chunk_size=HTTP_CHUNK_SIZE):
                            if not chunk:
                                continue
                            f.write(chunk)
                            bytes_read += len(chunk)

                            try:
                                import time as _time
                                now_ts = _time.time()
                            except Exception as e:
                                logger.warn(f"Could not get timestamp for download progress: {e}")
                                now_ts = 0.0

                            if last_state_update_ts == 0.0 or (now_ts - last_state_update_ts) >= DOWNLOAD_PROGRESS_UPDATE_INTERVAL:
                                self._set_download_state(appid, {
                                    'status': 'downloading',
                                    'bytesRead': bytes_read,
                                    'totalBytes': total,
                                    'endpoint': endpoint
                                })
                                last_state_update_ts = now_ts

                if bytes_read <= 0:
                    raise Exception("Empty download from endpoint")

                
                self._set_download_state(appid, {
                    'status': 'processing',
                    'bytesRead': bytes_read,
                    'totalBytes': bytes_read if total == 0 else total
                })

                logger.log(f"Downloaded {bytes_read} bytes to {temp_zip_path}")

                try:
                    is_zip = zipfile.is_zipfile(temp_zip_path)
                except Exception as e:
                    logger.warn(f"Could not verify if file is ZIP for app {appid}: {e}")
                    is_zip = False

                if is_zip:
                    self._extract_and_add_lua_from_zip(appid, temp_zip_path, endpoint)
                    if os.path.exists(temp_zip_path):
                        os.remove(temp_zip_path)
                else:
                    try:
                        target_dir = get_stplug_in_path()
                        dest_file = os.path.join(target_dir, f"{appid}.lua")

                        try:
                            with open(temp_zip_path, 'rb') as src, open(dest_file, 'wb') as dst:
                                dst.write(src.read())
                            os.remove(temp_zip_path)
                        except Exception as e:
                            logger.warn(f"Could not copy file for app {appid}: {e}")
                            raise

                        self._set_download_state(appid, {
                            'status': 'installing',
                            'installedFiles': [dest_file],
                            'installedPath': dest_file
                        })
                        logger.log(f"Installed single LUA file for app {appid}: {dest_file}")
                    except Exception as e:
                        logger.error(f"Failed to install non-zip payload for app {appid}: {e}")
                        raise

                self._set_download_state(appid, {
                    'status': 'done',
                    'success': True,
                    'api': f'manilua ({endpoint})'
                })

            except Exception as e:
                if os.path.exists(temp_zip_path):
                    try:
                        os.remove(temp_zip_path)
                    except Exception as e2:
                        logger.warn(f"Could not remove temp file on error cleanup for app {appid}: {e2}")

                error_message = str(e)
                if "authentication failed" in error_message.lower() or (HTTPX_AVAILABLE and HTTPStatusError is not None and isinstance(e, HTTPStatusError) and e.response.status_code == 401):
                    logger.error(f"API key authentication failed for app {appid}")
                    self._set_download_state(appid, {
                        'status': 'auth_failed',
                        'error': 'API key authentication failed. Please set a valid API key.',
                        'requiresNewKey': True
                    })
                    return

                self._set_download_state(appid, {
                    'status': 'failed',
                    'error': f'Download failed: {str(e)}'
                })

        except Exception as e:
            logger.error(f"Backend download failed: {str(e)}")
            self._set_download_state(appid, {
                'status': 'failed',
                'error': f'Backend error: {str(e)}'
            })

    def _extract_and_add_lua_from_zip(self, appid: int, zip_path: str, endpoint: str) -> None:
        try:
            target_dir = get_stplug_in_path()
            installed_files = []

            self._set_download_state(appid, {'status': 'extracting'})
            logger.log(f"Extracting ZIP file {zip_path} to {target_dir}")

            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                file_list = zip_file.namelist()
                logger.log(f"ZIP contains {len(file_list)} files")

                lua_files = [f for f in file_list if f.lower().endswith('.lua')]

                if not lua_files:
                    logger.warn(f"No .lua files found in ZIP, extracting all files")
                    lua_files = file_list

                self._set_download_state(appid, {'status': 'installing'})

                installed_files = []

                for file_name in lua_files:
                    if file_name.endswith('/'):
                        continue

                    try:
                        file_content = zip_file.read(file_name)

                        if file_name.lower().endswith('.lua'):
                            base_name = os.path.basename(file_name)
                            dest_file = os.path.join(target_dir, base_name)
                        else:
                            file_ext = os.path.splitext(file_name)[1] or '.txt'
                            dest_file = os.path.join(target_dir, f"{appid}{file_ext}")

                        if isinstance(file_content, bytes):
                            if file_name.lower().endswith('.lua'):
                                try:
                                    decoded_content = file_content.decode('utf-8')
                                    with open(dest_file, 'w', encoding='utf-8') as out:
                                        out.write(decoded_content)
                                except UnicodeDecodeError:
                                    with open(dest_file, 'wb') as out:
                                        out.write(file_content)
                            else:
                                with open(dest_file, 'wb') as out:
                                    out.write(file_content)
                        else:
                            with open(dest_file, 'w', encoding='utf-8') as out:
                                out.write(str(file_content))

                        installed_files.append(dest_file)

                    except Exception as e:
                        logger.error(f"Failed to extract {file_name}: {e}")
                        continue

            if not installed_files:
                raise Exception("No files were successfully extracted from ZIP")

            logger.log(f"Successfully installed {len(installed_files)} files from {endpoint}")
            self._set_download_state(appid, {
                'installedFiles': installed_files,
                'installedPath': installed_files[0] if installed_files else None
            })

        except zipfile.BadZipFile as e:
            logger.error(f'Invalid ZIP file for app {appid}: {e}')
            raise Exception(f"Invalid ZIP file: {str(e)}")
        except Exception as e:
            logger.error(f'Failed to extract ZIP for app {appid}: {e}')
            raise

    def add_via_lua(self, appid: int, endpoints: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            appid = int(appid)
        except (ValueError, TypeError):
            return {'success': False, 'error': 'Invalid appid'}


        self._set_download_state(appid, {
            'status': 'queued',
            'bytesRead': 0,
            'totalBytes': 0
        })

        available_endpoints = ['unified']
        if endpoints:
            available_endpoints = endpoints

        def safe_availability_check_wrapper(appid, endpoints_to_check):
            try:
                self._check_availability_and_download(appid, endpoints_to_check)
            except Exception as e:
                logger.error(f"Unhandled error in availability check thread: {e}")
                self._set_download_state(appid, {
                    'status': 'failed',
                    'error': f'Availability check crashed: {str(e)}'
                })

        thread = threading.Thread(
            target=safe_availability_check_wrapper,
            args=(appid, available_endpoints),
            daemon=True
        )
        thread.start()

        return {'success': True}

  
    def _check_availability_and_download(self, appid: int, endpoints_to_check: List[str]) -> None:
        self._download_from_manilua_backend(appid, 'unified')

    def remove_via_lua(self, appid: int) -> Dict[str, Any]:
        try:
            appid = int(appid)
        except (ValueError, TypeError):
            return {'success': False, 'error': 'Invalid appid'}

        try:
            stplug_path = get_stplug_in_path()
            removed_files = []

            lua_file = os.path.join(stplug_path, f'{appid}.lua')
            if os.path.exists(lua_file):
                os.remove(lua_file)
                removed_files.append(f'{appid}.lua')
                logger.log(f"Removed {lua_file}")

            disabled_file = os.path.join(stplug_path, f'{appid}.lua.disabled')
            if os.path.exists(disabled_file):
                os.remove(disabled_file)
                removed_files.append(f'{appid}.lua.disabled')
                logger.log(f"Removed {disabled_file}")

            for filename in os.listdir(stplug_path):
                if filename.startswith(f'{appid}_') and filename.endswith('.manifest'):
                    manifest_file = os.path.join(stplug_path, filename)
                    os.remove(manifest_file)
                    removed_files.append(filename)
                    logger.log(f"Removed {manifest_file}")

            if removed_files:
                logger.log(f"Successfully removed {len(removed_files)} files for app {appid}: {removed_files}")
                return {'success': True, 'message': f'Removed {len(removed_files)} files', 'removed_files': removed_files}
            else:
                return {'success': False, 'error': f'No files found for app {appid}'}

        except Exception as e:
            logger.error(f"Error removing files for app {appid}: {e}")
            return {'success': False, 'error': str(e)}
