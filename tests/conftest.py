"""Test isolation: never touch the developer's real data dir or system."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path_factory, monkeypatch):
    d = tmp_path_factory.mktemp("syscare_data")
    monkeypatch.setenv("SYSCARE_DATA_DIR", str(d))
    yield d
