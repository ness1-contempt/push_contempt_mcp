"""Cartelle prodotti = albero delle categorie WooCommerce: scansione a qualsiasi profondita',
casi dubbi segnalati, confronto con le categorie del sito, percorso passato alla creazione."""

from pathlib import Path

import pytest
import requests

from push_contempt_mcp import product_sync, product_tools


@pytest.fixture(autouse=True)
def _nessun_prodotto_esistente(monkeypatch):
    monkeypatch.setattr(product_sync, "_nomi_prodotti_esistenti", lambda: set())


def _prodotto(radice: Path, *percorso: str, foto: bool = True, testo: str | None = "prezzo: 10"):
    cartella = radice.joinpath(*percorso)
    cartella.mkdir(parents=True, exist_ok=True)
    if foto:
        (cartella / "foto.jpg").write_bytes(b"x")
    if testo is not None:
        (cartella / "scheda.txt").write_text(testo, encoding="utf-8")
    return cartella


def _scansiona(radice: Path) -> dict:
    return product_sync.scansiona_cartella_prodotti(str(radice))


def test_un_prodotto_a_due_livelli_come_prima(tmp_path):
    _prodotto(tmp_path, "Smartphone", "Nubia Z80")

    nuovo = _scansiona(tmp_path)["nuovi"][0]

    assert nuovo["nome"] == "Nubia Z80"
    assert nuovo["categoria"] == "Smartphone"
    assert nuovo["percorso_categoria"] == ["Smartphone"]


def test_le_cartelle_annidate_sono_il_percorso_delle_categorie(tmp_path):
    _prodotto(tmp_path, "Indumenti", "Magliette", "Maglietta rossa")
    _prodotto(tmp_path, "Indumenti", "Magliette", "Sportive", "Maglietta corsa")
    _prodotto(tmp_path, "Indumenti", "Pantaloni", "Jeans")

    nuovi = {p["nome"]: p for p in _scansiona(tmp_path)["nuovi"]}

    assert nuovi["Maglietta rossa"]["percorso_categoria"] == ["Indumenti", "Magliette"]
    assert nuovi["Maglietta rossa"]["categoria"] == "Magliette"
    assert nuovi["Maglietta corsa"]["percorso_categoria"] == ["Indumenti", "Magliette", "Sportive"]
    assert nuovi["Jeans"]["percorso_categoria"] == ["Indumenti", "Pantaloni"]


def test_un_prodotto_con_una_sottocartella_senza_prodotti_resta_un_prodotto(tmp_path):
    cartella = _prodotto(tmp_path, "Smartphone", "Nubia")
    (cartella / "originali").mkdir()  # una cartella di servizio, senza foto ne' testi

    nuovi = _scansiona(tmp_path)["nuovi"]

    assert [p["nome"] for p in nuovi] == ["Nubia"]


def test_prodotto_fuori_da_una_categoria_va_da_controllare(tmp_path):
    _prodotto(tmp_path, "Prodotto orfano")
    _prodotto(tmp_path, "Smartphone", "Nubia")

    risultato = _scansiona(tmp_path)

    assert [p["nome"] for p in risultato["nuovi"]] == ["Nubia"]
    assert len(risultato["da_controllare"]) == 1
    assert "fuori da una cartella di categoria" in risultato["da_controllare"][0]["motivo"]


def test_cartella_con_file_e_sottocartelle_di_prodotti_va_da_controllare(tmp_path):
    ambigua = _prodotto(tmp_path, "Indumenti", "Magliette")  # ha foto e testo...
    _prodotto(ambigua, "Maglietta rossa")  # ...e anche un prodotto sotto
    _prodotto(tmp_path, "Smartphone", "Nubia")

    risultato = _scansiona(tmp_path)

    assert [p["nome"] for p in risultato["nuovi"]] == ["Nubia"]
    assert "prodotto o una categoria" in risultato["da_controllare"][0]["motivo"]


def test_cartella_vuota_a_fondo_albero_e_un_prodotto_con_avviso_e_una_categoria_vuota_si_ignora(
    tmp_path,
):
    (tmp_path / "Categoria vuota").mkdir()
    (tmp_path / "Tavoli" / "Tavolo vuoto").mkdir(parents=True)

    risultato = _scansiona(tmp_path)

    assert [p["nome"] for p in risultato["nuovi"]] == ["Tavolo vuoto"]
    assert "Mancano foto" in risultato["nuovi"][0]["avviso"]


def test_i_prodotti_gia_presenti_si_riconoscono_a_qualsiasi_profondita(tmp_path, monkeypatch):
    _prodotto(tmp_path, "Indumenti", "Magliette", "Maglietta rossa")
    monkeypatch.setattr(
        product_sync,
        "_nomi_prodotti_esistenti",
        lambda: {product_sync._normalizza_nome("Maglietta Rossa")},
    )

    risultato = _scansiona(tmp_path)

    assert risultato["gia_presenti"] == ["Maglietta rossa"]
    assert risultato["nuovi"] == []


def test_le_categorie_da_creare_si_elencano_una_volta(tmp_path):
    _prodotto(tmp_path, "Indumenti", "Magliette", "A")
    _prodotto(tmp_path, "Indumenti", "Magliette", "B")

    risultato = _scansiona(tmp_path)

    assert risultato["categorie_da_creare"] == ["Indumenti", "Indumenti > Magliette"]
    assert risultato["nuovi"][0]["piano_categorie"][1]["stato"] == "da_creare"


def test_un_conflitto_col_sito_segnala_il_prodotto_e_non_gli_altri(tmp_path, monkeypatch):
    _prodotto(tmp_path, "Indumenti", "Magliette", "Maglietta rossa")
    _prodotto(tmp_path, "Smartphone", "Nubia")
    messaggio = (
        "La categoria «Magliette» esiste gia' come «Abbigliamento > Magliette», ma la cartella "
        "la vuole in «Indumenti > Magliette»: un nome di categoria deve esistere una volta sola."
    )

    def verifica(percorsi):
        return {
            "percorsi": [
                {
                    "percorso": p,
                    "livelli": [],
                    "errori": [messaggio] if p == ["Indumenti", "Magliette"] else [],
                }
                for p in percorsi
            ],
            "conflitti_tra_percorsi": [],
            "conflitti": [],
        }

    monkeypatch.setattr(product_tools, "verifica_categorie", verifica)

    nuovi = {p["nome"]: p for p in _scansiona(tmp_path)["nuovi"]}

    assert nuovi["Maglietta rossa"]["avviso"].startswith("PROBLEMA CON LE CATEGORIE, non caricare")
    assert "Abbigliamento > Magliette" in nuovi["Maglietta rossa"]["problemi_categorie"][0]
    assert nuovi["Nubia"]["avviso"] is None
    assert nuovi["Nubia"]["problemi_categorie"] == []


def test_lo_stesso_nome_in_due_rami_delle_cartelle_segnala_i_prodotti_coinvolti(
    tmp_path, monkeypatch
):
    _prodotto(tmp_path, "Indumenti", "Magliette", "A")
    _prodotto(tmp_path, "Sport", "Magliette", "B")
    _prodotto(tmp_path, "Smartphone", "Nubia")
    conflitti = [{"nome": "Magliette", "posti": ["Indumenti > Magliette", "Sport > Magliette"]}]

    def verifica(percorsi):
        return {
            "percorsi": [{"percorso": p, "livelli": [], "errori": []} for p in percorsi],
            "conflitti_tra_percorsi": ["..."],
            "conflitti": conflitti,
        }

    monkeypatch.setattr(product_tools, "verifica_categorie", verifica)

    risultato = _scansiona(tmp_path)
    nuovi = {p["nome"]: p for p in risultato["nuovi"]}

    assert "«Magliette» compare in piu' punti" in nuovi["A"]["problemi_categorie"][0]
    assert nuovi["B"]["problemi_categorie"]
    assert nuovi["Nubia"]["problemi_categorie"] == []
    assert risultato["conflitti_categorie"] == conflitti


def test_se_il_confronto_col_sito_fallisce_la_scansione_resta_utile(tmp_path, monkeypatch):
    _prodotto(tmp_path, "Smartphone", "Nubia")

    def verifica(percorsi):
        raise requests.ConnectionError("sito non raggiungibile")

    monkeypatch.setattr(product_tools, "verifica_categorie", verifica)

    risultato = _scansiona(tmp_path)

    assert [p["nome"] for p in risultato["nuovi"]] == ["Nubia"]
    assert "non riuscito" in risultato["avviso_categorie"]
    assert risultato["nuovi"][0]["piano_categorie"] is None


# --- il percorso arriva al plugin -------------------------------------------------


class _Risposta:
    status_code = 200

    def __init__(self, dati):
        self._dati = dati

    def raise_for_status(self):
        pass

    def json(self):
        return self._dati


@pytest.fixture
def corpi(monkeypatch):
    registro = []

    def post(url, json=None, **kwargs):
        registro.append(json)
        return _Risposta({"stato": "creato_in_bozza", "prodotto_id": 1})

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "a")
    monkeypatch.setenv("WP_APP_PASSWORD", "b")
    return registro


def _argomenti(**extra):
    return {
        "titolo": "Maglietta",
        "descrizione": "<p>d</p>",
        "prezzo_regolare": "10",
        "categoria": "Magliette",
        "percorsi_immagini": [],
        "alt_immagini": [],
        "frase_chiave_focus": "maglietta",
        "titolo_seo": "t",
        "meta_description": "m",
        **extra,
    }


def test_crea_prodotto_manda_il_percorso_solo_se_c_e(corpi):
    product_tools.crea_prodotto(**_argomenti(percorso_categoria=["Indumenti", "Magliette"]))
    product_tools.crea_prodotto(**_argomenti())

    assert corpi[0]["percorso_categoria"] == ["Indumenti", "Magliette"]
    assert corpi[0]["categoria"] == "Magliette"
    assert "percorso_categoria" not in corpi[1]


def test_crea_prodotto_variabile_manda_il_percorso(corpi):
    product_tools.crea_prodotto_variabile(
        **_argomenti(
            attributi={"Taglia": ["S", "M"]}, percorso_categoria=["Indumenti", "Magliette"]
        )
    )

    assert corpi[0]["percorso_categoria"] == ["Indumenti", "Magliette"]
    assert corpi[0]["tipo"] == "variable"


def test_un_conflitto_di_categorie_torna_con_il_messaggio_del_plugin(monkeypatch):
    class Rifiuto:
        status_code = 409
        text = ""

        def json(self):
            return {
                "code": "push_contempt_categoria_in_conflitto",
                "message": "La categoria «Magliette» esiste gia'...",
            }

        def raise_for_status(self):
            raise requests.HTTPError("409", response=self)

    monkeypatch.setattr(requests, "post", lambda *a, **k: Rifiuto())
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    monkeypatch.setenv("WP_APP_USER", "a")
    monkeypatch.setenv("WP_APP_PASSWORD", "b")

    risultato = product_tools.crea_prodotto(
        **_argomenti(percorso_categoria=["Indumenti", "Magliette"])
    )

    assert risultato["creato"] is False
    assert "HTTP 409" in risultato["errore"]
    assert "esiste gia'" in risultato["errore"]
