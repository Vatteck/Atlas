import logging
import re
from abc import ABC
from datetime import datetime, timezone
from logging import Logger
from typing import Optional, Union

re_command_forbidden_symbols = re.compile(r'[\'\"%$#*<>]')
re_several_spaces = re.compile(r'\s+')
re_command_parameter = re.compile(r'(^|\s)-+\w+')


class NullLoggerFactory(ABC):

    __instance: Optional[Logger] = None

    @classmethod
    def logger(cls) -> Logger:
        if cls.__instance is None:
            cls.__instance = logging.getLogger('__null__')
            cls.__instance.addHandler(logging.NullHandler())

        return cls.__instance


def deep_update(source: dict, overrides: dict):
    for key, value in overrides.items():
        if isinstance(value, dict):
            base = source.get(key)
            returned = deep_update(base if isinstance(base, dict) else {}, value)
            source[key] = returned
        elif value is None and isinstance(source.get(key), dict):
            # A null override (common in stale/partial config files) must not wipe out a
            # structured default — that left callers doing config['block']['key'] hitting
            # 'NoneType' is not subscriptable. Keep the template's nested defaults instead.
            continue
        else:
            source[key] = value
    return source


def size_to_byte(size: Union[float, int, str], unit: str, logger: Optional[Logger] = None) -> Optional[float]:
    lower_unit = unit.strip().lower()

    if isinstance(size, str):
        try:
            final_size = float(size.strip().replace(',', '.').replace(' ', ''))
        except ValueError:
            if logger:
                logger.error(f"Could not parse string size {size} to bytes")
            return
    else:
        final_size = float(size)

    if unit == 'b':
        return final_size / 8

    if unit == 'B':
        return final_size

    base = 1024 if lower_unit.endswith('ib') else 1000

    if lower_unit[0] == 'k':
        return final_size * base
    elif lower_unit[0] == 'm':
        return final_size * (base ** 2)
    elif lower_unit[0] == 'g':
        return final_size * (base ** 3)
    elif lower_unit[0] == 't':
        return final_size * (base ** 4)
    else:
        return final_size * (base ** 5)


def utc_now() -> datetime:
    """Return the current UTC time as a *naive* datetime (no tzinfo).

    This is the deprecation-free replacement for ``datetime.utcnow()`` and is
    deliberately naive. Atlas stores cache timestamps via ``utc_now().timestamp()``
    and reads them back with ``datetime.fromtimestamp(...)``; both sides operate in
    the same naive "UTC wall-clock" space, so switching to a timezone-aware value
    here would shift every stored timestamp by the local UTC offset and misread
    existing cache files. Keep it naive.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def datetime_as_milis(date: datetime = None) -> int:
    return int(round((date if date is not None else utc_now()).timestamp() * 1000))


def map_timestamp_file(file_path: str) -> str:
    path_split = file_path.split('/')
    return '/'.join(path_split[0:-1]) + '/' + path_split[-1].split('.')[0] + '.ts'


def sanitize_command_input(input_: str) -> str:
    final_input = input_

    for op in ('|', '&'):
        final_input = final_input.split(op)[0]

    for remove_re in (re_command_forbidden_symbols, re_command_parameter):
        final_input = remove_re.sub('', final_input)

    final_input = re_several_spaces.sub(' ', final_input)
    return final_input.strip()
