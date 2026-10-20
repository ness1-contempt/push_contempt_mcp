import pytest
import requests

from push_contempt_mcp import inventory_tools


class _RispostaFinta:
    def __init__(self, dati):
        self._dati = dati

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


def test_prodotti_sotto_scorta_chiama_endpoint_e_passa_la_soglia(monkeypatch):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append({"url": url, "params": params})
        return _RispostaFinta([{"id": 58, "esaurito": True}])

    monkeypatch.setattr(requests, "get", get_finto)
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")

    risultato = inventory_tools.prodotti_sotto_scorta(soglia=3)

    assert risultato == [{"id": 58, "esaurito": True}]
    assert chiamate[0]["url"] == "https://localhost/wp-json/push-contempt/v1/scorte"
    assert chiamate[0]["params"] == {"soglia": 3}


def test_prodotti_sotto_scorta_propaga_errori_http(monkeypatch):
    class RispostaErrore:
        def raise_for_status(self):
            raise requests.HTTPError("500")

    monkeypatch.setattr(
        requests, "get", lambda *a, **k: RispostaErrore()
    )
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")

    with pytest.raises(requests.HTTPError):
        inventory_tools.prodotti_sotto_scorta()
