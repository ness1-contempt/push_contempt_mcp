import subprocess

from push_contempt_mcp import cache_tools


def test_purga_cache_successo(monkeypatch):
    chiamate = []
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: chiamate.append(a) or type("R", (), {})()
    )

    risultato = cache_tools.purga_cache()

    assert risultato == {"cache_purgata": True}
    assert len(chiamate) == 3
    assert chiamate[0][0][3:5] == ["redis-cli", "FLUSHALL"]
    assert "rm -rf" in chiamate[1][0][-1]
    assert chiamate[2][0][:2] == ["docker", "restart"]


def test_purga_cache_fallimento_non_lancia_eccezione(monkeypatch):
    def fallisce(*a, **k):
        raise subprocess.CalledProcessError(1, "docker")

    monkeypatch.setattr(subprocess, "run", fallisce)

    risultato = cache_tools.purga_cache()

    assert risultato["cache_purgata"] is False
    assert "errore_cache" in risultato
