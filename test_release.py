
from release import Release
from re import search, MULTILINE

class MockServiceJsonLoader:
    def __init__(self, metadata):
        self.metadata = metadata
        
    def load(self):
        return self.metadata

mock_service_json_loader = MockServiceJsonLoader({ 'TEAM' : 'some-team' })

def test_positional_args():
    release = Release(
        ['0'],
        {},
        service_json_loader=mock_service_json_loader
    )
    assert release.version == '0', 'version passed'

def test_component_name_arg():
    release = Release(
        '1 -c mycomp1'.split(' '),
        {},
        service_json_loader=mock_service_json_loader
    )
    assert release.component_name == 'mycomp1', 'short component name argument'
    
    release = Release(
        '2 --component-name=mycomp2'.split(' '),
        {},
        service_json_loader=mock_service_json_loader
    )
    assert release.component_name == 'mycomp2', 'long component name argument '
    
    release = Release(
        '3 --component-name mycomp3'.split(' '),
        {},
        service_json_loader=mock_service_json_loader
    )
    assert release.component_name == 'mycomp3', 'long component name argument with equals'

def test_component_name_env():
    release = Release(
        '4 -c mycomp4'.split(' '),
        { 'COMPONENT_NAME' : 'notmycomp4' },
        service_json_loader=mock_service_json_loader
    )
    assert release.component_name == 'mycomp4', 'argument overrides environment variable'
    
    release = Release(
        '5'.split(' '),
        { 'COMPONENT_NAME' : 'mycomp5' },
        service_json_loader=mock_service_json_loader
    )
    assert release.component_name == 'mycomp5', 'component name from environment variable'

def test_component_name_from_git():

    class MockShellRunner:
        def run(self, command, capture=False):
            if command == 'git config remote.origin.url':
                assert capture, 'git command is captured'
                return 0, 'https://github.com/mergermarket/mycomp6.git\n', ''
            else:
                raise Exception('unexpected command ' + command)
                
    release = Release(
        '6'.split(' '),
        {},
        shell_runner=MockShellRunner(),
        service_json_loader=mock_service_json_loader
    )
    assert release.component_name == 'mycomp6', 'name extracted from git remote'
    
    release = Release(
        '6a -c mycomp6a'.split(' '),
        {},
        shell_runner=MockShellRunner(),
        service_json_loader=mock_service_json_loader
    )
    assert release.component_name == 'mycomp6a', 'arg overrides git remote'

    release = Release(
        '6b'.split(' '),
        { 'COMPONENT_NAME': 'mycomp6b' },
        shell_runner=MockShellRunner(),
        service_json_loader=mock_service_json_loader
    )
    assert release.component_name == 'mycomp6b', 'environment variable overrides git remote'

class CapturingMockShellRunner:
    def __init__(self):
        self.commands = []

    def run(self, command, capture=False):
        self.commands.append([ command, capture ])

def test_build_slug():
    runner = CapturingMockShellRunner()

    release = Release(
        '6c'.split(' '),
        { 'COMPONENT_NAME': 'mycomp6c' },
        shell_runner=runner,
        service_json_loader=mock_service_json_loader,
    )
    release._build_slug()
    assert release.metadata['DOCKER_BUILD_DIR'] == 'target', 'slug built in target/'
    assert len(runner.commands) == 3, 'three commands ran'
    assert not runner.commands[0][1] and not runner.commands[1][1] and not runner.commands[2][1], 'all commands captured'
    assert runner.commands[0][0] == 'mkdir -p target', 'target folder created'
    assert search(r'tar.*slug.tgz', runner.commands[1][0]), 'slug built ' + runner.commands[1][0]
    assert runner.commands[2][0] == 'cp /infra/Dockerfile_slug target/Dockerfile', 'slug dockerfile copied'
    assert 'cp /infra/Dockerfile_slug target/Dockerfile', 'slug building dockerfile used'

