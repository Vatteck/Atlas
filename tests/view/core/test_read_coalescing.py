import os
import threading
import unittest
from unittest.mock import Mock, patch

from atlas.api.abstract.controller import SearchResult
from atlas.view.core.controller import GenericSoftwareManager


def _new_manager():
    context = Mock()
    context.is_internet_available.return_value = True
    context.i18n = {}
    return GenericSoftwareManager(managers=[], context=context,
                                  config={'system': {'single_dependency_checking': False}})


class ReadInstalledCoalescingTest(unittest.TestCase):
    """Concurrent full read_installed calls share one underlying pass (leader/follower);
    sequential calls always read fresh. See docs/plans/2026-07-17-coalesce-read-installed.md."""

    def test_concurrent_full_reads_share_one_pass(self):
        manager = _new_manager()
        inner_started = threading.Event()
        release_inner = threading.Event()
        calls = []

        def slow_read(*args, **kwargs):
            calls.append(1)
            inner_started.set()
            release_inner.wait(5)
            return SearchResult(['pkg'], None, 1)

        results = []
        with patch.object(manager, '_read_installed_now', side_effect=slow_read):
            leader = threading.Thread(target=lambda: results.append(manager.read_installed()))
            leader.start()
            self.assertTrue(inner_started.wait(5), 'leader read never started')

            follower = threading.Thread(target=lambda: results.append(manager.read_installed()))
            follower.start()
            release_inner.set()
            leader.join(5)
            follower.join(5)

        self.assertEqual(1, len(calls), 'concurrent calls must run one underlying read')
        self.assertEqual(2, len(results))
        self.assertIs(results[0], results[1], 'followers share the leader result object')

    def test_sequential_full_reads_do_not_share(self):
        manager = _new_manager()
        with patch.object(manager, '_read_installed_now',
                          side_effect=[SearchResult([], None, 0), SearchResult([], None, 0)]) as inner:
            r1 = manager.read_installed()
            r2 = manager.read_installed()
        self.assertEqual(2, inner.call_count, 'a call arriving after completion reads fresh')
        self.assertIsNot(r1, r2)

    def test_typed_reads_bypass_coalescing(self):
        manager = _new_manager()
        inner_started = threading.Event()
        release_inner = threading.Event()

        def slow_read(disk_loader=None, limit=-1, only_apps=False, pkg_types=None, internet_available=None):
            if not pkg_types:
                inner_started.set()
                release_inner.wait(5)
            return SearchResult([], None, 0)

        with patch.object(manager, '_read_installed_now', side_effect=slow_read) as inner:
            leader = threading.Thread(target=manager.read_installed)
            leader.start()
            self.assertTrue(inner_started.wait(5))
            manager.read_installed(pkg_types={str})  # typed read must not wait on the full read
            release_inner.set()
            leader.join(5)
        self.assertEqual(2, inner.call_count)

    def test_leader_exception_propagates_to_follower_and_next_call_recovers(self):
        manager = _new_manager()
        inner_started = threading.Event()
        release_inner = threading.Event()
        boom = RuntimeError('read failed')

        def failing_read(*args, **kwargs):
            inner_started.set()
            release_inner.wait(5)
            raise boom

        errors = []

        def follow():
            try:
                manager.read_installed()
            except RuntimeError as e:
                errors.append(e)

        with patch.object(manager, '_read_installed_now', side_effect=failing_read):
            leader = threading.Thread(target=follow)
            leader.start()
            self.assertTrue(inner_started.wait(5))
            follower = threading.Thread(target=follow)
            follower.start()
            release_inner.set()
            leader.join(5)
            follower.join(5)

        self.assertEqual([boom, boom], errors, 'both callers see the failure')

        # the flight slot must be cleared — the next call runs a fresh read
        with patch.object(manager, '_read_installed_now', return_value=SearchResult([], None, 0)) as inner:
            manager.read_installed()
        inner.assert_called_once()

    def test_kill_switch_env_disables_coalescing(self):
        manager = _new_manager()
        inner_started = threading.Event()
        release_inner = threading.Event()
        calls = []

        def slow_read(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                inner_started.set()
                release_inner.wait(5)
            return SearchResult([], None, 0)

        with patch.dict(os.environ, {'ATLAS_NO_READ_COALESCING': '1'}):
            with patch.object(manager, '_read_installed_now', side_effect=slow_read):
                leader = threading.Thread(target=manager.read_installed)
                leader.start()
                self.assertTrue(inner_started.wait(5))
                manager.read_installed()  # would block as a follower if coalescing were active
                release_inner.set()
                leader.join(5)
        self.assertEqual(2, len(calls), 'kill switch restores independent reads')
