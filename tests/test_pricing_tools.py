import pytest
import requests

from push_contempt_mcp import pricing_tools


class _RispostaFinta:
    def __init__(self, dati):
        self._dati = dati

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")


def test_calcola_aggiornamento_prezzi_chiama_endpoint_giusto(monkeypatch):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append({"url": url, "params": params})
        return _RispostaFinta({"categoria": "smartphone", "aggiornamenti": []})

    monkeypatch.setattr(requests, "get", get_finto)

    risultato = pricing_tools.calcola_aggiornamento_prezzi("smartphone", percentuale=10)

    assert risultato == {"categoria": "smartphone", "aggiornamenti": []}
    assert chiamate[0]["url"] == "https://localhost/wp-json/push-contempt/v1/prezzi/calcola"
    assert chiamate[0]["params"] == {"categoria": "smartphone", "percentuale": 10, "delta": None}


def test_applica_aggiornamento_prezzi_chiama_endpoint_giusto_in_post(monkeypatch):
    chiamate = []

    def post_finto(url, json, auth, verify, timeout):
        chiamate.append({"url": url, "json": json})
        return _RispostaFinta({"stato": "applicato", "aggiornati": []})

    monkeypatch.setattr(requests, "post", post_finto)

    aggiornamenti = [{"id": 40, "prezzo_regolare_nuovo": "694.98"}]
    risultato = pricing_tools.applica_aggiornamento_prezzi(aggiornamenti)

    assert risultato == {"stato": "applicato", "aggiornati": []}
    assert chiamate[0]["url"] == "https://localhost/wp-json/push-contempt/v1/prezzi/applica"
    assert chiamate[0]["json"] == {"aggiornamenti": aggiornamenti}


def test_calcola_aggiornamento_prezzi_propaga_errori_http(monkeypatch):
    class RispostaErrore:
        def raise_for_status(self):
            raise requests.HTTPError("400")

    monkeypatch.setattr(requests, "get", lambda *a, **k: RispostaErrore())

    with pytest.raises(requests.HTTPError):
        pricing_tools.calcola_aggiornamento_prezzi("smartphone")
