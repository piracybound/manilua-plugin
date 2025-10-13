from typing import Optional
import PluginUtils

logger = PluginUtils.Logger()

class APIManager:
    def __init__(self, backend_path: str):
        self.backend_path = backend_path
        self._api_key: Optional[str] = None

    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key

    def get_api_key(self) -> Optional[str]:
        return self._api_key

    def get_download_endpoints(self) -> list:
        return ['unified']