import os
import tempfile
import textwrap

from tests.lib import reset_env, clear_environ, path_to_url, find_links


def test_options_from_env_vars():
    """
    Test if ConfigOptionParser reads env vars (e.g. not using PyPI here)

    """
    environ = clear_environ(os.environ.copy())
    environ['PIP_NO_INDEX'] = '1'
    script = reset_env(environ)
    result = script.pip('install', '-vvv', 'INITools', expect_error=True)
    assert "Ignoring indexes:" in result.stdout, str(result)
    assert "DistributionNotFound: No distributions at all found for INITools" in result.stdout


def test_command_line_options_override_env_vars():
    """
    Test that command line options override environmental variables.

    """
    environ = clear_environ(os.environ.copy())
    environ['PIP_INDEX_URL'] = 'http://b.pypi.python.org/simple/'
    script = reset_env(environ)
    result = script.pip('install', '-vvv', 'INITools', expect_error=True)
    assert "Getting page http://b.pypi.python.org/simple/INITools" in result.stdout
    script = reset_env(environ)
    result = script.pip('install', '-vvv', '--index-url', 'http://download.zope.org/ppix', 'INITools', expect_error=True)
    assert "b.pypi.python.org" not in result.stdout
    assert "Getting page http://download.zope.org/ppix" in result.stdout


def test_env_vars_override_config_file():
    """
    Test that environmental variables override settings in config files.

    """
    fd, config_file = tempfile.mkstemp('-pip.cfg', 'test-')
    try:
        _test_env_vars_override_config_file(config_file)
    finally:
        # `os.close` is a workaround for a bug in subprocess
        # http://bugs.python.org/issue3210
        os.close(fd)
        os.remove(config_file)


def _test_env_vars_override_config_file(config_file):
    environ = clear_environ(os.environ.copy())
    environ['PIP_CONFIG_FILE'] = config_file # set this to make pip load it
    script = reset_env(environ)
    # It's important that we test this particular config value ('no-index')
    # because their is/was a bug which only shows up in cases in which
    # 'config-item' and 'config_item' hash to the same value modulo the size
    # of the config dictionary.
    (script.scratch_path/config_file).write(textwrap.dedent("""\
        [global]
        no-index = 1
        """))
    result = script.pip('install', '-vvv', 'INITools', expect_error=True)
    assert "DistributionNotFound: No distributions at all found for INITools" in result.stdout
    environ['PIP_NO_INDEX'] = '0'
    script = reset_env(environ)
    result = script.pip('install', '-vvv', 'INITools', expect_error=True)
    assert "Successfully installed INITools" in result.stdout


def test_command_line_append_flags():
    """
    Test command line flags that append to defaults set by environmental variables.

    """
    environ = clear_environ(os.environ.copy())
    environ['PIP_FIND_LINKS'] = 'http://pypi.pinaxproject.com'
    script = reset_env(environ)
    result = script.pip('install', '-vvv', 'INITools', expect_error=True)
    assert "Analyzing links from page http://pypi.pinaxproject.com" in result.stdout
    script = reset_env(environ)
    result = script.pip('install', '-vvv', '--find-links', find_links, 'INITools', expect_error=True)
    assert "Analyzing links from page http://pypi.pinaxproject.com" in result.stdout
    assert "Skipping link %s" % find_links in result.stdout


def test_command_line_appends_correctly():
    """
    Test multiple appending options set by environmental variables.

    """
    environ = clear_environ(os.environ.copy())
    environ['PIP_FIND_LINKS'] = 'http://pypi.pinaxproject.com %s' % find_links
    script = reset_env(environ)
    result = script.pip('install', '-vvv', 'INITools', expect_error=True)

    assert "Analyzing links from page http://pypi.pinaxproject.com" in result.stdout, result.stdout
    assert "Skipping link %s" % find_links in result.stdout


def test_config_file_override_stack():
    """
    Test config files (global, overriding a global config with a
    local, overriding all with a command line flag).

    """
    fd, config_file = tempfile.mkstemp('-pip.cfg', 'test-')
    try:
        _test_config_file_override_stack(config_file)
    finally:
        # `os.close` is a workaround for a bug in subprocess
        # http://bugs.python.org/issue3210
        os.close(fd)
        os.remove(config_file)


def _test_config_file_override_stack(config_file):
    environ = clear_environ(os.environ.copy())
    environ['PIP_CONFIG_FILE'] = config_file # set this to make pip load it
    script = reset_env(environ)
    (script.scratch_path/config_file).write(textwrap.dedent("""\
        [global]
        index-url = http://download.zope.org/ppix
        """))
    result = script.pip('install', '-vvv', 'INITools', expect_error=True)
    assert "Getting page http://download.zope.org/ppix/INITools" in result.stdout
    script = reset_env(environ)
    (script.scratch_path/config_file).write(textwrap.dedent("""\
        [global]
        index-url = http://download.zope.org/ppix
        [install]
        index-url = http://pypi.appspot.com/
        """))
    result = script.pip('install', '-vvv', 'INITools', expect_error=True)
    assert "Getting page http://pypi.appspot.com/INITools" in result.stdout
    result = script.pip('install', '-vvv', '--index-url', 'http://pypi.python.org/simple', 'INITools', expect_error=True)
    assert "Getting page http://download.zope.org/ppix/INITools" not in result.stdout
    assert "Getting page http://pypi.appspot.com/INITools" not in result.stdout
    assert "Getting page http://pypi.python.org/simple/INITools" in result.stdout


def test_log_file_no_directory():
    """
    Test opening a log file with no directory name.

    """
    from pip.basecommand import open_logfile
    fp = open_logfile('testpip.log')
    fp.write('can write')
    fp.close()
    assert os.path.exists(fp.name)
    os.remove(fp.name)
