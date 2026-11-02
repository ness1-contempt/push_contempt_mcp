import pytest
import requests

from push_contempt_mcp.alt_tools import (
    aggiorna_alt_immagini_prodotto,
    leggi_alt_immagini_prodotto,
)
from push_contempt_mcp.descrizione_tools import (
    aggiorna_descrizione_prodotto,
    leggi_descrizione_prodotto,
    ripristina_descrizione_prodotti,
)

BASE = "https://localhost/wp-json/push-contempt/v1"


class _RispostaFinta:
    def __init__(self, dati, status_code=200):
        self._dati = dati
        self.status_code = status_code
        self.text = str(dati)

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "Andrea")
    monkeypatch.setenv("WP_APP_PASSWORD", "segreto")


def _finti(monkeypatch, get=None, post=None):
    chiamate = []

    def get_finto(url, params, auth, verify, timeout):
        chiamate.append(("GET", url, params))
        return get

    def post_finto(url, json, auth, verify, timeout):
        chiamate.append(("POST", url, json))
        return post

    monkeypatch.setattr(requests, "get", get_finto)
    monkeypatch.setattr(requests, "post", post_finto)
    return chiamate


# --- descrizione ---------------------------------------------------------------


def test_leggi_descrizione_prodotto_e_404(monkeypatch):
    chiamate = _finti(monkeypatch, get=_RispostaFinta({}, 404))

    assert "errore" in leggi_descrizione_prodotto(9)
    assert chiamate == [("GET", f"{BASE}/descrizione/prodotto", {"id": 9})]


def test_aggiorna_descrizione_restituisce_prima_e_dopo(monkeypatch):
    prima = {
        "id": 5,
        "descrizione": "<p>Vecchia</p>",
        "descrizione_breve": "Breve",
        "versioni": None,
    }
    dopo = {"descrizione": "<p>Nuova</p>", "descrizione_breve": "Breve"}
    chiamate = _finti(monkeypatch, get=_RispostaFinta(prima), post=_RispostaFinta(dopo))

    risultato = aggiorna_descrizione_prodotto(5, "<p>Nuova</p>")

    assert risultato == {
        "stato": "aggiornato",
        "prodotto_id": 5,
        "prima": {"descrizione": "<p>Vecchia</p>", "descrizione_breve": "Breve"},
        "dopo": dopo,
    }
    # senza breve e senza origine non si inviano: la breve resta com'e'
    assert chiamate[1] == (
        "POST",
        f"{BASE}/descrizione/prodotto",
        {"id": 5, "descrizione": "<p>Nuova</p>"},
    )


def test_aggiorna_descrizione_invia_breve_vuota_e_origine(monkeypatch):
    prima = {"descrizione": "A", "descrizione_breve": "B"}
    chiamate = _finti(monkeypatch, get=_RispostaFinta(prima), post=_RispostaFinta({}))

    aggiorna_descrizione_prodotto(5, "C", "", "concorrente x.it")

    assert chiamate[1][2] == {
        "id": 5,
        "descrizione": "C",
        "descrizione_breve": "",
        "origine": "concorrente x.it",
    }


def test_aggiorna_descrizione_su_prodotto_inesistente_non_scrive(monkeypatch):
    chiamate = _finti(monkeypatch, get=_RispostaFinta({}, 404))

    assert "errore" in aggiorna_descrizione_prodotto(9, "x")
    assert [c[0] for c in chiamate] == ["GET"]


def test_ripristina_descrizione_chiama_il_plugin_e_rifiuta_versioni_sconosciute(monkeypatch):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({"5": "ripristinato"}))

    assert ripristina_descrizione_prodotti([5]) == {"5": "ripristinato"}
    assert chiamate == [
        ("POST", f"{BASE}/descrizione/ripristina", {"ids": [5], "versione": "base"})
    ]
    assert "errore" in ripristina_descrizione_prodotti([5], "attuale")
    assert len(chiamate) == 1


# --- ALT -----------------------------------------------------------------------


def test_leggi_alt_immagini_prodotto(monkeypatch):
    dati = {"id": 7, "immagini": [{"allegato_id": 8, "alt": ""}]}
    chiamate = _finti(monkeypatch, get=_RispostaFinta(dati))

    assert leggi_alt_immagini_prodotto(7) == dati
    assert chiamate == [("GET", f"{BASE}/alt/prodotto", {"id": 7})]


def test_aggiorna_alt_immagini_prodotto(monkeypatch):
    esito = {"id": 7, "immagini": [{"allegato_id": 8, "prima": "", "dopo": "Sedia"}]}
    chiamate = _finti(monkeypatch, post=_RispostaFinta(esito))

    risultato = aggiorna_alt_immagini_prodotto(7, [{"allegato_id": 8, "alt": "Sedia"}])

    assert risultato == {"stato": "aggiornato", **esito}
    assert chiamate == [
        (
            "POST",
            f"{BASE}/alt/prodotto",
            {"id": 7, "immagini": [{"allegato_id": 8, "alt": "Sedia"}]},
        )
    ]


def test_aggiorna_alt_riporta_il_rifiuto_del_plugin(monkeypatch):
    _finti(
        monkeypatch,
        post=_RispostaFinta({"message": "Le immagini 99 non appartengono al prodotto 7"}, 400),
    )

    assert "99" in aggiorna_alt_immagini_prodotto(7, [{"allegato_id": 99, "alt": "x"}])["errore"]


def test_aggiorna_alt_con_elementi_malformati_non_parte(monkeypatch):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({}))

    assert "errore" in aggiorna_alt_immagini_prodotto(7, [{"alt": "senza id"}])
    assert "errore" in aggiorna_alt_immagini_prodotto(7, [{"allegato_id": "8", "alt": "x"}])
    assert chiamate == []


# --- link ----------------------------------------------------------------------


def test_analizza_link_prodotto_chiama_il_plugin(monkeypatch):
    from push_contempt_mcp.link_tools import analizza_link_prodotto

    dati = {"id": 7, "interni": [], "esterni": [], "ha_link_in_uscita": False}
    chiamate = _finti(monkeypatch, get=_RispostaFinta(dati))

    assert analizza_link_prodotto(7) == dati
    assert chiamate == [("GET", f"{BASE}/link/prodotto", {"id": 7})]


def test_analizza_link_prodotto_inesistente_da_errore(monkeypatch):
    from push_contempt_mcp.link_tools import analizza_link_prodotto

    _finti(monkeypatch, get=_RispostaFinta({"message": "Nessun prodotto con id 9"}, 404))

    assert analizza_link_prodotto(9) == {"errore": "Nessun prodotto con id 9"}


def test_analizza_link_prodotti_manda_i_filtri_come_testo(monkeypatch):
    from push_contempt_mcp.link_tools import analizza_link_prodotti

    dati = {"analizzati": 20, "senza_link_in_uscita": 18, "senza_link_interni": 3, "prodotti": []}
    chiamate = _finti(monkeypatch, get=_RispostaFinta(dati))

    assert analizza_link_prodotti() == dati
    analizza_link_prodotti("any", True)

    assert chiamate == [
        (
            "GET",
            f"{BASE}/link/prodotti",
            {"stato": "publish", "solo_senza_link_in_uscita": "false"},
        ),
        ("GET", f"{BASE}/link/prodotti", {"stato": "any", "solo_senza_link_in_uscita": "true"}),
    ]


def test_analizza_link_prodotti_rifiuta_uno_stato_sconosciuto(monkeypatch):
    from push_contempt_mcp.link_tools import analizza_link_prodotti

    chiamate = _finti(monkeypatch, get=_RispostaFinta({}))

    assert "errore" in analizza_link_prodotti("trash")
    assert chiamate == []
