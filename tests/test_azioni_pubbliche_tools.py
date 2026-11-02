import pytest
import requests

from push_contempt_mcp.azioni_pubbliche_tools import (
    crea_categoria_prodotti,
    lista_categorie_prodotti,
    pubblica_prodotti,
    sposta_categoria_prodotti,
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

    def get_finto(url, auth, verify, timeout):
        chiamate.append(("GET", url))
        return get

    def post_finto(url, json, auth, verify, timeout):
        chiamate.append(("POST", url, json))
        return post

    monkeypatch.setattr(requests, "get", get_finto)
    monkeypatch.setattr(requests, "post", post_finto)
    return chiamate


# --- categorie -------------------------------------------------------------------


def test_lista_categorie_chiama_il_plugin(monkeypatch):
    righe = [{"id": 5, "percorso": "Indumenti > Magliette"}]
    chiamate = _finti(monkeypatch, get=_RispostaFinta(righe))
    assert lista_categorie_prodotti() == righe
    assert chiamate == [("GET", f"{BASE}/categorie")]


def test_sposta_in_anteprima_manda_solo_anteprima_e_dice_cosa_fare_dopo(monkeypatch):
    anteprima = {"solo_anteprima": True, "codice_conferma": "abc", "percorso_dopo": "A > B"}
    chiamate = _finti(monkeypatch, post=_RispostaFinta(dict(anteprima)))

    risultato = sposta_categoria_prodotti(4, 1)

    assert risultato["codice_conferma"] == "abc"
    assert "esplicitamente" in risultato["prossimo_passo"]
    assert chiamate == [
        (
            "POST",
            f"{BASE}/categorie/sposta",
            {"id": 4, "nuova_madre": 1, "solo_anteprima": True, "codice_conferma": ""},
        )
    ]


def test_sposta_davvero_senza_codice_non_chiama_nemmeno_il_plugin(monkeypatch):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({}))
    risultato = sposta_categoria_prodotti(4, 1, anteprima=False)
    assert "codice_conferma" in risultato["errore"]
    assert chiamate == []


def test_sposta_davvero_manda_il_codice_e_non_aggiunge_il_prossimo_passo(monkeypatch):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({"spostata": True}))

    risultato = sposta_categoria_prodotti(4, 0, anteprima=False, codice_conferma="abc")

    assert risultato == {"spostata": True}
    assert chiamate[0][2] == {
        "id": 4,
        "nuova_madre": 0,
        "solo_anteprima": False,
        "codice_conferma": "abc",
    }


@pytest.mark.parametrize("stato", [400, 404, 409, 500])
def test_sposta_riporta_i_rifiuti_del_plugin(monkeypatch, stato):
    _finti(monkeypatch, post=_RispostaFinta({"message": "non si puo'"}, stato))
    assert sposta_categoria_prodotti(4, 1) == {"errore": "non si puo'"}


# --- pubblicazione ---------------------------------------------------------------


def test_pubblica_in_anteprima_chiede_la_conferma_all_utente(monkeypatch):
    dati = {"solo_anteprima": True, "da_pubblicare": [{"id": 7}], "codice_conferma": "xyz"}
    chiamate = _finti(monkeypatch, post=_RispostaFinta(dict(dati)))

    risultato = pubblica_prodotti([7])

    assert risultato["codice_conferma"] == "xyz"
    assert "esplicitamente" in risultato["prossimo_passo"]
    assert chiamate == [
        (
            "POST",
            f"{BASE}/prodotti/pubblica",
            {"ids": [7], "solo_anteprima": True, "codice_conferma": ""},
        )
    ]


def test_pubblica_in_anteprima_senza_nulla_di_pubblicabile_non_chiede_conferma(monkeypatch):
    _finti(
        monkeypatch,
        post=_RispostaFinta(
            {"da_pubblicare": [], "non_pubblicabili": [{"id": 7}], "codice_conferma": None}
        ),
    )
    risultato = pubblica_prodotti([7])
    assert "pubblicabile" in risultato["prossimo_passo"]
    assert "anteprima=False" not in risultato["prossimo_passo"]


def test_pubblica_davvero_senza_codice_non_chiama_il_plugin(monkeypatch):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({}))
    assert "codice_conferma" in pubblica_prodotti([7], anteprima=False)["errore"]
    assert (
        "codice_conferma" in pubblica_prodotti([7], anteprima=False, codice_conferma="")["errore"]
    )
    assert chiamate == []


def test_pubblica_davvero_manda_il_codice(monkeypatch):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({"pubblicati": [{"id": 7}], "falliti": []}))

    risultato = pubblica_prodotti([7, 8], anteprima=False, codice_conferma="xyz")

    assert risultato["pubblicati"] == [{"id": 7}]
    assert "prossimo_passo" not in risultato
    assert chiamate[0][2] == {"ids": [7, 8], "solo_anteprima": False, "codice_conferma": "xyz"}


@pytest.mark.parametrize("ids", [[], ["7"], [7, "8"]])
def test_pubblica_rifiuta_elenchi_malformati(monkeypatch, ids):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({}))
    assert "errore" in pubblica_prodotti(ids)
    assert chiamate == []


@pytest.mark.parametrize("stato", [400, 409])
def test_pubblica_riporta_i_rifiuti_del_plugin(monkeypatch, stato):
    _finti(monkeypatch, post=_RispostaFinta({"message": "codice non valido"}, stato))
    assert pubblica_prodotti([7]) == {"errore": "codice non valido"}


# --- creare una categoria --------------------------------------------------------


def test_crea_categoria_in_anteprima_non_crea_e_chiede_l_ok(monkeypatch):
    chiamate = _finti(
        monkeypatch,
        post=_RispostaFinta({"solo_anteprima": True, "percorso_dopo": "Indumenti"}),
    )

    risultato = crea_categoria_prodotti("Indumenti")

    assert risultato["percorso_dopo"] == "Indumenti"
    assert "anteprima=False" in risultato["prossimo_passo"]
    assert chiamate == [
        (
            "POST",
            f"{BASE}/categorie",
            {"nome": "Indumenti", "madre": 0, "solo_anteprima": True},
        )
    ]


def test_crea_categoria_davvero_non_chiede_il_codice(monkeypatch):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({"creata": True, "id": 30}))

    risultato = crea_categoria_prodotti("Magliette", madre_id=7, anteprima=False)

    assert risultato == {"creata": True, "id": 30}
    assert chiamate[0][2] == {"nome": "Magliette", "madre": 7, "solo_anteprima": False}


@pytest.mark.parametrize("nome", ["", "   ", None, 5])
def test_crea_categoria_con_nome_non_valido_non_chiama_il_plugin(monkeypatch, nome):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({}))
    assert "errore" in crea_categoria_prodotti(nome)
    assert chiamate == []


@pytest.mark.parametrize("stato", [400, 404, 409, 500])
def test_crea_categoria_riporta_i_rifiuti_del_plugin(monkeypatch, stato):
    _finti(monkeypatch, post=_RispostaFinta({"message": "esiste gia'"}, stato))
    assert crea_categoria_prodotti("X") == {"errore": "esiste gia'"}
