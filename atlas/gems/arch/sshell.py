from typing import Optional, Tuple

from atlas.commons.system import execute


def mkdir(dir_path: str, parent: bool = True, custom_user: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    cmd = ['mkdir', '-p', dir_path] if parent else ['mkdir', dir_path]
    code, output = execute(cmd, custom_user=custom_user)
    return code == 0, output
