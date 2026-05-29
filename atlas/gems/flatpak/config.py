from atlas.commons.config import YAMLConfigManager
from atlas.gems.flatpak import CONFIG_FILE


class FlatpakConfigManager(YAMLConfigManager):

    def __init__(self):
        super(FlatpakConfigManager, self).__init__(config_file_path=CONFIG_FILE)

    def get_default_config(self) -> dict:
        return {'installation_level': None}
