
import util

def test_shell_runner():
    runner = util.ShellRunner()

    code, stdout, stderr = runner.run('echo 1 2 3', capture=True)
    assert code == 0, 'successful status'
    assert stdout == '1 2 3\n', 'stdout'
    assert stderr == '', 'stderr empty'

    code, stdout, stderr = runner.run('echo 1 2 3 >&2', capture=True)
    assert stdout == '', 'stdout empty'
    assert stderr == '1 2 3\n', 'stderr'
    
    code, stdout, stderr = runner.run('false', capture=True)
    assert code != 0, 'unsuccessful status'

