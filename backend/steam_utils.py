import os
import sys
from typing import Optional
import Millennium
import PluginUtils

logger = PluginUtils.Logger()

if sys.platform.startswith('win'):
    try:
        import winreg
    except Exception:
        winreg = None

_steam_install_path: Optional[str] = None
_stplug_in_path_cache: Optional[str] = None

def detect_steam_install_path() -> str:
    global _steam_install_path

    if _steam_install_path:
        return _steam_install_path

    path = None

    if sys.platform.startswith('win') and winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                path, _ = winreg.QueryValueEx(key, 'SteamPath')
        except Exception:
            path = None

    if not path:
        try:
            path = Millennium.steam_path()
        except Exception:
            path = None

    _steam_install_path = path
    return _steam_install_path or ''

def get_steam_config_path() -> str:
    steam_path = detect_steam_install_path()
    if not steam_path:
        raise RuntimeError("Steam installation path not found")
    return os.path.join(steam_path, 'config')

def get_stplug_in_path() -> str:
    global _stplug_in_path_cache

    if _stplug_in_path_cache:
        return _stplug_in_path_cache

    config_path = get_steam_config_path()
    stplug_path = os.path.join(config_path, 'stplug-in')
    os.makedirs(stplug_path, exist_ok=True)
    _stplug_in_path_cache = stplug_path
    return stplug_path

def has_lua_for_app(appid: int) -> bool:
    try:
        base_path = detect_steam_install_path()
        if not base_path:
            return False

        stplug_path = os.path.join(base_path, 'config', 'stplug-in')
        lua_file = os.path.join(stplug_path, f'{appid}.lua')
        disabled_file = os.path.join(stplug_path, f'{appid}.lua.disabled')

        exists = os.path.exists(lua_file) or os.path.exists(disabled_file)
        return exists

    except Exception as e:
        logger.error(f'manilua (steam_utils): Error checking Lua scripts for app {appid}: {e}')
        return False

def list_lua_apps() -> list:
    try:
        base_path = detect_steam_install_path()
        if not base_path:
            return []

        stplug_path = os.path.join(base_path, 'config', 'stplug-in')
        if not os.path.exists(stplug_path):
            return []

        apps_mtime = {}
        for filename in os.listdir(stplug_path):
            if filename.endswith('.lua') or filename.endswith('.lua.disabled'):
                name = filename.split('.')[0]
                if not name.isdigit():
                    continue
                appid = int(name)
                path = os.path.join(stplug_path, filename)
                try:
                    mtime = os.path.getmtime(path)
                    apps_mtime[appid] = mtime
                except Exception:
                    continue

        return sorted(apps_mtime.keys(), key=lambda a: apps_mtime[a], reverse=True)

    except Exception as e:
        logger.error(f'manilua (steam_utils): list_lua_apps failed: {e}')
        return []
