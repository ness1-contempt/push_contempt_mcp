"""Nessun browser deve restare aperto dopo l'uso di un tool: con un finto Playwright
che registra aperture e chiusure si controlla che, dopo ogni tool (riuscito o fallito),
tutti i browser aperti siano chiusi e tutti i driver fermati."""

import playwright.sync_api
import pytest
from playwright.sync_api import Error as PlaywrightError

from push_contempt_mcp import browser_tools, competitor_seo


class _Pagina:
    def __init__(self, prezzo="10,00", errore_su=None):
        self.prezzo = prezzo
        self.errore_su = errore_su
        self.eventi = []
        self.context = None

    def _passo(self, nome):
        self.eventi.append(nome)
        if self.errore_su == nome:
            raise PlaywrightError(f"guasto simulato in {nome}")

    def goto(self, url, **kwargs):
        self._passo("goto")

    def wait_for_selector(self, selettore, **kwargs):
        self._passo(f"wait:{selettore}")

    def input_value(self, selettore):
        return self.prezzo

    def fill(self, selettore, valore):
        self.eventi.append(f"fill:{valore}")

    def eval_on_selector(self, selettore, js):
        self.eventi.append(f"click:{selettore}")

    def screenshot(self, **kwargs):
        pass


class _Browser:
    def __init__(self, registro, pagina, errore_in_chiusura=False):
        self.registro = registro
        self.pagina = pagina
        self.aperto = True
        self.errore_in_chiusura = errore_in_chiusura

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return self.pagina

    def close(self):
        self.aperto = False
        if self.errore_in_chiusura:
            raise PlaywrightError("gia' crollato")


class _Playwright:
    def __init__(self, registro, pagine, errore_in_chiusura=False, errore_avvio=False):
        self.registro = registro
        self.pagine = pagine
        self.errore_in_chiusura = errore_in_chiusura
        self.errore_avvio = errore_avvio
        self.fermato = False
        self.browsers = []
        self.chromium = self

    def start(self):
        return self

    def launch(self, headless=True):
        if self.errore_avvio:
            raise PlaywrightError("Chromium non parte")
        pagina = self.pagine.pop(0) if self.pagine else _Pagina()
        browser = _Browser(self.registro, pagina, self.errore_in_chiusura)
        self.browsers.append(browser)
        self.registro.append(browser)
        return browser

    def stop(self):
        self.fermato = True


@pytest.fixture
def finto(monkeypatch):
    """Sostituisce Playwright: `finto.browsers` sono tutti i browser aperti dai tool,
    `finto.drivers` tutti i driver avviati."""

    class Stato:
        browsers: list = []
        drivers: list = []
        pagine: list = []
        errore_in_chiusura = False

        def tutto_chiuso(self):
            return all(not b.aperto for b in self.browsers) and all(d.fermato for d in self.drivers)

    stato = Stato()
    stato.browsers, stato.drivers, stato.pagine = [], [], []

    def nuovo_playwright():
        driver = _Playwright(stato.browsers, stato.pagine, stato.errore_in_chiusura)
        stato.drivers.append(driver)
        return driver

    monkeypatch.setattr(browser_tools, "sync_playwright", nuovo_playwright)
    monkeypatch.setattr(browser_tools, "_assicura_login", lambda page, site: None)
    monkeypatch.setattr(
        browser_tools, "_formatta_prezzo_per_campo", lambda prezzo: prezzo.replace(".", ",")
    )
    monkeypatch.setattr(
        browser_tools, "_screenshot", lambda page, etichetta: f"/tmp/{etichetta}.png"
    )
    monkeypatch.setattr(browser_tools, "_in_sospeso", None)
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")
    return stato


# --- il gestore: chiude sempre -------------------------------------------------


def test_il_browser_si_chiude_a_lavoro_finito(finto):
    with browser_tools._browser_loggato():
        assert finto.browsers[0].aperto  # dentro il blocco e' aperto

    assert finto.tutto_chiuso()
    assert len(finto.browsers) == 1


def test_il_browser_si_chiude_anche_se_il_lavoro_fallisce(finto):
    with pytest.raises(RuntimeError, match="boom"), browser_tools._browser_loggato():
        raise RuntimeError("boom")

    assert finto.tutto_chiuso()


def test_il_browser_si_chiude_anche_se_il_login_fallisce(finto, monkeypatch):
    def login_fallito(page, site):
        raise RuntimeError("Login wp-admin fallito")

    monkeypatch.setattr(browser_tools, "_assicura_login", login_fallito)

    with pytest.raises(RuntimeError, match="Login"), browser_tools._browser_loggato():
        pytest.fail("non deve arrivare al lavoro")

    assert finto.tutto_chiuso()


def test_un_errore_nel_chiudere_il_browser_non_impedisce_di_fermare_il_driver(finto):
    finto.errore_in_chiusura = True

    with browser_tools._browser_loggato():
        pass

    assert finto.drivers[0].fermato


def test_se_chromium_non_parte_il_driver_si_ferma(monkeypatch):
    driver = _Playwright([], [], errore_avvio=True)
    monkeypatch.setattr(browser_tools, "sync_playwright", lambda: driver)
    monkeypatch.setenv("WP_SITE_URL", "https://localhost")

    with pytest.raises(PlaywrightError), browser_tools._browser_loggato():
        pytest.fail("non deve arrivare al lavoro")

    assert driver.fermato


# --- prezzo: prepara -> conferma, mai un browser aperto fra le due ---------------


def test_prepara_chiude_il_browser_e_ricorda_la_modifica(finto):
    risultato = browser_tools.prepara_modifica_prezzo_prodotto(42, "12.50")

    assert finto.tutto_chiuso()
    assert risultato["stato"] == "in_attesa_di_conferma"
    assert risultato["prezzo_attuale"] == "10,00"
    assert "browser e' stato chiuso" in risultato["nota"]
    assert browser_tools._in_sospeso["prodotto_id"] == 42
    assert browser_tools._in_sospeso["prezzo_campo"] == "12,50"


def test_prepara_che_fallisce_chiude_il_browser_e_non_ricorda_niente(finto):
    finto.pagine.append(_Pagina(errore_su="goto"))

    with pytest.raises(PlaywrightError):
        browser_tools.prepara_modifica_prezzo_prodotto(42, "12.50")

    assert finto.tutto_chiuso()
    assert browser_tools._in_sospeso is None


def test_conferma_riapre_ricontrolla_salva_e_richiude(finto):
    browser_tools.prepara_modifica_prezzo_prodotto(42, "12.50")
    pagina = _Pagina(prezzo="10,00")
    finto.pagine.append(pagina)

    risultato = browser_tools.conferma_modifica_in_corso()

    assert risultato["stato"] == "salvato"
    assert len(finto.browsers) == 2  # uno per prepara, uno per conferma
    assert finto.tutto_chiuso()
    assert "fill:12,50" in pagina.eventi
    assert "click:#publish" in pagina.eventi
    assert browser_tools._in_sospeso is None


def test_conferma_non_salva_se_il_prezzo_e_cambiato_nel_frattempo(finto):
    browser_tools.prepara_modifica_prezzo_prodotto(42, "12.50")
    pagina = _Pagina(prezzo="99,00")  # qualcuno l'ha cambiato dopo "prepara"
    finto.pagine.append(pagina)

    risultato = browser_tools.conferma_modifica_in_corso()

    assert risultato["stato"] == "annullato"
    assert "e' cambiato" in risultato["nota"]
    assert "click:#publish" not in pagina.eventi
    assert not any(e.startswith("fill:") for e in pagina.eventi)
    assert finto.tutto_chiuso()
    assert browser_tools._in_sospeso is None


def test_conferma_che_fallisce_chiude_il_browser_e_tiene_la_modifica_per_riprovare(finto):
    browser_tools.prepara_modifica_prezzo_prodotto(42, "12.50")
    finto.pagine.append(_Pagina(errore_su="wait:#message"))

    with pytest.raises(PlaywrightError):
        browser_tools.conferma_modifica_in_corso()

    assert finto.tutto_chiuso()
    assert browser_tools._in_sospeso is not None


def test_conferma_senza_modifica_non_apre_nessun_browser(finto):
    risultato = browser_tools.conferma_modifica_in_corso()

    assert risultato["stato"] == "errore"
    assert finto.browsers == []


def test_una_modifica_scaduta_non_si_conferma_e_non_apre_il_browser(finto, monkeypatch):
    browser_tools.prepara_modifica_prezzo_prodotto(42, "12.50")
    adesso = browser_tools._in_sospeso["preparata_alle"]
    monkeypatch.setattr(
        browser_tools.time,
        "monotonic",
        lambda: adesso + browser_tools.VALIDITA_MODIFICA_SECONDI + 1,
    )
    aperti_prima = len(finto.browsers)

    risultato = browser_tools.conferma_modifica_in_corso()

    assert "scaduta" in risultato["nota"]
    assert len(finto.browsers) == aperti_prima
    assert browser_tools._in_sospeso is None


def test_annulla_scarta_la_modifica_senza_aprire_browser(finto):
    browser_tools.prepara_modifica_prezzo_prodotto(42, "12.50")
    aperti = len(finto.browsers)

    assert browser_tools.annulla_modifica_in_corso() == {"stato": "annullato"}
    assert browser_tools._in_sospeso is None
    assert len(finto.browsers) == aperti
    assert browser_tools.annulla_modifica_in_corso()["stato"] == "errore"


# --- gli altri tool che usano il browser -----------------------------------------


def test_analisi_yoast_che_fallisce_chiude_il_browser(finto):
    finto.pagine.append(_Pagina(errore_su="wait:#wpseo-metabox-root"))

    with pytest.raises(PlaywrightError):
        browser_tools.leggi_analisi_seo_yoast(7)

    assert len(finto.browsers) == 1
    assert finto.tutto_chiuso()


def test_seo_categoria_che_fallisce_chiude_il_browser(finto):
    finto.pagine.append(_Pagina(errore_su="wait:#name"))

    with pytest.raises(PlaywrightError):
        browser_tools.aggiorna_seo_categoria(3, "Titolo", "Meta")

    assert len(finto.browsers) == 1
    assert finto.tutto_chiuso()


# --- analisi dei concorrenti ------------------------------------------------------


def test_analisi_concorrenti_se_la_pagina_non_si_crea_chiude_browser_e_driver(monkeypatch):
    registro: list = []
    driver = _Playwright(registro, [])
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: driver)
    monkeypatch.setattr(
        _Browser, "new_page", lambda self: (_ for _ in ()).throw(PlaywrightError("no"))
    )

    with pytest.raises(PlaywrightError):
        competitor_seo._avvia_playwright()

    assert registro[0].aperto is False
    assert driver.fermato


def test_analisi_concorrenti_se_chromium_non_parte_ferma_il_driver(monkeypatch):
    driver = _Playwright([], [], errore_avvio=True)
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: driver)

    with pytest.raises(PlaywrightError):
        competitor_seo._avvia_playwright()

    assert driver.fermato


def test_analisi_concorrenti_la_funzione_di_chiusura_chiude_tutto_anche_se_il_browser_crolla(
    monkeypatch,
):
    registro: list = []
    driver = _Playwright(registro, [], errore_in_chiusura=True)
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: driver)
    monkeypatch.setattr(_Pagina, "route", lambda self, *a, **k: None, raising=False)

    chiudi, _pagina = competitor_seo._avvia_playwright()
    with pytest.raises(PlaywrightError):
        chiudi()

    assert registro[0].aperto is False
    assert driver.fermato  # il driver si ferma comunque
