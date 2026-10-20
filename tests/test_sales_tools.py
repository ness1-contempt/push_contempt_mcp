import pytest
import requests

from push_contempt_mcp import sales_tools


class _RispostaFinta:
    def __init__(self, dati):
        self._dati = dati

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


def test_report_vendite_prodotti_chiama_endpoint_e_passa_il_periodo(monkeypatch):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append({"url": url, "params": params})
        return _RispostaFinta({"periodo": "3_mesi", "piu_venduti": [], "mai_venduti": []})

    monkeypatch.setattr(requests, "get", get_finto)
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")

    risultato = sales_tools.report_vendite_prodotti(periodo="3_mesi")

    assert risultato["periodo"] == "3_mesi"
    assert chiamate[0]["url"] == "https://localhost/wp-json/push-contempt/v1/vendite"
    assert chiamate[0]["params"] == {"periodo": "3_mesi"}


def test_report_vendite_prodotti_propaga_errori_http(monkeypatch):
    class RispostaErrore:
        def raise_for_status(self):
            raise requests.HTTPError("400")

    monkeypatch.setattr(requests, "get", lambda *a, **k: RispostaErrore())
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")

    with pytest.raises(requests.HTTPError):
        sales_tools.report_vendite_prodotti(periodo="2_settimane")
