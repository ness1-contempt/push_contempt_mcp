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

from push_contempt_mcp import seo_tools
from push_contempt_mcp.db import get_connection

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
) -> int:
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
    attachment = modale.locator(".attachment.selected")
    attachment.wait_for(timeout=30000)
    # L'ID serve subito dopo per scrivere l'ALT (testo basso rischio -> DB
    # diretto, stesso pattern dei campi Yoast), senza doverlo poi recuperare
    # per nome file.
    attachment_id = int(attachment.get_attribute("data-id"))
    modale.locator(f"button:has-text('{bottone_conferma_testo}')").click()
    return attachment_id


def _imposta_alt_immagini(alt_per_attachment_id: dict[int, str]) -> None:
    """Scrive l'attributo ALT delle immagini caricate (DB diretto, testo
    semplice senza effetti collaterali: stesso pattern dei campi Yoast)."""
    with get_connection() as conn, conn.cursor() as cursor:
        for attachment_id, alt in alt_per_attachment_id.items():
            cursor.execute(
                "DELETE FROM wp_postmeta WHERE post_id = %s "
                "AND meta_key = '_wp_attachment_image_alt'",
                (attachment_id,),
            )
            cursor.execute(
                "INSERT INTO wp_postmeta (post_id, meta_key, meta_value) "
                "VALUES (%s, '_wp_attachment_image_alt', %s)",
                (attachment_id, alt),
            )


def crea_prodotto(
    titolo: str,
    descrizione: str,
    prezzo_regolare: str,
    categoria: str,
    percorsi_immagini: list[str],
    alt_immagini: list[str],
    frase_chiave_focus: str,
    titolo_seo: str,
    meta_description: str,
) -> dict:
    """Crea e pubblica un nuovo prodotto WooCommerce via wp-admin, GIA' con SEO
    e ALT immagini impostati: non serve piu' un passo separato dopo la
    creazione.

    `prezzo_regolare` con il punto come decimale (es. "39.90"), tradotto
    automaticamente nel formato del sito. `percorsi_immagini[0]` diventa
    l'immagine in evidenza, le altre vanno nella galleria prodotto.
    `alt_immagini` deve avere la stessa lunghezza di `percorsi_immagini`
    (un ALT descrittivo per ciascuna immagine, nello stesso ordine: descrivi
    cosa si vede davvero nella foto, es. "aperto a libro", "vista laterale").
    `frase_chiave_focus`/`titolo_seo`/`meta_description` sono gli stessi campi
    di `aggiorna_seo_prodotto`, scritti subito dopo la pubblicazione.

    La descrizione dovrebbe gia' rispettare le regole SEO on-page (frase
    chiave ripetuta almeno 2 volte nel testo, presente in almeno un
    sottotitolo H2/H3, almeno un link interno a un prodotto o categoria
    correlati): il risultato include un campo `avvisi_seo` con quello che
    manca, da correggere se non vuoto.

    A differenza di `prepara_modifica_prezzo_prodotto`, qui si pubblica
    direttamente: è una creazione di un prodotto nuovo (nessun dato esistente
    da sovrascrivere), quindi non serve il passo di conferma separato.
    """
    if len(alt_immagini) != len(percorsi_immagini):
        raise ValueError(
            f"alt_immagini ({len(alt_immagini)} elementi) deve avere la stessa "
            f"lunghezza di percorsi_immagini ({len(percorsi_immagini)} elementi): "
            "un ALT per ogni immagine, stesso ordine."
        )

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

    attachment_ids: list[int] = []
    if percorsi_immagini:
        attachment_ids.append(
            _carica_in_modale_media(
                page, "#set-post-thumbnail", percorsi_immagini[0], "Imposta immagine prodotto"
            )
        )
        page.wait_for_selector("#remove-post-thumbnail")
        for percorso in percorsi_immagini[1:]:
            attachment_ids.append(
                _carica_in_modale_media(
                    page, ".add_product_images a", percorso, "Aggiungi alla galleria"
                )
            )
            page.wait_for_timeout(500)

    _click_js(page, "#publish")
    page.wait_for_selector("#message")

    prodotto_id = int(page.url.split("post=")[1].split("&")[0])

    alt_per_id = dict(zip(attachment_ids, alt_immagini, strict=True))
    _imposta_alt_immagini(alt_per_id)
    seo = seo_tools.scrivi_campi_yoast(
        prodotto_id, titolo_seo, meta_description, frase_chiave_focus
    )
    avvisi_seo = seo_tools.valida_contenuto_seo(descrizione, frase_chiave_focus)

    return {
        "stato": "pubblicato",
        "prodotto_id": prodotto_id,
        "url": page.url,
        "screenshot": _screenshot(page, f"prodotto-{prodotto_id}-pubblicato"),
        "alt_immagini_impostate": alt_per_id,
        "seo": seo,
        "avvisi_seo": avvisi_seo,
    }


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
