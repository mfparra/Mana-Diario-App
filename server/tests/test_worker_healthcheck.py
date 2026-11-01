import time

from worker import healthcheck


def test_heartbeat(tmp_path, monkeypatch):
    hb = tmp_path / "hb"
    monkeypatch.setattr(healthcheck, "HEARTBEAT", hb)
    assert not healthcheck.is_healthy()
    hb.write_text(str(time.time()))
    assert healthcheck.is_healthy()
    assert not healthcheck.is_healthy(now=time.time() + 1000)
