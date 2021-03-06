# #!/usr/bin/env python
import os
import sys
import re
import atexit
import textwrap
import site
import subprocess

import scripttest
import virtualenv

from pip.backwardcompat import uses_pycache

from tests.lib.path import Path, curdir, u


pyversion = sys.version[:3]
pyversion_nodot = "%d%d" % (sys.version_info[0], sys.version_info[1])
tests_lib = Path(__file__).abspath.folder  # pip/tests/lib
tests_root = tests_lib.folder  # pip/tests
tests_cache = os.path.join(tests_root, 'tests_cache')  # pip/tests/tests_cache
src_folder = tests_root.folder  # pip/
tests_data = os.path.join(tests_root, 'data')  # pip/tests/data
packages = os.path.join(tests_data, 'packages')  # pip/tests/data/packages

fast_test_env_root = tests_cache / 'test_ws'


def path_to_url(path):
    """
    Convert a path to URI. The path will be made absolute and
    will not have quoted path parts.
    (adapted from pip.util)
    """
    path = os.path.normpath(os.path.abspath(path))
    drive, path = os.path.splitdrive(path)
    filepath = path.split(os.path.sep)
    url = '/'.join(filepath)
    if drive:
        return 'file:///' + drive + url
    return 'file://' + url

find_links = path_to_url(os.path.join(tests_data, 'packages'))
find_links2 = path_to_url(os.path.join(tests_data, 'packages2'))


def clear_environ(environ):
    return dict(((k, v) for k, v in environ.items()
                if not k.lower().startswith('pip_')))


def reset_env(environ=None, system_site_packages=False):
    """
    Return a test environment.

    Keyword arguments:
    environ: an environ object to use.
    system_site_packages: create a virtualenv that simulates
        --system-site-packages.
    """
    # Clear our previous test directory
    fast_test_env_root.rmtree()

    # Create a virtual environment
    venv_root = fast_test_env_root.join(".virtualenv")
    virtualenv.create_environment(venv_root,
        never_download=True,
        no_pip=True,
    )

    # On Python < 3.3 we don't have subprocess.DEVNULL
    try:
        devnull = subprocess.DEVNULL
    except AttributeError:
        devnull = open(os.devnull, "wb")

    # Install our development version of pip install the virtual environment
    p = subprocess.Popen(
        [venv_root.join("bin/python"), "setup.py", "develop"],
        stderr=subprocess.STDOUT,
        stdout=devnull,
    )
    p.communicate()

    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, p.args)

    # Create our pip test environment
    env = TestPipEnvironment(fast_test_env_root,
        environ=environ,
        virtualenv=venv_root,
        ignore_hidden=False,
        start_clear=False,
        capture_temp=True,
        assert_no_temp=True,
    )

    if system_site_packages:
        # Testing often occurs starting from a private virtualenv (e.g. tox)
        #   from that context, you can't successfully use
        #   virtualenv.create_environment to create a 'system-site-packages'
        #   virtualenv hence, this workaround
        env.lib_path.join("no-global-site-packages.txt").rm()

    return env


class TestFailure(AssertionError):
    """
    An "assertion" failed during testing.
    """
    pass


class TestPipResult(object):

    def __init__(self, impl, verbose=False):
        self._impl = impl

        if verbose:
            print(self.stdout)
            if self.stderr:
                print('======= stderr ========')
                print(self.stderr)
                print('=======================')

    def __getattr__(self, attr):
        return getattr(self._impl, attr)

    if sys.platform == 'win32':

        @property
        def stdout(self):
            return self._impl.stdout.replace('\r\n', '\n')

        @property
        def stderr(self):
            return self._impl.stderr.replace('\r\n', '\n')

        def __str__(self):
            return str(self._impl).replace('\r\n', '\n')
    else:
        # Python doesn't automatically forward __str__ through __getattr__

        def __str__(self):
            return str(self._impl)

    def assert_installed(self, pkg_name, editable=True, with_files=[],
                         without_files=[], without_egg_link=False,
                         use_user_site=False):
        e = self.test_env

        if editable:
            pkg_dir = e.venv/'src'/pkg_name.lower()
        else:
            without_egg_link = True
            pkg_dir = e.site_packages/pkg_name

        if use_user_site:
            egg_link_path = e.user_site / pkg_name + '.egg-link'
        else:
            egg_link_path = e.site_packages / pkg_name + '.egg-link'

        if without_egg_link:
            if egg_link_path in self.files_created:
                raise TestFailure('unexpected egg link file created: '\
                                  '%r\n%s' % (egg_link_path, self))
        else:
            if not egg_link_path in self.files_created:
                raise TestFailure('expected egg link file missing: '\
                                  '%r\n%s' % (egg_link_path, self))

            egg_link_file = self.files_created[egg_link_path]

            if not (# FIXME: I don't understand why there's a trailing . here
                    egg_link_file.bytes.endswith('.')
                and egg_link_file.bytes[:-1].strip().endswith(pkg_dir)):
                raise TestFailure(textwrap.dedent(u('''\
                Incorrect egg_link file %r
                Expected ending: %r
                ------- Actual contents -------
                %s
                -------------------------------''' % (
                        egg_link_file,
                        pkg_dir + u('\n.'),
                        egg_link_file.bytes))))

        if use_user_site:
            pth_file = e.user_site/'easy-install.pth'
        else:
            pth_file = e.site_packages/'easy-install.pth'

        if (pth_file in self.files_updated) == without_egg_link:
            raise TestFailure('%r unexpectedly %supdated by install' % (
                pth_file, (not without_egg_link and 'not ' or '')))

        if (pkg_dir in self.files_created) == (curdir in without_files):
            raise TestFailure(textwrap.dedent('''\
            expected package directory %r %sto be created
            actually created:
            %s
            ''') % (
                pkg_dir,
                (curdir in without_files and 'not ' or ''),
                sorted(self.files_created.keys())))

        for f in with_files:
            if not (pkg_dir/f).normpath in self.files_created:
                raise TestFailure('Package directory %r missing '\
                                  'expected content %r' % (pkg_dir, f))

        for f in without_files:
            if (pkg_dir/f).normpath in self.files_created:
                raise TestFailure('Package directory %r has '\
                                  'unexpected content %f' % (pkg_dir, f))


class TestPipEnvironment(scripttest.TestFileEnvironment):
    """
    A specialized TestFileEnvironment for testing pip
    """

    #
    # Attribute naming convention
    # ---------------------------
    #
    # Instances of this class have many attributes representing paths
    # in the filesystem.  To keep things straight, absolute paths have
    # a name of the form xxxx_path and relative paths have a name that
    # does not end in '_path'.

    exe = sys.platform == 'win32' and '.exe' or ''
    verbose = False

    def __init__(self, base_path, *args, **kwargs):
        # Make our base_path a test.lib.path.Path object
        base_path = Path(base_path)

        # Store paths related to the virtual environment
        _virtualenv = kwargs.pop("virtualenv")
        venv, lib, include, bin = virtualenv.path_locations(_virtualenv)
        self.venv_path = venv
        self.lib_path = lib
        self.include_path = include
        self.bin_path = bin

        if hasattr(sys, "pypy_version_info"):
            self.site_packages_path = self.venv_path.join("site-packages")
        else:
            self.site_packages_path = self.lib_path.join("site-packages")

        self.user_base_path = self.venv_path.join("user")
        self.user_site_path = self.venv_path.join(
            "user",
            site.USER_SITE[len(site.USER_BASE) + 1:],
        )

        # Create a Directory to use as a scratch pad
        self.scratch_path = base_path.join("scratch").mkdir()

        # Set our default working directory
        kwargs.setdefault("cwd", self.scratch_path)

        # Setup our environment
        environ = kwargs.get("environ")
        if environ is None:
            environ = os.environ.copy()

        environ["PIP_LOG_FILE"] = base_path.join("pip-log.txt")
        environ["PATH"] = Path.pathsep.join(
            [self.bin_path] + [environ.get("PATH", [])],
        )
        environ["PYTHONUSERBASE"] = self.user_base_path
        # Writing bytecode can mess up updated file detection
        environ["PYTHONDONTWRITEBYTECODE"] = "1"
        kwargs["environ"] = environ

        # Call the TestFileEnvironment __init__
        super(TestPipEnvironment, self).__init__(base_path, *args, **kwargs)

        # Expand our absolute path directories into relative
        for name in ["base", "venv", "lib", "include", "bin", "site_packages",
                     "user_base", "user_site", "scratch"]:
            real_name = "%s_path" % name
            setattr(self, name, getattr(self, real_name) - self.base_path)

        # Ensure the tmp dir exists, things break horribly if it doesn't
        self.temp_path.mkdir()

        # create easy-install.pth in user_site, so we always have it updated
        #   instead of created
        self.user_site_path.makedirs()
        self.user_site_path.join("easy-install.pth").touch()

    def _ignore_file(self, fn):
        if fn.endswith('__pycache__') or fn.endswith(".pyc"):
            result = True
        else:
            result = super(TestPipEnvironment, self)._ignore_file(fn)
        return result

    def run(self, *args, **kw):
        if self.verbose:
            print('>> running %s %s' % (args, kw))
        cwd = kw.pop('cwd', None)
        run_from = kw.pop('run_from', None)
        assert not cwd or not run_from, "Don't use run_from; it's going away"
        cwd = cwd or run_from or self.cwd
        return TestPipResult(super(TestPipEnvironment, self).run(cwd=cwd, *args, **kw), verbose=self.verbose)

    def pip(self, *args, **kwargs):
        return self.run("pip", *args, **kwargs)

    def pip_install_local(self, *args, **kwargs):
        return self.pip("install", "--no-index", "--find-links", find_links,
            *args, **kwargs
        )


# FIXME ScriptTest does something similar, but only within a single
# ProcResult; this generalizes it so states can be compared across
# multiple commands.  Maybe should be rolled into ScriptTest?
def diff_states(start, end, ignore=None):
    """
    Differences two "filesystem states" as represented by dictionaries
    of FoundFile and FoundDir objects.

    Returns a dictionary with following keys:

    ``deleted``
        Dictionary of files/directories found only in the start state.

    ``created``
        Dictionary of files/directories found only in the end state.

    ``updated``
        Dictionary of files whose size has changed (FIXME not entirely
        reliable, but comparing contents is not possible because
        FoundFile.bytes is lazy, and comparing mtime doesn't help if
        we want to know if a file has been returned to its earlier
        state).

    Ignores mtime and other file attributes; only presence/absence and
    size are considered.

    """
    ignore = ignore or []

    def prefix_match(path, prefix):
        if path == prefix:
            return True
        prefix = prefix.rstrip(os.path.sep) + os.path.sep
        return path.startswith(prefix)

    start_keys = set([k for k in start.keys()
                      if not any([prefix_match(k, i) for i in ignore])])
    end_keys = set([k for k in end.keys()
                    if not any([prefix_match(k, i) for i in ignore])])
    deleted = dict([(k, start[k]) for k in start_keys.difference(end_keys)])
    created = dict([(k, end[k]) for k in end_keys.difference(start_keys)])
    updated = {}
    for k in start_keys.intersection(end_keys):
        if (start[k].size != end[k].size):
            updated[k] = end[k]
    return dict(deleted=deleted, created=created, updated=updated)


def assert_all_changes(start_state, end_state, expected_changes):
    """
    Fails if anything changed that isn't listed in the
    expected_changes.

    start_state is either a dict mapping paths to
    scripttest.[FoundFile|FoundDir] objects or a TestPipResult whose
    files_before we'll test.  end_state is either a similar dict or a
    TestPipResult whose files_after we'll test.

    Note: listing a directory means anything below
    that directory can be expected to have changed.
    """
    start_files = start_state
    end_files = end_state
    if isinstance(start_state, TestPipResult):
        start_files = start_state.files_before
    if isinstance(end_state, TestPipResult):
        end_files = end_state.files_after

    diff = diff_states(start_files, end_files, ignore=expected_changes)
    if list(diff.values()) != [{}, {}, {}]:
        raise TestFailure('Unexpected changes:\n' + '\n'.join(
            [k + ': ' + ', '.join(v.keys()) for k, v in diff.items()]))

    # Don't throw away this potentially useful information
    return diff


def _create_test_package(script):
    script.scratch_path.join("version_pkg").mkdir()
    version_pkg_path = script.scratch_path/'version_pkg'
    version_pkg_path.join("version_pkg.py").write(textwrap.dedent("""
        def main():
            print('0.1')
    """))
    version_pkg_path.join("setup.py").write(textwrap.dedent("""
        from setuptools import setup, find_packages
        setup(
            name='version_pkg',
            version='0.1',
            packages=find_packages(),
            py_modules=['version_pkg'],
            entry_points=dict(console_scripts=['version_pkg=version_pkg:main'])
        )
    """))
    script.run('git', 'init', cwd=version_pkg_path)
    script.run('git', 'add', '.', cwd=version_pkg_path)
    script.run('git', 'commit', '-q',
            '--author', 'Pip <python-virtualenv@googlegroups.com>',
            '-am', 'initial version', cwd=version_pkg_path)
    return version_pkg_path


def _change_test_package_version(script, version_pkg_path):
    version_pkg_path.join("version_pkg.py").write(textwrap.dedent('''\
        def main():
            print("some different version")'''))
    script.run('git', 'clean', '-qfdx',
        cwd=version_pkg_path,
        expect_stderr=True,
    )
    script.run('git', 'commit', '-q',
            '--author', 'Pip <python-virtualenv@googlegroups.com>',
            '-am', 'messed version',
            cwd=version_pkg_path, expect_stderr=True)


def assert_raises_regexp(exception, reg, run, *args, **kwargs):
    """Like assertRaisesRegexp in unittest"""
    try:
        run(*args, **kwargs)
        assert False, "%s should have been thrown" % exception
    except Exception:
        e = sys.exc_info()[1]
        p = re.compile(reg)
        assert p.search(str(e)), str(e)


#
# This cleanup routine ensures that FastTestPipEnvironment doesn't leave an
# environment hanging around that might confuse the next test run.
#
atexit.register(fast_test_env_root.rmtree)
