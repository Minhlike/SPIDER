import pytest
from spider.models.enums import ObservableType
from spider.models.observable import NormalizedObservable
from spider.providers.fake.provider_a import FakeProviderA

def test_command_injection_sanitization():
    # Testing that malicious target inputs are sanitized and never passed via shell=True
    malicious_inputs = [
        "example.com; calc.exe",
        "example.com && whoami",
        "example.com | dir",
        "$(calc.exe).example.com",
        "`whoami`.example.com"
    ]
    provider = FakeProviderA()

    for mal in malicious_inputs:
        obs = NormalizedObservable(type=ObservableType.DOMAIN, value=mal)
        cmd = provider.build_command(obs)
        # Verify cmd is a structured list (argv array)
        assert isinstance(cmd, list)
        assert cmd[0] == "fake_a.exe"
        assert cmd[1] == "-d"
        # Verify argument is passed as single raw literal token in argv, never string-concatenated shell command
        assert cmd[2] == obs.canonical_value
