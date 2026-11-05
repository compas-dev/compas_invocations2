import pytest

from compas_invocations2 import grasshopper


@pytest.mark.parametrize(
    "system, machine, expected",
    [
        ("Windows", "AMD64", "win-x64/yak.exe"),
        ("Windows", "ARM64", "win-arm64/yak.exe"),
        ("Darwin", "arm64", "osx-universal/yak"),
        ("Darwin", "x86_64", "osx-universal/yak"),
        ("Linux", "x86_64", "linux-x64/yak"),
        ("Linux", "aarch64", "linux-arm64/yak"),
    ],
)
def test_get_yak_url(monkeypatch, system, machine, expected):
    monkeypatch.setattr(grasshopper.platform, "system", lambda: system)
    monkeypatch.setattr(grasshopper.platform, "machine", lambda: machine)

    url = grasshopper._get_yak_url()

    assert url == f"https://files.mcneel.com/yak/tools/{grasshopper.YAK_VERSION}/{expected}"
