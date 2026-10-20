import requests

from push_contempt_mcp.seo_tools import lista_stato_seo_prodotti, valida_contenuto_seo


class _RispostaFinta:
    def __init__(self, dati):
        self._dati = dati

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


def test_lista_stato_seo_prodotti_chiama_endpoint_giusto(monkeypatch):
    chiamate = []

    def get_finto(url, auth, verify, timeout):
        chiamate.append(url)
        return _RispostaFinta([{"id": 40, "titolo_seo": "X"}])

    monkeypatch.setattr(requests, "get", get_finto)
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")

    risultato = lista_stato_seo_prodotti()

    assert risultato == [{"id": 40, "titolo_seo": "X"}]
    assert chiamate[0] == "https://localhost/wp-json/push-contempt/v1/seo/stato"


def test_valida_contenuto_seo_tutto_ok():
    descrizione = (
        "<p>Scopri il Prodotto X, il migliore della categoria.</p>"
        "<p>Il Prodotto X è perfetto per ogni occasione.</p>"
        "<p>Guarda anche <a href='/prodotto/altro/'>Altro prodotto</a>.</p>"
        "<h3>Prodotto X: scheda tecnica</h3>"
    )
    assert valida_contenuto_seo(descrizione, "Prodotto X") == []


def test_valida_contenuto_seo_segnala_tutti_i_problemi():
    descrizione = "<p>Testo generico senza nulla di rilevante.</p>"
    avvisi = valida_contenuto_seo(descrizione, "Prodotto X")
    assert len(avvisi) == 3
    assert any("Frase chiave" in a for a in avvisi)
    assert any("sottotitolo" in a for a in avvisi)
    assert any("link interno" in a for a in avvisi)
