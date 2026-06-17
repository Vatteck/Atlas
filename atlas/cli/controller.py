import json

from atlas.cli import __app_name__
from atlas.view.core.controller import GenericSoftwareManager


class CLIManager:

    def __init__(self, manager: GenericSoftwareManager):
        self.manager = manager

    def _print(self, msg: str):
        print('[{}] {}'.format(__app_name__, msg))

    def _arch_manager(self):
        """The arch gem manager (the one exposing the AUR client + cgit file fetch), or None."""
        for man in getattr(self.manager, 'managers', None) or []:
            if hasattr(man, 'aur_client') and hasattr(man, 'fetch_aur_file'):
                return man
        return None

    def audit_rescan(self, sample: int, fp_threshold: float, output_format: str):
        """Sample live AUR PKGBUILDs and report each audit rule's fire rate (rule-health check)."""
        from atlas.gems.arch import audit_rescan

        arch_man = self._arch_manager()
        if arch_man is None:
            self._print('Arch/AUR support is not available — cannot run the audit re-scan.')
            return

        names = arch_man.aur_client.download_names()
        if not names:
            self._print('Could not fetch the AUR package index (no names / no internet).')
            return

        if output_format != 'json':
            self._print(f'Sampling {min(sample, len(names))} of {len(names)} AUR PKGBUILDs '
                        '(advisory rule-health check)...')

        samples = audit_rescan.collect_samples(
            list(names), lambda n: arch_man.fetch_aur_file(n, 'PKGBUILD'), sample)
        counts, total = audit_rescan.aggregate_fire_counts(samples)
        report = audit_rescan.build_report(counts, total, fp_threshold)

        if output_format == 'json':
            print(audit_rescan.format_report_json(report))
        else:
            print(audit_rescan.format_report_text(report))

    def list_updates(self, output_format: str):
        updates = self.manager.list_updates()

        json_output = output_format == 'json'

        if not updates and not json_output:
            self._print('No updates available')
            return

        if not json_output:
            self._print('There are {} updates available:\n'.format(len(updates)))

            for idx, u in enumerate(updates):
                print('{}. Name: {}\tVersion: {}\tType: {}'.format(idx+1, u.name, u.version, u.type))
        else:
            print(json.dumps([u.__dict__ for u in updates]))
