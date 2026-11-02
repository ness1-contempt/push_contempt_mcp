import pytest
import requests

from push_contempt_mcp.seo_varianti_tools import (
    aggiorna_seo_varianti,
    leggi_seo_varianti,
    valida_testi_variabile,
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


# --- lettura ---------------------------------------------------------------------


def test_leggi_seo_varianti_chiama_il_plugin_e_restituisce_i_dati(monkeypatch):
    dati = {"id": 142, "varianti": [], "problemi": [], "conteggio": {"errori": 0}}
    chiamate = _finti(monkeypatch, get=_RispostaFinta(dati))

    assert leggi_seo_varianti(142) == dati
    assert chiamate == [("GET", f"{BASE}/seo/varianti", {"id": 142})]


@pytest.mark.parametrize("stato", [400, 404])
def test_leggi_seo_varianti_riporta_il_rifiuto_del_plugin(monkeypatch, stato):
    _finti(monkeypatch, get=_RispostaFinta({"message": "non variabile"}, stato))
    assert leggi_seo_varianti(5) == {"errore": "non variabile"}


# --- scrittura -------------------------------------------------------------------


def test_aggiorna_seo_varianti_manda_id_varianti_e_anteprima(monkeypatch):
    risposta = {"id": 142, "solo_anteprima": False, "varianti": [{"id": 143}]}
    chiamate = _finti(monkeypatch, post=_RispostaFinta(risposta))

    risultato = aggiorna_seo_varianti(142, [{"id": 143, "sku": "FEL-NM"}])

    assert risultato["stato"] == "aggiornato"
    assert risultato["varianti"] == [{"id": 143}]
    assert chiamate == [
        (
            "POST",
            f"{BASE}/seo/varianti",
            {"id": 142, "varianti": [{"id": 143, "sku": "FEL-NM"}], "solo_anteprima": False},
        )
    ]


def test_aggiorna_seo_varianti_in_anteprima_lo_dice(monkeypatch):
    _finti(monkeypatch, post=_RispostaFinta({"id": 1, "solo_anteprima": True, "varianti": []}))
    assert (
        aggiorna_seo_varianti(1, [{"id": 2, "descrizione": "x"}], solo_anteprima=True)["stato"]
        == "anteprima"
    )


@pytest.mark.parametrize("stato", [400, 404, 409])
def test_aggiorna_seo_varianti_riporta_i_rifiuti_senza_alzare_eccezioni(monkeypatch, stato):
    _finti(monkeypatch, post=_RispostaFinta({"message": "SKU gia' in uso"}, stato))
    assert aggiorna_seo_varianti(1, [{"id": 2, "sku": "A"}]) == {"errore": "SKU gia' in uso"}


@pytest.mark.parametrize(
    "varianti",
    [
        [{"descrizione": "senza id"}],
        [{"id": "143", "sku": "A"}],
        [{"id": 143}],
        [{"id": 143, "sku": 123}],
        [{"id": 143, "descrizione": None}],
    ],
)
def test_aggiorna_seo_varianti_malformato_non_parte(monkeypatch, varianti):
    chiamate = _finti(monkeypatch, post=_RispostaFinta({}))
    assert "errore" in aggiorna_seo_varianti(1, varianti)
    assert chiamate == []


# --- controllo dei testi ---------------------------------------------------------

ATTRIBUTI = [
    {"nome": "Colore", "valori": ["Nero", "Grigio"]},
    {"nome": "Taglia", "valori": ["M", "L"]},
]


def test_testi_a_posto_non_danno_avvisi():
    assert (
        valida_testi_variabile(
            "<p>Felpa in cotone, nero o grigio, taglie M e L.</p>",
            "Felpa in cotone",
            "felpa cotone",
            ATTRIBUTI,
        )
        == []
    )


def test_valori_assenti_dalla_descrizione_sono_elencati_e_l_html_non_conta():
    avvisi = valida_testi_variabile(
        '<p class="grigio">Felpa in cotone, taglia M.</p>', "Felpa", "felpa", ATTRIBUTI
    )
    assert len(avvisi) == 1
    for atteso in ("Colore: Nero", "Colore: Grigio", "Taglia: L"):
        assert atteso in avvisi[0]
    assert "Taglia: M" not in avvisi[0]


def test_una_taglia_non_e_trovata_dentro_un_altra_parola():
    # "L" e "M" non sono in "Felpa" ne' in "Maglia": serve la parola intera.
    avvisi = valida_testi_variabile("Felpa Maglia nero grigio", "x", "y", ATTRIBUTI)
    assert "Taglia: L" in avvisi[0] and "Taglia: M" in avvisi[0]


def test_titolo_e_parola_chiave_che_citano_una_sola_variante():
    avvisi = valida_testi_variabile(
        "Felpa nero grigio M L", "Felpa Nero", "felpa grigio", ATTRIBUTI
    )
    assert any("titolo seo cita solo una variante (nero)" in a.lower() for a in avvisi)
    assert any("parola chiave focus cita solo una variante (grigio)" in a.lower() for a in avvisi)


def test_un_attributo_con_un_solo_valore_non_fa_scattare_il_titolo():
    avvisi = valida_testi_variabile(
        "Felpa nero", "Felpa Nero", "felpa", [{"nome": "Colore", "valori": ["Nero"]}]
    )
    assert avvisi == []
