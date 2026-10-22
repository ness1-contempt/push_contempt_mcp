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


# Blocco reale catturato dal pannello "Risultati dell'analisi" di Yoast
# (inner_text del metabox, prodotto con 1 problema/2 miglioramenti/14 risultati
# buoni) - vedi browser_tools._analisi_seo_da_testo.
_BLOCCO_ANALISI_SEO_REALE = (
    "Risultati dell'analisi\n"
    "Problemi (1)\n\n"
    "Link in uscita: non ci sono link in uscita in questa pagina. "
    "Ti suggeriamo di aggiungerne qualcuno.\n\n"
    "Miglioramenti (2)\n\n"
    "Lunghezza della meta descrizione: la meta descrizione è troppo corta.\n\n"
    "Lunghezza del testo: il testo contiene 291 parole.\n\n"
    "Risultati buoni (14)\n\n"
    "Frase chiave nell'attributo ALT della immagine: ottimo lavoro!\n\n"
    "Immagini: ottimo lavoro!\n\n"
)


def test_analisi_seo_da_testo_divide_le_tre_categorie():
    sezioni = browser_tools._analisi_seo_da_testo(_BLOCCO_ANALISI_SEO_REALE)

    assert sezioni["problemi"] == [
        "Link in uscita: non ci sono link in uscita in questa pagina. "
        "Ti suggeriamo di aggiungerne qualcuno."
    ]
    assert sezioni["miglioramenti"] == [
        "Lunghezza della meta descrizione: la meta descrizione è troppo corta.",
        "Lunghezza del testo: il testo contiene 291 parole.",
    ]
    assert sezioni["risultati_buoni"] == [
        "Frase chiave nell'attributo ALT della immagine: ottimo lavoro!",
        "Immagini: ottimo lavoro!",
    ]


def test_analisi_seo_da_testo_categoria_assente_resta_vuota():
    blocco = "Risultati dell'analisi\nRisultati buoni (1)\n\nTutto ok: ottimo lavoro!\n\n"

    sezioni = browser_tools._analisi_seo_da_testo(blocco)

    assert sezioni["problemi"] == []
    assert sezioni["miglioramenti"] == []
    assert sezioni["risultati_buoni"] == ["Tutto ok: ottimo lavoro!"]


class _LocatorFinto:
    def __init__(self, pagina, chiamate_attese):
        self._pagina = pagina
        self._chiamate_attese = chiamate_attese

    @property
    def first(self):
        return self

    def fill(self, valore):
        self._pagina.compilato = valore

    def click(self):
        self._pagina.cliccato = True


class _PaginaFinta:
    """Fake minimale di Page, solo per _risolvi_sfida_antibot: espone
    inner_text/locator/get_by_role/wait_for_load_state con lo stesso
    contratto usato dal codice, senza bisogno di un browser reale."""

    def __init__(self, testo):
        self._testo = testo
        self.compilato = None
        self.cliccato = False
        self.attesa_caricamento = False

    def inner_text(self, _selettore):
        return self._testo

    def locator(self, _selettore):
        return _LocatorFinto(self, None)

    def get_by_role(self, _ruolo, name=None):
        assert name.search("Continua")
        return _LocatorFinto(self, None)

    def wait_for_load_state(self, *_a, **_k):
        self.attesa_caricamento = True


def test_risolvi_sfida_antibot_assente_non_tocca_la_pagina():
    pagina = _PaginaFinta("Bentornato in wp-admin.")

    assert browser_tools._risolvi_sfida_antibot(pagina) is False
    assert pagina.compilato is None
    assert pagina.cliccato is False


def test_risolvi_sfida_antibot_risolve_addizione():
    pagina = _PaginaFinta(
        "Risolvi questo problema di matematica per dimostrare che non sei un bot.\n7 + 2 ="
    )

    assert browser_tools._risolvi_sfida_antibot(pagina) is True
    assert pagina.compilato == "9"
    assert pagina.cliccato is True
    assert pagina.attesa_caricamento is True


def test_risolvi_sfida_antibot_risolve_sottrazione_e_moltiplicazione():
    for testo, atteso in [
        ("problema di matematica\n9 - 4 =", "5"),
        ("problema di matematica\n6 x 3 =", "18"),
    ]:
        pagina = _PaginaFinta(testo)
        assert browser_tools._risolvi_sfida_antibot(pagina) is True
        assert pagina.compilato == atteso
