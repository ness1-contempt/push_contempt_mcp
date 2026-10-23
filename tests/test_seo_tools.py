import pytest
import requests

from push_contempt_mcp.seo_tools import (
    aggiorna_seo_prodotto,
    leggi_seo_prodotti_selezionati,
    leggi_seo_prodotto,
    lista_stato_seo_prodotti,
    ripristina_seo_prodotti,
    valida_contenuto_seo,
)


class _RispostaFinta:
    def __init__(self, dati, status_code=200):
        self._dati = dati
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")


def test_lista_stato_seo_prodotti_chiama_endpoint_giusto(monkeypatch):
    chiamate = []

    def get_finto(url, auth, verify, timeout):
        chiamate.append(url)
        return _RispostaFinta([{"id": 40, "titolo_seo": "X"}])

    monkeypatch.setattr(requests, "get", get_finto)

    risultato = lista_stato_seo_prodotti()

    assert risultato == [{"id": 40, "titolo_seo": "X"}]
    assert chiamate[0] == "https://localhost/wp-json/push-contempt/v1/seo/stato"


def test_leggi_seo_prodotto_chiama_endpoint_giusto(monkeypatch):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append({"url": url, "params": params})
        return _RispostaFinta({"id": 40, "titolo": "Sedia", "titolo_seo": "X"})

    monkeypatch.setattr(requests, "get", get_finto)

    risultato = leggi_seo_prodotto(40)

    assert risultato == {"id": 40, "titolo": "Sedia", "titolo_seo": "X"}
    assert chiamate[0]["url"] == "https://localhost/wp-json/push-contempt/v1/seo/prodotto"
    assert chiamate[0]["params"] == {"id": 40}


def test_leggi_seo_prodotto_restituisce_errore_su_404(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _RispostaFinta({"code": "non_trovato"}, status_code=404)
    )

    risultato = leggi_seo_prodotto(999)

    assert risultato == {"errore": "Nessun prodotto con id 999"}


def test_leggi_seo_prodotti_selezionati_chiama_una_volta_per_id(monkeypatch):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append(params["id"])
        return _RispostaFinta({"id": params["id"]})

    monkeypatch.setattr(requests, "get", get_finto)

    risultato = leggi_seo_prodotti_selezionati([40, 41])

    assert chiamate == [40, 41]
    assert risultato == [{"id": 40}, {"id": 41}]


def test_aggiorna_seo_prodotto_scrive_e_restituisce_prima_dopo(monkeypatch):
    def get_finto(url, params, auth, verify, timeout):
        return _RispostaFinta(
            {
                "id": 40,
                "titolo_seo": "Vecchio titolo",
                "meta_description": "Vecchia descrizione",
                "parola_chiave_focus": "vecchia",
            }
        )

    chiamate_post = []

    def post_finto(url, json, auth, verify, timeout):
        chiamate_post.append({"url": url, "json": json})
        return _RispostaFinta(
            {
                "titolo_seo": json["titolo_seo"],
                "meta_description": json["meta_description"],
                "parola_chiave_focus": json["parola_chiave_focus"],
            }
        )

    monkeypatch.setattr(requests, "get", get_finto)
    monkeypatch.setattr(requests, "post", post_finto)

    risultato = aggiorna_seo_prodotto(40, "Nuovo titolo", "Nuova descrizione", "nuova")

    assert chiamate_post[0]["url"] == "https://localhost/wp-json/push-contempt/v1/seo/prodotto"
    assert chiamate_post[0]["json"] == {
        "id": 40,
        "titolo_seo": "Nuovo titolo",
        "meta_description": "Nuova descrizione",
        "parola_chiave_focus": "nuova",
    }
    assert risultato == {
        "stato": "aggiornato",
        "prodotto_id": 40,
        "prima": {
            "titolo_seo": "Vecchio titolo",
            "meta_description": "Vecchia descrizione",
            "parola_chiave_focus": "vecchia",
        },
        "dopo": {
            "titolo_seo": "Nuovo titolo",
            "meta_description": "Nuova descrizione",
            "parola_chiave_focus": "nuova",
        },
    }


def test_aggiorna_seo_prodotto_propaga_errore_se_prodotto_non_trovato(monkeypatch):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _RispostaFinta({}, status_code=404)
    )

    risultato = aggiorna_seo_prodotto(999, "X", "Y", "Z")

    assert risultato == {"errore": "Nessun prodotto con id 999"}


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


def test_aggiorna_seo_prodotto_passa_l_origine_solo_se_c_e(monkeypatch):
    chiamate_post = []

    def post_finto(url, json, auth, verify, timeout):
        chiamate_post.append(json)
        return _RispostaFinta({})

    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _RispostaFinta(
            {"titolo_seo": None, "meta_description": None, "parola_chiave_focus": None}
        ),
    )
    monkeypatch.setattr(requests, "post", post_finto)

    aggiorna_seo_prodotto(40, "T", "M", "k", origine="concorrente x.it")
    aggiorna_seo_prodotto(40, "T", "M", "k")

    assert chiamate_post[0]["origine"] == "concorrente x.it"
    assert "origine" not in chiamate_post[1]


def test_ripristina_seo_prodotti_chiama_il_plugin_e_restituisce_gli_esiti(monkeypatch):
    chiamate = []

    def post_finto(url, json, auth, verify, timeout):
        chiamate.append({"url": url, "json": json})
        return _RispostaFinta({"40": "ripristinato", "41": "nessuno_snapshot"})

    monkeypatch.setattr(requests, "post", post_finto)

    risultato = ripristina_seo_prodotti([40, 41])

    url = "https://localhost/wp-json/push-contempt/v1/seo/ripristina"
    assert chiamate == [{"url": url, "json": {"ids": [40, 41]}}]
    assert risultato == {"40": "ripristinato", "41": "nessuno_snapshot"}
