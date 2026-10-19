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
import uuid
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

from mio_mcp_server.db import get_connection

load_dotenv()

SCREENSHOT_DIR = Path(__file__).resolve().parent.parent.parent / ".screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

_playwright = None
_browser = None
_page: Page | None = None


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

    _page.goto(f"{site}/wp-login.php", wait_until="domcontentloaded")
    _page.fill("#user_login", os.environ["WP_ADMIN_USER"])
    _page.fill("#user_pass", os.environ["WP_ADMIN_PASSWORD"])
    _page.click("#wp-submit")
    # wp-admin esegue polling continuo (Heartbeat API): "networkidle" non si
    # risolve mai li', quindi si aspetta un elemento concreto della pagina di
    # destinazione (login riuscito o messaggio di errore).
    _page.wait_for_selector("#wpadminbar, #login_error")

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
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT option_value FROM wp_options "
            "WHERE option_name = 'woocommerce_price_decimal_sep'"
        )
        row = cursor.fetchone()
        return row["option_value"] if row else "."


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


def _seleziona_o_crea_categoria(page: Page, categoria: str) -> None:
    checkbox = page.query_selector(f"#product_catchecklist li:has-text('{categoria}') input")
    if checkbox:
        # .check() di Playwright e' inaffidabile su questa checklist (falso
        # "outside of viewport" anche in modalita' headed): si imposta lo
        # stato via JS, che per un checkbox funziona bene.
        page.evaluate(
            "el => { el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); }",
            checkbox,
        )
        return

    _click_js(page, "#product_cat-add-toggle")
    page.fill("#newproduct_cat", categoria)
    _click_js(page, "#product_cat-add-submit")
    page.wait_for_selector(f"#product_catchecklist li:has-text('{categoria}')", timeout=15000)


def _carica_in_modale_media(
    page: Page,
    apri_modale_selector: str,
    percorso_immagine: str,
    bottone_conferma_testo: str,
) -> None:
    # wp-admin non rimuove il <div id="wp-media-modal"> del frame precedente
    # (es. l'immagine in evidenza) quando se ne apre un altro (es. la
    # galleria): restano due ".media-modal" nel DOM, quello vecchio nascosto.
    # Tutte le interazioni vanno quindi scoperte sull'ULTIMO modal aperto
    # (quello visibile), non su un selettore generico sulla pagina.
    _click_js(page, apri_modale_selector)
    modale = page.locator(".media-modal").last
    modale.wait_for(state="visible", timeout=10000)
    tab_carica = modale.locator("#menu-item-upload")
    if tab_carica.count() > 0:
        tab_carica.click()
    file_input = modale.locator("input[type=file]")
    file_input.set_input_files(percorso_immagine)
    modale.locator(".attachment.selected").wait_for(timeout=30000)
    modale.locator(f"button:has-text('{bottone_conferma_testo}')").click()


def crea_prodotto(
    titolo: str,
    descrizione: str,
    prezzo_regolare: str,
    categoria: str,
    percorsi_immagini: list[str],
) -> dict:
    """Crea e pubblica un nuovo prodotto WooCommerce via wp-admin.

    `prezzo_regolare` con il punto come decimale (es. "39.90"), tradotto
    automaticamente nel formato del sito. `percorsi_immagini[0]` diventa
    l'immagine in evidenza, le altre vanno nella galleria prodotto.

    A differenza di `prepara_modifica_prezzo_prodotto`, qui si pubblica
    direttamente: è una creazione di un prodotto nuovo (nessun dato esistente
    da sovrascrivere), quindi non serve il passo di conferma separato.
    """
    site = os.environ["WP_SITE_URL"]
    page = _get_logged_in_page()
    page.goto(f"{site}/wp-admin/post-new.php?post_type=product", wait_until="domcontentloaded")
    page.wait_for_selector("#title")
    page.fill("#title", titolo)

    _click_js(page, "#content-html")  # editor in modalità testo semplice, niente iframe TinyMCE
    page.fill("#content", descrizione)

    page.wait_for_selector("#_regular_price")
    page.fill("#_regular_price", _formatta_prezzo_per_campo(prezzo_regolare))

    _seleziona_o_crea_categoria(page, categoria)

    if percorsi_immagini:
        _carica_in_modale_media(
            page, "#set-post-thumbnail", percorsi_immagini[0], "Imposta immagine prodotto"
        )
        page.wait_for_selector("#remove-post-thumbnail")
        for percorso in percorsi_immagini[1:]:
            _carica_in_modale_media(
                page, ".add_product_images a", percorso, "Aggiungi alla galleria"
            )
            page.wait_for_timeout(500)

    _click_js(page, "#publish")
    page.wait_for_selector("#message")

    prodotto_id = int(page.url.split("post=")[1].split("&")[0])
    return {
        "stato": "pubblicato",
        "prodotto_id": prodotto_id,
        "url": page.url,
        "screenshot": _screenshot(page, f"prodotto-{prodotto_id}-pubblicato"),
    }
