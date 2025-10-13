import Millennium
import PluginUtils
import json
import os

from http_client import close_global_client
from api_manager import APIManager
from manilua import maniluaManager
from steam_utils import has_lua_for_app, list_lua_apps
from config import API_KEY_PREFIX, VERSION

logger = PluginUtils.Logger()

def json_response(data: dict) -> str:
    return json.dumps(data)

def success_response(**kwargs) -> str:
    return json_response({'success': True, **kwargs})

def error_response(error: str, **kwargs) -> str:
    return json_response({'success': False, 'error': error, **kwargs})

def GetPluginDir():
    current_file = os.path.realpath(__file__)

    if current_file.endswith('/main.py/main.py') or current_file.endswith('\\main.py\\main.py'):
        current_file = current_file[:-8]
    elif current_file.endswith('/main.py') or current_file.endswith('\\main.py'):
        current_file = current_file[:-8]

    if current_file.endswith('main.py'):
        backend_dir = os.path.dirname(current_file)
    else:
        backend_dir = current_file

    plugin_dir = os.path.dirname(backend_dir)

    return plugin_dir

class Plugin:
    def __init__(self):
        self.plugin_dir = GetPluginDir()
        self.backend_path = os.path.join(self.plugin_dir, 'backend')
        self.api_manager = APIManager(self.backend_path)
        self.manilua_manager = maniluaManager(self.backend_path, self.api_manager)
        self._api_key = None
        self._injected = False
        self._load_api_key()

        if self.has_api_key() and isinstance(self._api_key, str) and self._api_key.strip() != "":
            self.api_manager.set_api_key(self._api_key)
            self.manilua_manager.set_api_key(self._api_key)
        else:
            logger.log("manilua: backend initialized without API key")

    def _load_api_key(self):
        api_key_file = os.path.join(self.backend_path, 'api_key.txt')
        try:
            if os.path.exists(api_key_file):
                with open(api_key_file, 'r', encoding='utf-8') as f:
                    self._api_key = f.read().strip()
                if not self._api_key:
                    logger.log("manilua: API key file is empty")
        except Exception as e:
            logger.error(f"manilua: Failed to load API key: {e}")

    def _save_api_key(self, api_key: str):
        api_key_file = os.path.join(self.backend_path, 'api_key.txt')
        try:
            with open(api_key_file, 'w', encoding='utf-8') as f:
                f.write(api_key)
            self._api_key = api_key
        except Exception as e:
            logger.error(f"manilua: Failed to save API key: {e}")

    def get_api_key(self):
        return self._api_key

    def has_api_key(self):
        return self._api_key is not None and self._api_key.strip() != ""

    def _inject_webkit_files(self):
        if self._injected:
            return

        try:
            js_file_path = os.path.join(self.plugin_dir, '.millennium', 'Dist', 'index.js')

            if os.path.exists(js_file_path):
                Millennium.add_browser_js(js_file_path)
                self._injected = True
            else:
                logger.error(f"manilua: Bundle not found")
        except Exception as e:
            logger.error(f'manilua: Failed to inject: {e}')

    def _front_end_loaded(self):
        logger.log(f"manilua: v{VERSION} ready")

    def _load(self):
        logger.log(f"manilua: backend loading (v{VERSION})")
        self._inject_webkit_files()
        Millennium.ready()
        logger.log("manilua: backend ready")

    def _unload(self):
        logger.log("Unloading manilua plugin")
        close_global_client()


_plugin_instance = None

def get_plugin():
    global _plugin_instance
    if _plugin_instance is None:
        _plugin_instance = Plugin()
        _plugin_instance._load()
    return _plugin_instance

plugin = get_plugin()

class Logger:
    @staticmethod
    def log(message: str) -> str:
        logger.log(f"[Frontend] {message}")
        return success_response()

def hasluaForApp(appid: int) -> str:
    try:
        exists = has_lua_for_app(appid)
        return success_response(exists=exists)
    except Exception as e:
        logger.error(f'hasluaForApp failed for {appid}: {e}')
        return error_response(str(e))

def addViamanilua(appid: int) -> str:
    try:
        if not plugin.has_api_key():
            return error_response('No API key configured. Please set an API key first.', requiresNewKey=True)

        endpoints = plugin.api_manager.get_download_endpoints()
        result = plugin.manilua_manager.add_via_lua(appid, endpoints)
        return json_response(result)
    except Exception as e:
        logger.error(f'addViamanilua failed for {appid}: {e}')
        return error_response(str(e))

def GetStatus(appid: int) -> str:
    try:
        result = plugin.manilua_manager.get_download_status(appid)
        return json_response(result)
    except Exception as e:
        logger.error(f'GetStatus failed for {appid}: {e}')
        return error_response(str(e))

def GetLocalLibrary() -> str:
    try:
        apps = list_lua_apps()
        return success_response(apps=apps)
    except Exception as e:
        logger.error(f'GetLocalLibrary failed: {e}')
        return error_response(str(e))


def SetAPIKey(*args, **kwargs) -> str:
    try:
        api_key = None
        if args:
            api_key = args[0]
        elif 'api_key' in kwargs:
            api_key = kwargs['api_key']
        elif kwargs and len(kwargs) == 1:
            api_key = next(iter(kwargs.values()))

        if not api_key or not isinstance(api_key, str):
            return error_response('Invalid API key')

        if not api_key.startswith(API_KEY_PREFIX):
            return error_response(f'Invalid API key format (must start with {API_KEY_PREFIX})')

        plugin._save_api_key(api_key)
        plugin.api_manager.set_api_key(api_key)
        plugin.manilua_manager.set_api_key(api_key)

        return success_response(message='API key configured successfully')
    except Exception as e:
        logger.error(f'SetAPIKey failed: {e}')
        return error_response(str(e))

def GetAPIKeyStatus() -> str:
    try:
        has_key = plugin.has_api_key()
        if has_key:
            api_key = plugin.get_api_key()
            if api_key is not None:
                masked_key = api_key[:12] + '...' + api_key[-4:] if len(api_key) > 16 else api_key[:8] + '...'
            else:
                masked_key = ''

            return success_response(
                hasKey=True,
                maskedKey=masked_key,
                isValid=True,
                message='API key is configured'
            )
        else:
            return success_response(
                hasKey=False,
                message='No API key configured. Please set an API key from www.piracybound.com/manilua'
            )
    except Exception as e:
        logger.error(f'GetAPIKeyStatus failed: {e}')
        return error_response(str(e))



def removeViamanilua(appid: int) -> str:
    try:
        result = plugin.manilua_manager.remove_via_lua(appid)
        return json_response(result)
    except Exception as e:
        logger.error(f'removeViamanilua failed for {appid}: {e}')
        return error_response(str(e))
