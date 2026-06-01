import traceback
from io import StringIO
from threading import Thread

from atlas.api.abstract.cache import MemoryCache
from atlas.api.abstract.context import ApplicationContext
from atlas.api.abstract.controller import SoftwareManager
from atlas.api.abstract.model import PackageStatus
from atlas.gems.flatpak import flathub
from atlas.gems.flatpak.constants import FLATHUB_URL
from atlas.gems.flatpak.model import FlatpakApplication


class FlatpakAsyncDataLoader(Thread):

    def __init__(self, app: FlatpakApplication, manager: SoftwareManager, context: ApplicationContext, api_cache: MemoryCache, category_cache: MemoryCache):
        super(FlatpakAsyncDataLoader, self).__init__()
        self.app = app
        self.manager = manager
        self.http_client = context.http_client
        self.api_cache = api_cache
        self.persist = False
        self.logger = context.logger
        self.category_cache = category_cache

    @staticmethod
    def format_category(category: str) -> str:
        word = StringIO()
        last_l = None
        for idx, l in enumerate(category):
            if idx != 0 and last_l != ' ' and l.isupper() and idx + 1 < len(category) and category[idx + 1].islower():
                word.write(' ')

            last_l = l.lower()
            word.write(last_l)

        word.seek(0)
        return word.read()

    def run(self):
        if self.app:
            self.app.status = PackageStatus.LOADING_DATA

            try:
                data = flathub.get_appstream(self.http_client, self.app.id)

                if not data:
                    self.logger.warning("Could not retrieve Flathub data for id '{}'".format(self.app.id))
                else:
                    release = flathub.latest_release(data)

                    if not self.app.name:
                        self.app.name = data.get('name')

                    if not self.app.description:
                        self.app.description = data.get('description') or data.get('summary')

                    # v2 'icon' is an absolute URL; keep the legacy relative-path guard just in case.
                    self.app.icon_url = data.get('icon')
                    if self.app.icon_url and self.app.icon_url.startswith('/'):
                        self.app.icon_url = FLATHUB_URL + self.app.icon_url

                    self.app.latest_version = release.get('version') or self.app.version

                    if self.app.latest_version and (not self.app.version or not self.app.update):
                        self.app.version = self.app.latest_version

                    if not self.app.installed and self.app.latest_version:
                        self.app.version = self.app.latest_version

                    cats = flathub.categories(data)
                    if cats:
                        formatted = []
                        for c in cats:
                            cached = self.category_cache.get(c)

                            if not cached:
                                cached = self.format_category(c)
                                self.category_cache.add_non_existing(c, cached)

                            formatted.append(cached)

                        self.app.categories = formatted

                    loaded_data = self.app.get_data_to_cache()

                    self.api_cache.add(self.app.id, loaded_data)
                    self.persist = self.app.supports_disk_cache()
            except Exception:
                self.logger.error("Could not retrieve app data for id '{}'".format(self.app.id))
                traceback.print_exc()

            self.app.status = PackageStatus.READY

            if self.persist:
                self.manager.cache_to_disk(pkg=self.app, icon_bytes=None, only_icon=False)
