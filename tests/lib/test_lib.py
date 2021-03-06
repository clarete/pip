"""Test the test support."""
import filecmp
import re
from os.path import join, isdir

from tests.lib import reset_env, src_folder


def test_tmp_dir_exists_in_env():
    """
    Test that $TMPDIR == env.temp_path and path exists and env.assert_no_temp() passes (in fast env)
    """
    #need these tests to ensure the assert_no_temp feature of scripttest is working
    env = reset_env()
    env.assert_no_temp() #this fails if env.tmp_path doesn't exist
    assert env.environ['TMPDIR'] == env.temp_path
    assert isdir(env.temp_path)


def test_correct_pip_version():
    """
    Check we are running proper version of pip in run_pip.
    """
    script = reset_env()

    # output is like:
    # pip PIPVERSION from PIPDIRECTORY (python PYVERSION)
    result = script.pip('--version')

    # compare the directory tree of the invoked pip with that of this source distribution
    dir = re.match(r'pip \d(\.[\d])+(\.?(rc|dev|pre|post)\d+)? from (.*) \(python \d(.[\d])+\)$',
                   result.stdout).group(4)
    pip_folder = join(src_folder, 'pip')
    pip_folder_outputed = join(dir, 'pip')

    diffs = filecmp.dircmp(pip_folder, pip_folder_outputed)

    # If any non-matching .py files exist, we have a problem: run_pip
    # is picking up some other version!  N.B. if this project acquires
    # primary resources other than .py files, this code will need
    # maintenance
    mismatch_py = [x for x in diffs.left_only + diffs.right_only + diffs.diff_files if x.endswith('.py')]
    assert not mismatch_py, 'mismatched source files in %r and %r: %r'% (pip_folder, pip_folder_outputed, mismatch_py)

