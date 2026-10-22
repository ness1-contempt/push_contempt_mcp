import pytest
import requests

from push_contempt_mcp import order_tools


class _Risposta:
    def __init__(self, dati, status_code=200):
        self._dati = dati
        self.status_code = status_code
        self.text = str(dati)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._dati


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")


def test_lista_ordini_passa_i_filtri_all_endpoint_giusto(monkeypatch):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append({"url": url, "params": params, "auth": auth})
        return _Risposta({"totale_trovati": 1, "restituiti": 1, "ordini": [{"id": 7}]})

    monkeypatch.setattr(requests, "get", get_finto)

    risultato = order_tools.lista_ordini(
        stato="processing,on-hold", piu_vecchi_di_ore=24, limite=10
    )

    assert risultato["ordini"] == [{"id": 7}]
    assert chiamate[0]["url"] == "https://localhost/wp-json/push-contempt/v1/ordini"
    assert chiamate[0]["auth"] == ("Andrea", "segreto")
    assert chiamate[0]["params"]["stato"] == "processing,on-hold"
    assert chiamate[0]["params"]["piu_vecchi_di_ore"] == 24
    assert chiamate[0]["params"]["limite"] == 10


def test_dettaglio_ordine_chiama_la_rotta_con_id(monkeypatch):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append(url)
        return _Risposta({"id": 42})

    monkeypatch.setattr(requests, "get", get_finto)

    assert order_tools.dettaglio_ordine(42) == {"id": 42}
    assert chiamate[0] == "https://localhost/wp-json/push-contempt/v1/ordini/42"


def test_errore_400_propaga_il_messaggio_del_plugin(monkeypatch):
    messaggio = 'Stato ordine sconosciuto "evaso". Validi: pending, processing.'
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _Risposta({"message": messaggio}, status_code=400)
    )

    with pytest.raises(ValueError, match="Validi: pending, processing"):
        order_tools.lista_ordini(stato="evaso")


def test_errore_404_ordine_inesistente(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _Risposta({"message": "Ordine non trovato."}, 404)
    )

    with pytest.raises(ValueError, match="Ordine non trovato"):
        order_tools.dettaglio_ordine(999)


def test_errore_server_resta_http_error(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Risposta({}, status_code=500))

    with pytest.raises(requests.HTTPError):
        order_tools.lista_ordini()
