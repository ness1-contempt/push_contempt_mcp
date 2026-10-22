"""Automazione browser per le operazioni "sensibili" di WooCommerce.

Pattern a due fasi, pensato per far rivedere all'utente l'operazione prima
che diventi definitiva:
  1. `prepara_*`  compila il form e si FERMA prima del submit, restituendo
     uno screenshot da controllare.
  2. `conferma_modifica_in_corso` / `annulla_modifica_in_corso` eseguono (o
     scartano) il submit sulla pagina lasciata aperta dal passo 1.

Usa Playwright in modalità sincrona: va bene perché il tool MCP è una
funzione sincrona, eseguita dall'SDK in un thread separato.
"""

import os
import re
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

load_dotenv()

SCREENSHOT_DIR = Path(__file__).resolve().parent.parent.parent / ".screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

_playwright = None
_browser = None
_page: Page | None = None

_PATTERN_SFIDA_MATEMATICA = re.compile(r"(\d+)\s*([+\-×x*])\s*(\d+)\s*=")


def _risolvi_sfida_antibot(page: Page) -> bool:
    """Altervista a volte interpone, al posto del login, una sfida tipo
    "Risolvi questo problema di matematica per dimostrare che non sei un
    bot": e' testo semplice nella pagina (non un'immagine), quindi si legge
    e si risolve senza bisogno di uno screenshot. Dopo averla risolta
    bisogna rifare il login da capo (e' la pagina stessa a dirlo).
    Ritorna True se la sfida c'era ed e' stata gestita.
    """
    testo = page.inner_text("body")
    if "problema di matematica" not in testo:
        return False

    corrispondenza = _PATTERN_SFIDA_MATEMATICA.search(testo)
    if not corrispondenza:
        return False

    a, operatore, b = corrispondenza.groups()
    a, b = int(a), int(b)
    risultato = {"+": a + b, "-": a - b}.get(operatore, a * b)

    page.locator("input[type=text], input[type=number]").first.fill(str(risultato))
    page.get_by_role("button", name=re.compile("Continua")).click()
    page.wait_for_load_state("domcontentloaded")
    return True


def _esegui_login(page: Page, site: str, tentativi_rimasti: int = 2) -> None:
    page.goto(f"{site}/wp-login.php", wait_until="domcontentloaded")
    if _risolvi_sfida_antibot(page):
        page.goto(f"{site}/wp-login.php", wait_until="domcontentloaded")

    page.fill("#user_login", os.environ["WP_ADMIN_USER"])
    page.fill("#user_pass", os.environ["WP_ADMIN_PASSWORD"])
    page.click("#wp-submit")
    # wp-admin esegue polling continuo (Heartbeat API): "networkidle" non si
    # risolve mai li', quindi si aspetta un elemento concreto della pagina di
    # destinazione (login riuscito, messaggio di errore, o la sfida antibot).
    page.wait_for_selector("#wpadminbar, #login_error, body")

    if _risolvi_sfida_antibot(page) and tentativi_rimasti > 0:
        _esegui_login(page, site, tentativi_rimasti - 1)


def _get_logged_in_page() -> Page:
    """Riusa la pagina già loggata se c'è, altrimenti avvia browser + login."""
    global _playwright, _browser, _page

    if _page is not None and not _page.is_closed():
        return _page

    site = os.environ["WP_SITE_URL"]
    _playwright = _playwright or sync_playwright().start()
    # headless=False: la build Chromium "fallback" che Playwright scarica su
    # questo host (OS non ufficialmente supportato) calcola male la posizione
    # di alcuni elementi della sidebar di wp-admin in modalita' headless
    # ("outside of viewport" anche se visibili); in modalita' headed il
    # rendering e' corretto e i click nativi funzionano senza trucchi via JS.
    _browser = _browser or _playwright.chromium.launch(headless=False)
    context = _browser.new_context(
        ignore_https_errors=True, viewport={"width": 1600, "height": 1200}
    )
    _page = context.new_page()

    _esegui_login(_page, site)

    if "wp-login.php" in _page.url:
        raise RuntimeError(
            "Login wp-admin fallito: controlla WP_ADMIN_USER/WP_ADMIN_PASSWORD in .env"
        )

    return _page


def _separatore_decimale_woocommerce() -> str:
    """Il campo prezzo di wp-admin applica una maschera basata su questa opzione:
    un punto inviato come decimale viene letto come separatore delle migliaia
    (es. "9.99" -> "999") se il sito usa la virgola, come in IT. Va quindi
    tradotto prima di scrivere nel campo.

    Letta via REST (vedi PrezziController::handle_impostazioni), cosi'
    funziona anche dove il DB non e' raggiungibile dall'esterno.
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/prezzi/impostazioni",
        auth=(os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"]),
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()["separatore_decimale"]


def _formatta_prezzo_per_campo(prezzo: str) -> str:
    """Converte un prezzo scritto con il punto come decimale (es. "9.99")
    nel formato che si aspetta il campo prezzo di wp-admin per questo sito."""
    separatore = _separatore_decimale_woocommerce()
    return prezzo.replace(".", separatore) if separatore != "." else prezzo


def _screenshot(page: Page, etichetta: str) -> str:
    path = SCREENSHOT_DIR / f"{etichetta}-{uuid.uuid4().hex[:8]}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def _click_js(page: Page, selector: str) -> None:
    """Click per qualunque elemento FUORI dal modale media di wp-admin.

    Gli actionability check di Playwright (incl. il controllo sul viewport)
    sono inaffidabili sulla pagina di modifica prodotto di wp-admin: falliscono
    in modo intermittente, a prescindere da headless/headed e dall'elemento
    (sidebar, checklist categorie, bottone Pubblica...). Il click via JS li
    bypassa e qui funziona sempre. Dentro al modale media vale l'opposto: li'
    serve _carica_in_modale_media, che usa invece il click nativo perche' le
    view Backbone/jQuery di WordPress non reagiscono a un click sintetico.
    """
    page.eval_on_selector(selector, "el => el.click()")


def prepara_modifica_prezzo_prodotto(prodotto_id: int, nuovo_prezzo_regolare: str) -> dict:
    """Apre il prodotto in wp-admin e compila il nuovo prezzo regolare, SENZA salvare.

    `nuovo_prezzo_regolare` va scritto con il punto come separatore decimale
    (es. "12.50"); viene tradotto automaticamente nel formato del sito.

    Restituisce uno screenshot da far controllare all'utente. Per rendere
    effettiva la modifica serve poi chiamare `conferma_modifica_in_corso`.
    """
    site = os.environ["WP_SITE_URL"]
    page = _get_logged_in_page()
    url = f"{site}/wp-admin/post.php?post={prodotto_id}&action=edit"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#_regular_price")
    page.fill("#_regular_price", _formatta_prezzo_per_campo(nuovo_prezzo_regolare))

    return {
        "stato": "in_attesa_di_conferma",
        "prodotto_id": prodotto_id,
        "nuovo_prezzo_regolare": nuovo_prezzo_regolare,
        "screenshot": _screenshot(page, f"prezzo-{prodotto_id}-preview"),
        "nota": "Form compilato ma NON salvato. Controlla lo screenshot, poi "
        "chiama conferma_modifica_in_corso per salvare o annulla_modifica_in_corso per scartare.",
    }


def conferma_modifica_in_corso() -> dict:
    """Clicca 'Aggiorna' sulla pagina prodotto lasciata aperta dal passo 'prepara_*'."""
    global _page
    if _page is None or _page.is_closed():
        return {"stato": "errore", "nota": "Nessuna modifica in sospeso da confermare."}

    page = _page
    _click_js(page, "#publish")
    page.wait_for_selector("#message")
    return {
        "stato": "salvato",
        "screenshot": _screenshot(page, "dopo-salvataggio"),
    }


def annulla_modifica_in_corso() -> dict:
    """Scarta la modifica in sospeso senza salvare (ricarica la pagina)."""
    global _page
    if _page is None or _page.is_closed():
        return {"stato": "errore", "nota": "Nessuna modifica in sospeso da annullare."}

    _page.reload()
    return {"stato": "annullato"}


def _scrivi_campo_draftjs(page: Page, selettore: str, testo: str) -> None:
    """I campi titolo/meta description di Yoast (anche sui termini di
    tassonomia) sono editor React/Draft.js, non <input>: .fill() non li
    aggiorna. Si clicca, si seleziona tutto e si ridigita.
    """
    campo = page.locator(selettore)
    campo.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(testo)


def aggiorna_seo_categoria(term_id: int, titolo_seo: str, meta_description: str) -> dict:
    """Scrive titolo SEO e meta description di una categoria prodotto (tassonomia
    product_cat) passando dalla UI di wp-admin.

    A differenza dei prodotti, per i termini di tassonomia Yoast non rilegge i
    propri campi se scritti via DB diretto (anche dopo un reindex): serve
    passare dal salvataggio reale della pagina di modifica categoria, che
    aggiorna correttamente l'indicizzabile interno di Yoast.
    """
    site = os.environ["WP_SITE_URL"]
    page = _get_logged_in_page()
    url = f"{site}/wp-admin/term.php?taxonomy=product_cat&tag_ID={term_id}&post_type=product"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#name")
    page.wait_for_timeout(1500)  # il metabox Yoast (React) si monta dopo il DOM ready

    _scrivi_campo_draftjs(page, "#yoast-google-preview-title-metabox", titolo_seo)
    _scrivi_campo_draftjs(page, "#yoast-google-preview-description-metabox", meta_description)

    page.wait_for_timeout(500)
    page.click("input[type=submit][value='Aggiorna']")
    page.wait_for_selector("#name")

    return {
        "stato": "aggiornato",
        "term_id": term_id,
        "titolo_seo": titolo_seo,
        "meta_description": meta_description,
    }


_INTESTAZIONE_CATEGORIA = re.compile(r"^(Problemi|Miglioramenti|Risultati buoni) \(\d+\)$")
_NOME_CHIAVE_CATEGORIA = {
    "Problemi": "problemi",
    "Miglioramenti": "miglioramenti",
    "Risultati buoni": "risultati_buoni",
}


def _analisi_seo_da_testo(blocco: str) -> dict:
    """Divide il testo grezzo del pannello "Risultati dell'analisi" di Yoast
    nelle sue tre categorie. Il blocco e' una sequenza di paragrafi separati
    da riga vuota: un'intestazione ("Problemi (1)") seguita dai paragrafi di
    quella categoria, fino alla prossima intestazione. L'ultima riga di ogni
    paragrafo e' quella controllata, cosi' la primissima intestazione (che
    nel testo e' preceduta da "Risultati dell'analisi\\n" sulla stessa riga
    di paragrafo) viene riconosciuta comunque.
    """
    sezioni: dict = {"problemi": [], "miglioramenti": [], "risultati_buoni": []}
    categoria_corrente = None

    for paragrafo in blocco.split("\n\n"):
        paragrafo = paragrafo.strip()
        if not paragrafo:
            continue
        corrispondenza = _INTESTAZIONE_CATEGORIA.match(paragrafo.splitlines()[-1])
        if corrispondenza:
            categoria_corrente = _NOME_CHIAVE_CATEGORIA[corrispondenza.group(1)]
            continue
        if categoria_corrente:
            sezioni[categoria_corrente].append(paragrafo)

    return sezioni


def leggi_analisi_seo_yoast(prodotto_id: int) -> dict:
    """Apre il prodotto in wp-admin e legge il verdetto REALE di Yoast
    (problemi/miglioramenti/risultati buoni), non la nostra approssimazione
    in seo_tools.valida_contenuto_seo: Yoast calcola la sua analisi in JS
    lato client nell'editor, non c'e' una REST API che dia lo stesso
    dettaglio, quindi serve leggerla da li'.
    """
    site = os.environ["WP_SITE_URL"]
    page = _get_logged_in_page()
    url = f"{site}/wp-admin/post.php?post={prodotto_id}&action=edit"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_selector("#wpseo-metabox-root")

    risultati = page.get_by_text("Risultati dell'analisi", exact=False).first
    page.wait_for_timeout(1500)  # Yoast calcola l'analisi in modo asincrono dopo il mount
    if not risultati.is_visible():
        page.get_by_text("Analisi SEO", exact=False).first.click()
    risultati.wait_for(timeout=15000)

    testo = page.inner_text("#wpseo-metabox-root")
    inizio = testo.find("Risultati dell'analisi")
    fine = testo.find("Aggiungi una frase chiave correlata")
    blocco = testo[inizio : fine if fine != -1 else None]

    return {"prodotto_id": prodotto_id, **_analisi_seo_da_testo(blocco)}
