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
from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

load_dotenv()

SCREENSHOT_DIR = Path(__file__).resolve().parent.parent.parent / ".screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Cookie di sessione wp-admin salvati su disco: dopo il primo login (che puo'
# richiedere un reCAPTCHA da spuntare a mano) i login successivi non servono
# piu' finche' il cookie e' valido ("Ricordami" = ~14 giorni). Contiene una
# sessione valida: e' in .gitignore e viene creato con permessi 600.
STATE_FILE = Path(__file__).resolve().parent.parent.parent / ".auth" / "wp_admin_state.json"

# Quanto aspettare che l'utente completi il reCAPTCHA nella finestra del browser.
ATTESA_RECAPTCHA_MS = 120_000

_playwright = None
_browser = None
_page: Page | None = None

_PATTERN_SFIDA_MATEMATICA = re.compile(r"(\d+)\s*([+\-×x*])\s*(\d+)\s*=")


def _calcola_sfida(testo: str) -> int | None:
    """Legge un'equazione tipo "7 + 2 =" dal testo e ne calcola il risultato."""
    corrispondenza = _PATTERN_SFIDA_MATEMATICA.search(testo)
    if not corrispondenza:
        return None
    a, operatore, b = corrispondenza.groups()
    a, b = int(a), int(b)
    return {"+": a + b, "-": a - b}.get(operatore, a * b)


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

    risultato = _calcola_sfida(testo)
    if risultato is None:
        return False

    page.locator("input[type=text], input[type=number]").first.fill(str(risultato))
    page.get_by_role("button", name=re.compile("Continua")).click()
    page.wait_for_load_state("domcontentloaded")
    return True


def _risolvi_sfida_nel_form(page: Page) -> bool:
    """Il form di login ha di suo una sfida Jetpack Protect ("9 + 1 = [ ]",
    campo #jetpack_protect_answer): e' un'addizione in chiaro, si risolve qui.
    Ritorna True se il campo c'era ed e' stato compilato.
    """
    if page.locator("#jetpack_protect_answer").count() == 0:
        return False

    risultato = _calcola_sfida(page.inner_text("label[for=jetpack_protect_answer]"))
    if risultato is None:
        return False

    page.fill("#jetpack_protect_answer", str(risultato))
    return True


def _completa_recaptcha(page: Page) -> None:
    """Il reCAPTCHA v2 ("Non sono un robot") NON si risolve da codice, ed e'
    proprio il punto: qui si prova solo il click sulla casella (a volte Google
    la accetta da sola) e poi si aspetta che sia l'utente a completarlo nella
    finestra del browser (headed), se serve. Il token compare nella textarea
    #g-recaptcha-response quando la sfida e' superata.
    """
    if page.locator(".g-recaptcha").count() == 0:
        return

    # Il div .g-recaptcha e' nell'HTML subito, ma la textarea del token la crea
    # lo script di Google quando ha finito di renderizzare il widget.
    page.wait_for_selector("#g-recaptcha-response", state="attached", timeout=15000)

    def _token_presente() -> bool:
        return bool(page.eval_on_selector("#g-recaptcha-response", "el => el.value"))

    if _token_presente():
        return

    try:
        page.frame_locator("iframe[title=reCAPTCHA]").locator("#recaptcha-anchor").click(
            timeout=5000
        )
    except PlaywrightError:
        pass  # pazienza: ci pensa l'utente nella finestra

    try:
        page.wait_for_function(
            "() => document.querySelector('#g-recaptcha-response')?.value",
            timeout=ATTESA_RECAPTCHA_MS,
        )
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "reCAPTCHA del login wp-admin non completato entro "
            f"{ATTESA_RECAPTCHA_MS // 1000}s: spunta 'Non sono un robot' nella "
            "finestra del browser aperta dal server MCP e riprova. Una volta "
            "loggato, la sessione viene salvata e non servira' ripeterlo."
        ) from None


def _esegui_login(page: Page, site: str, tentativi_rimasti: int = 2) -> None:
    page.goto(f"{site}/wp-login.php", wait_until="domcontentloaded")
    if _risolvi_sfida_antibot(page):
        page.goto(f"{site}/wp-login.php", wait_until="domcontentloaded")

    page.fill("#user_login", os.environ["WP_ADMIN_USER"])
    page.fill("#user_pass", os.environ["WP_ADMIN_PASSWORD"])
    page.check("#rememberme")  # cookie di lunga durata: meno login futuri
    _risolvi_sfida_nel_form(page)
    _completa_recaptcha(page)
    page.click("#wp-submit")
    # wp-admin esegue polling continuo (Heartbeat API): "networkidle" non si
    # risolve mai li', quindi si aspetta un elemento concreto della pagina di
    # destinazione (login riuscito, messaggio di errore, o la sfida antibot).
    # Niente "body" tra le alternative: esiste gia' nella pagina di login che
    # si sta lasciando, e farebbe leggere l'esito prima che il POST finisca.
    esito = (
        page.locator("#wpadminbar")
        .or_(page.locator("#login_error"))
        .or_(page.get_by_text("problema di matematica"))
    )
    esito.first.wait_for(timeout=30000)

    if _risolvi_sfida_antibot(page) and tentativi_rimasti > 0:
        _esegui_login(page, site, tentativi_rimasti - 1)
        return

    if page.locator("#login_error").count():
        raise RuntimeError(f"Login wp-admin rifiutato: {page.inner_text('#login_error').strip()}")


def _sessione_valida(context: BrowserContext, site: str) -> bool:
    """Controlla con una richiesta HTTP leggera (stessi cookie del browser, senza
    navigare) se la sessione wp-admin e' ancora viva: da loggati /wp-admin/
    risponde 200 con la admin bar, altrimenti redirige a wp-login.php."""
    try:
        risposta = context.request.get(f"{site}/wp-admin/", max_redirects=0, timeout=15000)
    except PlaywrightError:
        return False
    return risposta.status == 200 and 'id="wpadminbar"' in risposta.text()


def _salva_sessione(context: BrowserContext) -> None:
    STATE_FILE.parent.mkdir(mode=0o700, exist_ok=True)
    context.storage_state(path=str(STATE_FILE))
    STATE_FILE.chmod(0o600)


def _assicura_login(page: Page, site: str) -> None:
    """Se la sessione corrente e' scaduta rifa' il login e la salva su disco."""
    if _sessione_valida(page.context, site):
        return

    _esegui_login(page, site)
    if not _sessione_valida(page.context, site):
        raise RuntimeError(
            "Login wp-admin fallito: controlla WP_ADMIN_USER/WP_ADMIN_PASSWORD in .env"
        )
    _salva_sessione(page.context)


def _get_logged_in_page() -> Page:
    """Riusa la pagina già loggata se c'è (rifacendo il login solo se la sessione
    e' scaduta), altrimenti avvia browser, ripristina i cookie salvati e logga
    solo se non bastano."""
    global _playwright, _browser, _page

    site = os.environ["WP_SITE_URL"]

    if _page is not None and not _page.is_closed():
        _assicura_login(_page, site)
        return _page

    _playwright = _playwright or sync_playwright().start()
    # headless=False: la build Chromium "fallback" che Playwright scarica su
    # questo host (OS non ufficialmente supportato) calcola male la posizione
    # di alcuni elementi della sidebar di wp-admin in modalita' headless
    # ("outside of viewport" anche se visibili); in modalita' headed il
    # rendering e' corretto e i click nativi funzionano senza trucchi via JS.
    # Serve anche per il reCAPTCHA: l'utente deve poterlo vedere e spuntare.
    _browser = _browser or _playwright.chromium.launch(headless=False)
    context = _browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1600, "height": 1200},
        storage_state=str(STATE_FILE) if STATE_FILE.exists() else None,
    )
    _page = context.new_page()

    _assicura_login(_page, site)
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
