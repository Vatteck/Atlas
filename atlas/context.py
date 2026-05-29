from typing import Tuple

from atlas.view.util import translation
from atlas.view.util.translation import I18n

DEFAULT_I18N_KEY = 'en'
PROPERTY_HARDCODED_STYLESHEET = 'hcqss'


def _gen_i18n_data(app_config: dict, locale_dir: str) -> Tuple[str, dict, str, dict]:
    i18n_key, current_i18n = translation.get_locale_keys(app_config['locale'], locale_dir=locale_dir)
    default_i18n = translation.get_locale_keys(DEFAULT_I18N_KEY, locale_dir=locale_dir)[1] if i18n_key != DEFAULT_I18N_KEY else {}
    return i18n_key, current_i18n, DEFAULT_I18N_KEY, default_i18n


def generate_i18n(app_config: dict, locale_dir: str) -> I18n:
    return I18n(*_gen_i18n_data(app_config, locale_dir))


def update_i18n(app_config, locale_dir: str, i18n: I18n) -> I18n:
    cur_key, cur_dict, def_key, def_dict = _gen_i18n_data(app_config, locale_dir)

    if i18n.current_key == cur_key:
        i18n.current.update(cur_dict)

    i18n.default.update(def_dict)
    return i18n
