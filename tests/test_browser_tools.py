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


class _PaginaFormFinta:
    """Fake di Page per il form di login: solo i metodi usati da
    _risolvi_sfida_nel_form."""

    def __init__(self, etichetta=None):
        self._etichetta = etichetta
        self.compilati = {}

    def locator(self, _selettore):
        class _Conteggio:
            def count(inner):
                return 0 if self._etichetta is None else 1

        return _Conteggio()

    def inner_text(self, _selettore):
        return self._etichetta

    def fill(self, selettore, valore):
        self.compilati[selettore] = valore


def test_risolvi_sfida_nel_form_compila_la_somma_jetpack():
    # Il label reale contiene spazi non separabili (&nbsp;) attorno agli operandi.
    pagina = _PaginaFormFinta("9 \xa0+\xa0 1 \xa0=\xa0")

    assert browser_tools._risolvi_sfida_nel_form(pagina) is True
    assert pagina.compilati == {"#jetpack_protect_answer": "10"}


def test_risolvi_sfida_nel_form_assente_non_compila_nulla():
    pagina = _PaginaFormFinta(None)

    assert browser_tools._risolvi_sfida_nel_form(pagina) is False
    assert pagina.compilati == {}


class _RispostaSessione:
    def __init__(self, status, testo):
        self.status = status
        self._testo = testo

    def text(self):
        return self._testo


class _ContestoFinto:
    def __init__(self, risposta=None, errore=None):
        self.request = self
        self._risposta = risposta
        self._errore = errore

    def get(self, url, **_kw):
        if self._errore:
            raise self._errore
        return self._risposta


def test_sessione_valida_solo_con_200_e_admin_bar():
    ok = _ContestoFinto(_RispostaSessione(200, '<div id="wpadminbar">'))
    redirect = _ContestoFinto(_RispostaSessione(302, ""))
    sfida = _ContestoFinto(_RispostaSessione(200, "Risolvi questo problema di matematica"))

    assert browser_tools._sessione_valida(ok, "https://x") is True
    assert browser_tools._sessione_valida(redirect, "https://x") is False
    assert browser_tools._sessione_valida(sfida, "https://x") is False


def test_sessione_valida_false_se_la_richiesta_fallisce():
    contesto = _ContestoFinto(errore=browser_tools.PlaywrightError("net::ERR"))

    assert browser_tools._sessione_valida(contesto, "https://x") is False


def test_salva_sessione_scrive_file_con_permessi_600(monkeypatch, tmp_path):
    monkeypatch.setattr(browser_tools, "STATE_FILE", tmp_path / ".auth" / "stato.json")

    class _Contesto:
        def storage_state(self, path):
            open(path, "w").write("{}")

    browser_tools._salva_sessione(_Contesto())

    assert (tmp_path / ".auth" / "stato.json").stat().st_mode & 0o777 == 0o600
