from unittest.mock import Mock, patch

from atlas.view.util.util import close_notification, notify_user


@patch('atlas.view.util.util.get_default_icon_path', return_value='/tmp/atlas icon.png')
@patch('atlas.view.util.util.subprocess.run')
def test_attention_notification_uses_safe_arguments_and_returns_id(run, _icon):
    run.return_value = Mock(returncode=0, stdout='42\n')

    notification_id = notify_user(
        "Review pkg'; touch /tmp/not-run",
        title='Atlas needs your attention', urgency='critical', expire_time=0,
        print_id=True)

    assert notification_id == 42
    argv = run.call_args.args[0]
    assert isinstance(argv, list)
    assert argv[-2:] == ['Atlas needs your attention', "Review pkg'; touch /tmp/not-run"]
    assert ['--urgency', 'critical'] == argv[argv.index('--urgency'):argv.index('--urgency') + 2]
    assert ['--expire-time', '0'] == argv[argv.index('--expire-time'):argv.index('--expire-time') + 2]
    assert 'string:desktop-entry:atlas-pm' in argv


@patch('atlas.view.util.util.subprocess.run')
def test_close_notification_replaces_it_with_one_millisecond_transient(run):
    close_notification(42)

    argv = run.call_args.args[0]
    assert ['--replace-id', '42'] == argv[argv.index('--replace-id'):argv.index('--replace-id') + 2]
    assert ['--expire-time', '1'] == argv[argv.index('--expire-time'):argv.index('--expire-time') + 2]
    assert '--transient' in argv
