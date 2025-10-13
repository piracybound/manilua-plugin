import os
import hashlib
import time
import random
import Millennium
import PluginUtils
from typing import Dict, Optional, Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

logger = PluginUtils.Logger()

class SteamVerification:
    def __init__(self):
        self.steam_pid = None
        self.steam_process = None
        self.millennium_version = None
        self.plugin_checksum = None
        self._discover_steam_process()
        self._calculate_plugin_checksum()

    def _discover_steam_process(self):
        try:
            if not PSUTIL_AVAILABLE:
                self.steam_pid = random.randint(1000, 65535)
                return

            if psutil is not None:
                for proc in psutil.process_iter(['pid', 'name', 'exe']):
                    try:
                        proc_info = proc.info
                        if proc_info['name'] and 'steam' in proc_info['name'].lower():
                            if proc_info['exe'] and 'steam.exe' in proc_info['exe'].lower():
                                self.steam_pid = proc_info['pid']
                                self.steam_process = proc
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue

            if not self.steam_pid:
                self.steam_pid = random.randint(1000, 65535)

            try:
                self.millennium_version = Millennium.version()
            except Exception:
                self.millennium_version = "1.0.0"

        except Exception as e:
            logger.error(f"manilua (steam_verification): Error discovering Steam process: {e}")
            self.steam_pid = random.randint(1000, 65535)
            self.millennium_version = "1.0.0"

    def _calculate_plugin_checksum(self):
        try:
            hasher = hashlib.sha256()

            plugin_file = __file__
            if os.path.exists(plugin_file):
                with open(plugin_file, 'rb') as f:
                    hasher.update(f.read())

            if self.steam_process:
                try:
                    steam_exe = self.steam_process.exe()
                    if steam_exe and os.path.exists(steam_exe):
                        with open(steam_exe, 'rb') as f:
                            steam_data = f.read(1024)
                            hasher.update(steam_data)
                except Exception as e:
                    logger.warn(f"manilua (steam_verification): Could not read Steam executable for checksum: {e}")

            import platform
            machine_info = f"{platform.node()}-{platform.processor()}-{os.environ.get('USERNAME', 'unknown')}"
            hasher.update(machine_info.encode())

            self.plugin_checksum = hasher.hexdigest()

        except Exception as e:
            logger.error(f"manilua (steam_verification): Error calculating plugin checksum: {e}")
            fallback_data = f"{time.time()}-{os.environ.get('USERNAME', 'unknown')}-{self.steam_pid}"
            self.plugin_checksum = hashlib.sha256(fallback_data.encode()).hexdigest()

    def _get_process_hash(self) -> str:
        try:
            if self.steam_process:
                memory_info = self.steam_process.memory_info()
                cpu_percent = self.steam_process.cpu_percent()
                create_time = self.steam_process.create_time()

                process_data = f"{memory_info.rss}-{memory_info.vms}-{cpu_percent}-{create_time}"
                return hashlib.sha256(process_data.encode()).hexdigest()[:32]
        except Exception as e:
            logger.warn(f"manilua (steam_verification): Could not get process metrics for session token: {e}")

        fallback_data = f"{time.time()}-{self.steam_pid}"
        return hashlib.sha256(fallback_data.encode()).hexdigest()[:32]

    def _get_memory_proof(self) -> str:
        try:
            if self.steam_process:
                threads = len(self.steam_process.threads())
                memory_maps = len(self.steam_process.memory_maps()) if hasattr(self.steam_process, 'memory_maps') else 0

                memory_data = f"{threads}-{memory_maps}-{self.steam_pid}"
                return hashlib.sha256(memory_data.encode()).hexdigest()[:32]
        except Exception as e:
            logger.warn(f"manilua (steam_verification): Could not get memory metrics for memory token: {e}")

        fallback_data = f"memory-{self.steam_pid}-{time.time()}"
        return hashlib.sha256(fallback_data.encode()).hexdigest()[:32]

    def get_verification_headers(self) -> Dict[str, str]:
        current_time = str(int(time.time() * 1000))

        headers = {
            'X-Steam-PID': str(self.steam_pid),
            'X-Millennium-Version': self.millennium_version,
            'X-Plugin-Checksum': self.plugin_checksum,
            'X-Process-Hash': self._get_process_hash(),
            'X-Memory-Proof': self._get_memory_proof(),
            'X-Plugin-Timestamp': current_time,
            'User-Agent': f'manilua-plugin/{self.millennium_version} (Millennium)',
        }

        return headers

    def refresh_verification(self):
        try:
            if self.steam_process and not self.steam_process.is_running():
                logger.log("manilua (steam_verification): Steam process changed, refreshing...")
                self._discover_steam_process()

            if random.random() < 0.1:
                self._calculate_plugin_checksum()

        except Exception as e:
            logger.error(f"manilua (steam_verification): Error refreshing verification: {e}")

    def get_steam_info(self) -> Dict[str, Any]:
        info = {
            'steam_pid': self.steam_pid,
            'millennium_version': self.millennium_version,
            'has_process': self.steam_process is not None,
            'checksum_length': len(self.plugin_checksum) if self.plugin_checksum else 0
        }

        if self.steam_process:
            try:
                info.update({
                    'process_name': self.steam_process.name(),
                    'process_running': self.steam_process.is_running(),
                    'memory_rss': self.steam_process.memory_info().rss
                })
            except Exception as e:
                logger.warn(f"manilua (steam_verification): Could not get process debug info: {e}")

        return info

_verification_instance: Optional[SteamVerification] = None

def get_steam_verification() -> SteamVerification:
    global _verification_instance
    if _verification_instance is None:
        _verification_instance = SteamVerification()
    return _verification_instance

def refresh_steam_verification():
    global _verification_instance
    if _verification_instance:
        _verification_instance.refresh_verification()
