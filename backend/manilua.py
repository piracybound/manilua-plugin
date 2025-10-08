import os
import zipfile
import threading
from typing import Dict, Any, List, Optional
import PluginUtils
from http_client import get_global_client
from steam_utils import get_stplug_in_path
from api_manager import APIManager
from config import API_BASE_URL, HTTP_CHUNK_SIZE, DOWNLOAD_PROGRESS_UPDATE_INTERVAL

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
                'currentApi': f'manilua ({endpoint})',
                'bytesRead': 0,
                'totalBytes': 0,
                'endpoint': endpoint
            })

            client = get_global_client()
            if not client:
                raise Exception("Failed to get HTTP client")


        except Exception as e:
            logger.error(f"manilua: Fatal error in download setup: {e}")
            self._set_download_state(appid, {
                'status': 'failed',
                'error': f'Setup failed: {str(e)}'
            })
            return

        try:
            if endpoint == 'manilua':
                download_url = f'{API_BASE_URL}/file/{appid}'
            elif endpoint == 'donation':
                download_url = f'{API_BASE_URL}/donation'
            else:
                download_url = f'{API_BASE_URL}/{endpoint}'


            api_key = self.get_api_key()

            params = {'appid': appid}

            if endpoint == 'ryuu' and api_key:
                user_id_result = self.api_manager.get_user_id()

                if user_id_result.get('success') and user_id_result.get('userId'):
                    params['userId'] = user_id_result['userId']
                else:
                    logger.warn(f"manilua: Failed to get user ID for Ryuu endpoint: {user_id_result.get('error', 'Unknown error')}")

            self._set_download_state(appid, {
                'status': 'downloading',
                'endpoint': endpoint,
                'bytesRead': 0,
                'totalBytes': 0
            })

            temp_zip_path = os.path.join(self.backend_path, f"temp_{appid}.zip")
            bytes_read = 0
            last_state_update_ts = 0.0

            try:
                with client.stream_get(download_url, params=params, auth_token=api_key) as resp:
                    try:
                        total = int(resp.headers.get('Content-Length', '0'))
                    except Exception as e:
                        logger.warn(f"manilua: Could not parse Content-Length header: {e}")
                        total = 0

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
                                logger.warn(f"manilua: Could not get timestamp for download progress: {e}")
                                now_ts = 0.0

                            if last_state_update_ts == 0.0 or (now_ts - last_state_update_ts) >= DOWNLOAD_PROGRESS_UPDATE_INTERVAL:
                                self._set_download_state(appid, {
                                    'status': 'downloading',
                                    'bytesRead': bytes_read,
                                    'totalBytes': total
                                })
                                last_state_update_ts = now_ts

                if bytes_read <= 0:
                    raise Exception("Empty download from endpoint")

                self._set_download_state(appid, {
                    'status': 'downloading',
                    'bytesRead': bytes_read,
                    'totalBytes': total if total > 0 else bytes_read
                })

                self._set_download_state(appid, {
                    'status': 'processing',
                    'bytesRead': bytes_read,
                    'totalBytes': bytes_read if total == 0 else total
                })

                logger.log(f"manilua: Downloaded {bytes_read} bytes to {temp_zip_path}")

                try:
                    is_zip = zipfile.is_zipfile(temp_zip_path)
                except Exception as e:
                    logger.warn(f"manilua: Could not verify if file is ZIP for app {appid}: {e}")
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
                            os.replace(temp_zip_path, dest_file)
                        except Exception as e:
                            logger.warn(f"manilua: Could not replace file for app {appid}, copying instead: {e}")
                            with open(temp_zip_path, 'rb') as src, open(dest_file, 'wb') as dst:
                                dst.write(src.read())
                            try:
                                os.remove(temp_zip_path)
                            except Exception as e2:
                                logger.warn(f"manilua: Could not remove temp file for app {appid}: {e2}")

                        self._set_download_state(appid, {
                            'status': 'installing',
                            'installedFiles': [dest_file],
                            'installedPath': dest_file
                        })
                        logger.log(f"manilua: Installed single LUA file for app {appid}: {dest_file}")
                    except Exception as e:
                        logger.error(f"manilua: Failed to install non-zip payload for app {appid}: {e}")
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
                        logger.warn(f"manilua: Could not remove temp file on error cleanup for app {appid}: {e2}")

                self._set_download_state(appid, {
                    'status': 'failed',
                    'error': f'Download failed: {str(e)}'
                })

        except Exception as e:
            logger.error(f"manilua: Backend download failed: {str(e)}")
            self._set_download_state(appid, {
                'status': 'failed',
                'error': f'Backend error: {str(e)}'
            })

    def _extract_and_add_lua_from_zip(self, appid: int, zip_path: str, endpoint: str) -> None:
        try:
            target_dir = get_stplug_in_path()
            installed_files = []

            self._set_download_state(appid, {'status': 'extracting'})
            logger.log(f"manilua: Extracting ZIP file {zip_path} to {target_dir}")

            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                file_list = zip_file.namelist()
                logger.log(f"manilua: ZIP contains {len(file_list)} files: {file_list}")

                lua_files = [f for f in file_list if f.lower().endswith('.lua')]

                if not lua_files:
                    logger.warn(f"manilua: No .lua files found in ZIP, extracting all files")
                    lua_files = file_list

                self._set_download_state(appid, {'status': 'installing'})

                for file_name in lua_files:
                    try:
                        if file_name.endswith('/'):
                            continue

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
                        logger.log(f"manilua: Extracted {file_name} -> {dest_file}")

                    except Exception as e:
                        logger.error(f"manilua: Failed to extract {file_name}: {e}")
                        continue

            if not installed_files:
                raise Exception("No files were successfully extracted from ZIP")

            logger.log(f"manilua: Successfully installed {len(installed_files)} files from {endpoint}")
            self._set_download_state(appid, {
                'installedFiles': installed_files,
                'installedPath': installed_files[0] if installed_files else None
            })

        except zipfile.BadZipFile as e:
            logger.error(f'manilua: Invalid ZIP file for app {appid}: {e}')
            raise Exception(f"Invalid ZIP file: {str(e)}")
        except Exception as e:
            logger.error(f'manilua: Failed to extract ZIP for app {appid}: {e}')
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

        available_endpoints = ['oureveryday', 'ryuu', 'manilua', 'donation']
        if endpoints:
            available_endpoints = endpoints

        def safe_availability_check_wrapper(appid, endpoints_to_check):
            try:
                self._check_availability_and_download(appid, endpoints_to_check)
            except Exception as e:
                logger.error(f"manilua: Unhandled error in availability check thread: {e}")
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

    def select_endpoint_and_download(self, appid: int, selected_endpoint: str) -> Dict[str, Any]:
        try:
            appid = int(appid)
        except (ValueError, TypeError):
            return {'success': False, 'error': 'Invalid appid'}

        state = self._get_download_state(appid)
        if state.get('status') != 'awaiting_endpoint_choice':
            return {'success': False, 'error': 'Not awaiting endpoint choice'}

        available_endpoints = state.get('available_endpoints', [])
        if selected_endpoint not in available_endpoints:
            return {'success': False, 'error': f'Endpoint {selected_endpoint} not available'}


        def safe_download_wrapper():
            try:
                self._download_from_manilua_backend(appid, selected_endpoint)
            except Exception as e:
                logger.error(f"manilua: Download error: {e}")
                self._set_download_state(appid, {
                    'status': 'failed',
                    'error': f'Download failed: {str(e)}'
                })

        thread = threading.Thread(target=safe_download_wrapper, daemon=True)
        thread.start()

        return {'success': True}

    def _check_availability_and_download(self, appid: int, endpoints_to_check: List[str]) -> None:
        self._set_download_state(appid, {
            'status': 'checking_availability',
            'currentApi': 'Checking all endpoints...',
            'bytesRead': 0,
            'totalBytes': 0
        })

        available_on = []

        import concurrent.futures

        def check_single_endpoint(endpoint):
            try:
                result = self.api_manager.check_availability(appid, endpoint)

                if 'debug' in result:
                    pass

                if result.get('success', False) and result.get('available', False):
                    return endpoint
                else:
                    return None

            except Exception as e:
                logger.error(f"manilua: Error checking availability on {endpoint}: {e}")
                return None

        self._set_download_state(appid, {
            'status': 'checking_availability',
            'currentApi': 'Checking all endpoints...',
        })

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_endpoint = {executor.submit(check_single_endpoint, endpoint): endpoint
                                      for endpoint in endpoints_to_check}

                try:
                    for future in concurrent.futures.as_completed(future_to_endpoint, timeout=15):
                        try:
                            result = future.result()
                            if result:
                                available_on.append(result)
                        except Exception as e:
                            endpoint = future_to_endpoint[future]
                            logger.error(f"manilua: Parallel check failed for {endpoint}: {e}")
                except concurrent.futures.TimeoutError:
                    for future in future_to_endpoint:
                        if not future.done():
                            future.cancel()
                    logger.warn(f"manilua: Availability check timed out, using {len(available_on)} completed results")
        except Exception as e:
            logger.error(f"manilua: Availability check crashed: {e}")
            try:
                result = check_single_endpoint(endpoints_to_check[0])
                if result:
                    available_on.append(result)
            except Exception as e2:
                logger.error(f"manilua: Fallback single-endpoint check also failed: {e2}")

        if not available_on:
            self._set_download_state(appid, {
                'status': 'failed',
                'error': f'App {appid} is not available on any endpoint'
            })
            return
        elif len(available_on) == 1:
            selected_endpoint = available_on[0]
        else:
            self._set_download_state(appid, {
                'status': 'awaiting_endpoint_choice',
                'available_endpoints': available_on,
                'message': f'Available on: {", ".join(available_on)}. Choose an endpoint to download from.'
            })
            return

        self._download_from_manilua_backend(appid, selected_endpoint)

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
                logger.log(f"manilua: Removed {lua_file}")

            disabled_file = os.path.join(stplug_path, f'{appid}.lua.disabled')
            if os.path.exists(disabled_file):
                os.remove(disabled_file)
                removed_files.append(f'{appid}.lua.disabled')
                logger.log(f"manilua: Removed {disabled_file}")

            for filename in os.listdir(stplug_path):
                if filename.startswith(f'{appid}_') and filename.endswith('.manifest'):
                    manifest_file = os.path.join(stplug_path, filename)
                    os.remove(manifest_file)
                    removed_files.append(filename)
                    logger.log(f"manilua: Removed {manifest_file}")

            if removed_files:
                logger.log(f"manilua: Successfully removed {len(removed_files)} files for app {appid}: {removed_files}")
                return {'success': True, 'message': f'Removed {len(removed_files)} files', 'removed_files': removed_files}
            else:
                return {'success': False, 'error': f'No files found for app {appid}'}

        except Exception as e:
            logger.error(f"manilua: Error removing files for app {appid}: {e}")
            return {'success': False, 'error': str(e)}
