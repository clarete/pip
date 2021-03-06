import pytest

from pip.exceptions import CommandError
from pip.baseparser import create_main_parser
from pip.basecommand import ERROR, SUCCESS
from pip.commands.help import HelpCommand
from pip.commands import commands
from mock import Mock
from tests.lib import reset_env


def test_run_method_should_return_sucess_when_finds_command_name():
    """
    Test HelpCommand.run for existing command
    """
    options_mock = Mock()
    args = ('freeze',)
    help_cmd = HelpCommand(create_main_parser())
    status = help_cmd.run(options_mock, args)
    assert status == SUCCESS


def test_run_method_should_return_sucess_when_command_name_not_specified():
    """
    Test HelpCommand.run when there are no args
    """
    options_mock = Mock()
    args = ()
    help_cmd = HelpCommand(create_main_parser())
    status = help_cmd.run(options_mock, args)
    assert status == SUCCESS


def test_run_method_should_raise_command_error_when_command_does_not_exist():
    """
    Test HelpCommand.run for non-existing command
    """
    options_mock = Mock()
    args = ('mycommand',)
    help_cmd = HelpCommand(create_main_parser())

    with pytest.raises(CommandError):
        help_cmd.run(options_mock, args)


def test_help_command_should_exit_status_ok_when_command_exists():
    """
    Test `help` command for existing command
    """
    script = reset_env()
    result = script.pip('help', 'freeze')
    assert result.returncode == SUCCESS


def test_help_command_should_exit_status_ok_when_no_command_is_specified():
    """
    Test `help` command for no command
    """
    script = reset_env()
    result = script.pip('help')
    assert result.returncode == SUCCESS


def test_help_command_should_exit_status_error_when_command_does_not_exist():
    """
    Test `help` command for non-existing command
    """
    script = reset_env()
    result = script.pip('help', 'mycommand', expect_error=True)
    assert result.returncode == ERROR

def test_help_commands_equally_functional():
    """
    Test if `pip help` and 'pip --help' behave the same way.
    """
    script = reset_env()

    results = list(map(script.pip, ('help', '--help')))
    results.append(script.pip())

    out = map(lambda x: x.stdout, results)
    ret = map(lambda x: x.returncode, results)

    msg = '"pip --help" != "pip help" != "pip"'
    assert len(set(out)) == 1, 'output of: ' + msg
    assert sum(ret) == 0, 'exit codes of: ' + msg

    for name, cls in commands.items():
        if cls.hidden: continue
        assert script.pip('help', name).stdout == \
               script.pip(name, '--help').stdout
