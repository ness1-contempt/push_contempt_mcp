import pytest
import requests

from push_contempt_mcp import browser_tools


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


def test_separatore_decimale_woocommerce_chiama_endpoint_giusto(monkeypatch):
    chiamate = []

    def get_finto(url, auth, verify, timeout):
        chiamate.append(url)
        return _RispostaFinta({"separatore_decimale": ","})

    monkeypatch.setattr(requests, "get", get_finto)

    assert browser_tools._separatore_decimale_woocommerce() == ","
    assert chiamate[0] == "https://localhost/wp-json/push-contempt/v1/prezzi/impostazioni"


def test_separatore_decimale_woocommerce_propaga_errori_http(monkeypatch):
    class RispostaErrore:
        def raise_for_status(self):
            raise requests.HTTPError("500")

    monkeypatch.setattr(requests, "get", lambda *a, **k: RispostaErrore())

    with pytest.raises(requests.HTTPError):
        browser_tools._separatore_decimale_woocommerce()
