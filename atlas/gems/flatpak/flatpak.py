import os
import re
import subprocess
import traceback
from datetime import datetime
from threading import Thread
from typing import List, Dict, Set, Iterable, Optional, Tuple

from atlas.api.exception import NoInternetException
from atlas.commons import system
from atlas.commons.system import new_subprocess, run_cmd, SimpleProcess, ProcessHandler, DEFAULT_LANG
from atlas.commons.util import size_to_byte
from atlas.commons.version_util import map_str_version
from atlas.gems.flatpak import EXPORTS_PATH, VERSION_1_3, VERSION_1_2, VERSION_1_5, VERSION_1_12
from atlas.gems.flatpak.constants import FLATHUB_URL

RE_SEVERAL_SPACES = re.compile(r'\s+')
RE_COMMIT = re.compile(r'(Latest commit|Commit)\s*:\s*(.+)')
RE_REQUIRED_RUNTIME = re.compile(rf'Required\s+runtime\s+.+\(([\w./]+)\)\s*.+\s+remote\s+([\w+./]+)')
OPERATION_UPDATE_SYMBOLS = {'i', 'u'}


def get_app_info_fields(app_id: str, branch: str, installation: str, fields: List[str] = [], check_runtime: bool = False):
    info = get_app_info(app_id, branch, installation)

    if not info:
        return {}

    info = re.findall(r'\w+:\s.+', info)
    data = {}
    fields_to_retrieve = len(fields) + (1 if check_runtime and 'ref' not in fields else 0)

    for field in info:

        if fields and fields_to_retrieve == 0:
            break

        field_val = field.split(':')
        field_name = field_val[0].lower()

        if not fields or field_name in fields or (check_runtime and field_name == 'ref'):
            data[field_name] = field_val[1].strip()

            if fields:
                fields_to_retrieve -= 1

        if check_runtime and field_name == 'ref':
            data['runtime'] = data['ref'].startswith('runtime/')

    return data


def get_fields(app_id: str, branch: str, fields: List[str]) -> List[str]:
    cmd = ['flatpak', 'info', app_id]

    if branch:
        cmd.append(branch)

    info = new_subprocess(cmd).stdout

    res = []
    for o in new_subprocess(('grep', '-E', '({}):.+'.format('|'.join(fields)), '-o'), stdin=info).stdout:
        if o:
            res.append(o.decode().split(':')[-1].strip())

    return res


def is_installed():
    version = get_version()
    return False if version is None else True


def get_version() -> Optional[Tuple[str, ...]]:
    res = run_cmd('flatpak --version', print_error=False)
    return map_str_version(res.split(' ')[1].strip()) if res else None


def get_app_info(app_id: str, branch: str, installation: str) -> Optional[str]:
    try:
        return run_cmd(f'flatpak info {app_id} {branch} --{installation}')
    except Exception:
        traceback.print_exc()
        return ''


def show_permissions(app_id: str, branch: str, installation: str) -> Optional[str]:
    """`flatpak info --show-permissions` — the app's effective [Context] (incl. existing overrides)."""
    cmd = f'flatpak info --show-permissions {app_id}'
    if branch:
        cmd += f' {branch}'
    if installation:  # None/'' when the webview didn't resolve it — bare '--None' is an invalid flag
        cmd += f' --{installation}'
    return run_cmd(cmd, ignore_return_code=True, print_error=False)


def set_override(app_id: str, flag: str) -> Tuple[bool, str]:
    """Apply a single `flatpak override --user <flag> <app>` (user-level — no root). Returns
    (success, stderr)."""
    proc = new_subprocess(['flatpak', 'override', '--user', flag, app_id])
    _, err = proc.communicate()
    return proc.returncode == 0, (err or b'').decode(errors='replace').strip()


def reset_overrides(app_id: str) -> bool:
    """Clear all user overrides for an app (`flatpak override --user --reset <app>`)."""
    proc = new_subprocess(['flatpak', 'override', '--user', '--reset', app_id])
    proc.communicate()
    return proc.returncode == 0


def get_commit(app_id: str, branch: str, installation: str) -> Optional[str]:
    info = run_cmd(f'flatpak info {app_id} {branch} --{installation}')

    if info:
        commits = RE_COMMIT.findall(info)
        if commits:
            return commits[0][1].strip()


def list_installed(version: Tuple[str, ...]) -> List[dict]:
    apps = []

    if version < VERSION_1_2:
        app_list = new_subprocess(('flatpak', 'list', '-d'), lang=None)

        for o in app_list.stdout:
            if o:
                data = o.decode().strip().split('\t')
                ref_split = data[0].split('/')
                runtime = 'runtime' in data[5]

                apps.append({
                    'id': ref_split[0],
                    'name': ref_split[0].split('.')[-1].capitalize(),
                    'ref': data[0],
                    'arch': ref_split[1],
                    'branch': ref_split[2],
                    'description': None,
                    'origin': data[1],
                    'runtime': runtime,
                    'installation': 'user' if 'user' in data[5] else 'system',
                    'version': ref_split[2] if runtime else None
                })

    else:
        name_col = '' if version < VERSION_1_3 else 'name,'
        cols = f'application,ref,arch,branch,description,origin,options,{name_col}version'
        app_list = new_subprocess(('flatpak', 'list', f'--columns={cols}'), lang=None)

        for o in app_list.stdout:
            if o:
                data = o.decode().strip().split('\t')
                runtime = 'runtime' in data[6]

                if version < VERSION_1_3:
                    name = data[0].split('.')[-1]

                    if len(data) > 7 and data[7]:
                        app_ver = data[7]
                    elif runtime:
                        app_ver = data[3]
                    else:
                        app_ver = None
                else:
                    name = data[7]

                    if len(data) > 8 and data[8]:
                        app_ver = data[8]
                    elif runtime:
                        app_ver = data[3]
                    else:
                        app_ver = None

                apps.append({'id': data[0],
                             'name': name,
                             'ref': data[1],
                             'arch': data[2],
                             'branch': data[3],
                             'description': data[4],
                             'origin': data[5],
                             'runtime': runtime,
                             'installation': 'user' if 'user' in data[6] else 'system',
                             'version': app_ver})
    return apps


def update(app_ref: str, installation: str, version: Tuple[str, ...], related: bool = False, deps: bool = False) \
        -> SimpleProcess:
    cmd = ['flatpak', 'update', '-y', app_ref, f'--{installation}']

    if not related:
        cmd.append('--no-related')

    if not deps:
        cmd.append('--no-deps')

    return SimpleProcess(cmd=cmd, extra_paths={EXPORTS_PATH}, shell=True,
                         lang=DEFAULT_LANG if version < VERSION_1_12 else None)


def full_update(version: VERSION_1_12) -> SimpleProcess:
    return SimpleProcess(cmd=('flatpak', 'update', '-y'), extra_paths={EXPORTS_PATH}, shell=True,
                         lang=DEFAULT_LANG if version < VERSION_1_12 else None)


def uninstall(app_ref: str, installation: str, version: Tuple[str, ...]) -> SimpleProcess:
    return SimpleProcess(cmd=('flatpak', 'uninstall', app_ref, '-y', f'--{installation}'),
                         extra_paths={EXPORTS_PATH},
                         lang=DEFAULT_LANG if version < VERSION_1_12 else None,
                         shell=True)


def _new_updates() -> Dict[str, Set[str]]:
    return {'full': set(), 'partial': set()}


def list_updates_as_str(version: Tuple[str, ...]) -> Dict[str, Set[str]]:
    sys_updates, user_updates = _new_updates(), _new_updates()

    threads = []
    for type_, output in (('system', sys_updates), ('user', user_updates)):
        fill = Thread(target=fill_updates, args=(version, type_, output), daemon=True)
        fill.start()
        threads.append(fill)

    for t in threads:
        t.join()

    all_updates = _new_updates()

    for updates in (sys_updates, user_updates):
        if updates:
            for key, val in updates.items():
                if val:
                    all_updates[key].update(val)

    return all_updates


def list_required_runtime_updates(installation: str) -> Optional[List[Tuple[str, str]]]:
    """
    Return a list of tuples composed by the reference and the origin.
    e.g: ('runtime/org.gnome.Desktop/42/x86_64', 'flathub')
    """
    _, updates = system.execute(f'flatpak update --{installation}', shell=True,
                                custom_env=system.gen_env())

    if updates:
        return RE_REQUIRED_RUNTIME.findall(updates)


def fill_updates(version: Tuple[str, ...], installation: str, res: Dict[str, Set[str]]):
    if version < VERSION_1_2:
        try:
            output = run_cmd(f'flatpak update --no-related --no-deps --{installation}', ignore_return_code=True)

            if f'Updating in {installation}' in output:
                for line in output.split(f'Updating in {installation}:\n')[1].split('\n'):
                    if not line.startswith('Is this ok'):
                        res['full'].add('{}/{}'.format(installation, line.split('\t')[0].strip()))
        except Exception:
            traceback.print_exc()
    else:
        updates = new_subprocess(('flatpak', 'update', f'--{installation}', '--no-deps')).stdout

        reg = r'[0-9]+\.\s+.+'

        try:
            for o in new_subprocess(('grep', '-E', reg, '-o', '--color=never'), stdin=updates).stdout:
                if o:
                    line_split = o.decode().strip().split('\t')

                    if len(line_split) >= 5:
                        if version >= VERSION_1_5:
                            update_id = f'{line_split[2]}/{line_split[3]}/{installation}'

                            if len(line_split) >= 6:
                                update_id = f'{update_id}/{line_split[5]}'

                        elif version >= VERSION_1_2:
                            update_id = f'{line_split[2]}/{line_split[4]}/{installation}'

                            if len(line_split) >= 6:
                                update_id = f'{update_id}/{line_split[5]}'
                        else:
                            update_id = f'{line_split[2]}/{line_split[4]}/{installation}'

                        if version >= VERSION_1_3 and len(line_split) >= 6:
                            if line_split[4].strip().lower() in OPERATION_UPDATE_SYMBOLS:
                                if '(partial)' in line_split[-1]:
                                    res['partial'].add(update_id)
                                else:
                                    res['full'].add(update_id)
                        else:
                            res['full'].add(update_id)
        except Exception:
            traceback.print_exc()


def downgrade(app_ref: str, commit: str, installation: str, root_password: Optional[str], version: Tuple[str, ...]) -> SimpleProcess:
    cmd = ('flatpak', 'update', '--no-related', '--no-deps', f'--commit={commit}', app_ref, '-y', f'--{installation}')

    return SimpleProcess(cmd=cmd,
                         root_password=root_password if installation == 'system' else None,
                         extra_paths={EXPORTS_PATH},
                         lang=DEFAULT_LANG if version < VERSION_1_12 else None,
                         success_phrases={'Changes complete.', 'Updates complete.'} if version < VERSION_1_12 else None,
                         wrong_error_phrases={'Warning'} if version < VERSION_1_12 else None)


def get_app_commits(app_ref: str, origin: str, installation: str, handler: ProcessHandler) -> Optional[List[str]]:
    try:
        p = SimpleProcess(('flatpak', 'remote-info', '--log', origin, app_ref, f'--{installation}'))
        success, output = handler.handle_simple(p)
        if output.startswith('error:'):
            return
        else:
            return re.findall(r'Commit+:\s(.+)', output)
    except Exception:
        raise NoInternetException()


def parse_commit_date(raw: str) -> datetime:
    """Parse a `flatpak remote-info --log` Date line — always UTC ('+0000') — and convert it to
    the local timezone, returned as a *naive* local wall-clock. Naive-local keeps the displayed
    string clean (no `+00:00` offset suffix once ISO-formatted) while showing the user their own
    time instead of UTC, which not everyone recognises."""
    return datetime.strptime(raw, '%Y-%m-%d %H:%M:%S %z').astimezone().replace(tzinfo=None)


def get_app_commits_data(app_ref: str, origin: str, installation: str, full_str: bool = True) -> List[dict]:
    log = run_cmd(f'flatpak remote-info --log {origin} {app_ref} --{installation}')

    if not log:
        raise NoInternetException()

    res = re.findall(r'(Commit|Subject|Date):\s(.+)', log)

    commits = []

    commit = {}

    for idx, data in enumerate(res):
        attr = data[0].strip().lower()
        commit[attr] = data[1].strip()

        if attr == 'commit':
            commit[attr] = commit[attr] if full_str else commit[attr][0:8]

        if attr == 'date':
            try:
                commit[attr] = parse_commit_date(commit[attr])
            except ValueError:
                pass  # unexpected date format → leave the raw string rather than break history

        if (idx + 1) % 3 == 0:
            commits.append(commit)
            commit = {}

    return commits


def search(version: Tuple[str, ...], word: str, installation: str, app_id: bool = False) -> Optional[List[dict]]:

    res = run_cmd(f'flatpak search {word} --{installation}', lang=None)

    if not res:
        return

    found = None
    split_res = res.strip().split('\n')

    if split_res and '\t' in split_res[0]:
        found = []
        for info in split_res:
            if info:
                info_list = info.split('\t')
                if version >= VERSION_1_3:
                    id_ = info_list[2].strip()

                    if app_id and id_ != word:
                        continue

                    pkg_ver = info_list[3].strip()
                    app = {
                        'name': info_list[0].strip(),
                        'description': info_list[1].strip(),
                        'id': id_,
                        'version': pkg_ver,
                        'latest_version': pkg_ver,
                        'branch': info_list[4].strip(),
                        'origin': info_list[5].strip(),
                        'runtime': False,
                        'arch': None,  # unknown at this moment,
                        'ref': None  # unknown at this moment
                    }
                elif version >= VERSION_1_2:
                    id_ = info_list[1].strip()

                    if app_id and id_ != word:
                        continue

                    desc = info_list[0].split('-')
                    pkg_ver = info_list[2].strip()
                    app = {
                        'name': desc[0].strip(),
                        'description': desc[1].strip(),
                        'id': id_,
                        'version': pkg_ver,
                        'latest_version': pkg_ver,
                        'branch': info_list[3].strip(),
                        'origin': info_list[4].strip(),
                        'runtime': False,
                        'arch': None,  # unknown at this moment,
                        'ref': None  # unknown at this moment
                    }
                else:
                    id_ = info_list[0].strip()

                    if app_id and id_ != word:
                        continue

                    pkg_ver = info_list[1].strip()
                    app = {
                        'name': '',
                        'description': info_list[4].strip(),
                        'id': id_,
                        'version': pkg_ver,
                        'latest_version': pkg_ver,
                        'branch': info_list[2].strip(),
                        'origin': info_list[3].strip(),
                        'runtime': False,
                        'arch': None,  # unknown at this moment,
                        'ref': None  # unknown at this moment
                    }

                found.append(app)

                if app_id and len(found) > 0:
                    break

    return found


def install(app_id: str, origin: str, installation: str, version: Tuple[str, ...]) -> SimpleProcess:
    return SimpleProcess(cmd=('flatpak', 'install', origin, app_id, '-y', f'--{installation}'),
                         extra_paths={EXPORTS_PATH},
                         lang=DEFAULT_LANG if version < VERSION_1_12 else None,
                         wrong_error_phrases={'Warning'} if version < VERSION_1_12 else None,
                         shell=True)


def set_default_remotes(installation: str, root_password: Optional[str] = None) -> SimpleProcess:
    cmd = ('flatpak', 'remote-add', '--if-not-exists', 'flathub', f'{FLATHUB_URL}/repo/flathub.flatpakrepo',
           f'--{installation}')

    return SimpleProcess(cmd, root_password=root_password)


def has_remotes_set() -> bool:
    return bool(run_cmd('flatpak remotes').strip())


def list_remotes() -> Dict[str, Set[str]]:
    res = {'system': set(), 'user': set()}
    output = run_cmd('flatpak remotes').strip()

    if output:
        lines = output.split('\n')

        for line in lines:
            remote = line.split('\t')

            if 'system' in remote[1]:
                res['system'].add(remote[0].strip())
            elif 'user' in remote[1]:
                res['user'].add(remote[0].strip())

    return res


def run(app_id: str):
    subprocess.Popen((f'flatpak run {app_id}',), shell=True, env={**os.environ})


def map_installed_sizes() -> Dict[str, float]:
    """Map each installed flatpak id -> on-disk size in bytes (the `flatpak list` 'size'
    column, e.g. '287.9 MB' — number and unit are separated by a non-breaking space)."""
    res = {}
    output = run_cmd('flatpak list --columns=application,size')

    if not output:
        return res

    for line in output.split('\n'):
        app_id, _, size_str = line.partition('\t')
        app_id = app_id.strip()
        if not app_id or '\t' not in line:
            continue

        parts = size_str.split()  # str.split() treats the NBSP as whitespace too
        if len(parts) >= 2:
            size = size_to_byte(parts[0], parts[1])
            if size is not None:
                res[app_id] = size

    return res


def map_update_download_size(app_ids: Iterable[str], installation: str, version: Tuple[str, ...]) -> Dict[str, float]:
    success, output = ProcessHandler().handle_simple(SimpleProcess(('flatpak', 'update', f'--{installation}',
                                                                    '--no-deps')))
    if version >= VERSION_1_2:
        res = {}
        p = re.compile(r'^\d+.\t')
        p2 = re.compile(r'([0-9.?a-zA-Z]+\s?)')
        for l in output.split('\n'):
            if l:
                line = l.strip()

                if line:
                    found = p.match(line)

                    if found:
                        line_split = line.split('\t')
                        line_id = line_split[2].strip()

                        related_id = [appid for appid in app_ids if appid == line_id]

                        if related_id and len(line_split) >= 7:
                            size_tuple = p2.findall(line_split[6])

                            if size_tuple:
                                if version >= VERSION_1_5:
                                    size = size_tuple[0].split('?')

                                    if size and len(size) > 1:
                                        try:
                                            res[related_id[0].strip()] = size_to_byte(size[0], size[1].strip())
                                        except Exception:
                                            traceback.print_exc()
                                else:
                                    try:
                                        res[related_id[0].strip()] = size_to_byte(size_tuple[0], size_tuple[1].strip())
                                    except Exception:
                                        traceback.print_exc()
        return res
