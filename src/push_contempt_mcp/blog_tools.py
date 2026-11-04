"""Blog: client sottile della REST API del plugin push_contempt (vedi
includes/Rest/BlogController.php), stesso schema di product_tools.py.

Il plugin non usa l'AI: offre brief e contesto del negozio e un posto dove lasciare gli
articoli, che nascono SEMPRE in bozza (la pubblicazione resta all'utente da wp-admin).
La scrittura la fa l'assistente dell'utente; qui ci sono i tool per leggere il materiale,
caricare le immagini e salvare l'articolo, piu' `valida_articolo`, i controlli on-page
che non richiedono l'AI.
"""

import mimetypes
import os
import re
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# Lunghezze consigliate da Yoast e dai motori di ricerca (caratteri).
TITOLO_SEO_MAX = 60
META_MIN = 120
META_MAX = 160
# Sotto questa quota della lunghezza chiesta nel brief l'articolo e' troppo corto.
QUOTA_LUNGHEZZA_MIN = 0.7

_SEGNAPOSTO = re.compile(
    r"lorem ipsum|\[(?:inserire|da completare|todo|link|fonte|prodotto)[^\]]*\]|\bTODO\b|\bXXX+\b",
    re.IGNORECASE,
)


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def _url(percorso: str) -> str:
    return f"{os.environ['WP_SITE_URL']}/wp-json/push-contempt/v1/{percorso}"


def _dettaglio(errore: requests.RequestException) -> str:
    """Stato e messaggio che manda WordPress, non solo "400 Client Error"."""
    risposta = getattr(errore, "response", None)
    if risposta is None:
        return str(errore)
    try:
        messaggio = risposta.json().get("message", risposta.text)
    except ValueError:
        messaggio = risposta.text
    return f"HTTP {risposta.status_code}: {messaggio}"


def _chiama(metodo: str, percorso: str, **richiesta) -> dict | list:
    """Chiama il plugin; un errore HTTP diventa `{"errore": ...}` con il messaggio vero
    di WordPress (e `articolo_id` se e' un doppione), invece di un'eccezione generica."""
    try:
        risposta = requests.request(
            metodo,
            _url(percorso),
            auth=_auth(),
            verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
            timeout=60,
            **richiesta,
        )
        risposta.raise_for_status()
    except requests.RequestException as errore:
        esito = {"errore": _dettaglio(errore)}
        corpo = getattr(getattr(errore, "response", None), "json", None)
        try:
            dati = corpo()["data"] if corpo else {}
        except (ValueError, KeyError, TypeError):
            dati = {}
        if isinstance(dati, dict) and "articolo_id" in dati:
            esito["articolo_id"] = dati["articolo_id"]
        return esito
    return risposta.json()


def leggi_brief_blog() -> dict:
    """Le indicazioni del negozio per il blog (argomento, pubblico, tono, lingua,
    lunghezza, quanti articoli, categorie di prodotti, note) e `compilato`."""
    return _chiama("GET", "blog/brief")


def salva_brief_blog(
    argomento: str | None = None,
    pubblico: str | None = None,
    tono: str | None = None,
    lingua: str | None = None,
    lunghezza_parole: int | None = None,
    n_articoli: int | None = None,
    categorie_prodotti: list[int] | None = None,
    note: str | None = None,
) -> dict:
    """Aggiorna il brief: cambiano solo i campi passati, gli altri restano."""
    campi = {
        "argomento": argomento,
        "pubblico": pubblico,
        "tono": tono,
        "lingua": lingua,
        "lunghezza_parole": lunghezza_parole,
        "n_articoli": n_articoli,
        "categorie_prodotti": categorie_prodotti,
        "note": note,
    }
    return _chiama("POST", "blog/brief", json={k: v for k, v in campi.items() if v is not None})


def contesto_blog() -> dict:
    """Negozio, brief, categorie di prodotti e del blog, prodotti piu' venduti (con
    indirizzo e immagine) e articoli gia' presenti."""
    return _chiama("GET", "blog/contesto")


def lista_articoli(stato: str = "any", ricerca: str = "", limite: int = 50) -> list[dict] | dict:
    """Articoli del blog (piu' recenti prima). `stato`: any, draft o publish."""
    if stato not in ("any", "draft", "publish"):
        return {"errore": 'Lo stato va scelto fra "any", "draft" e "publish".'}
    return _chiama(
        "GET", "blog/articoli", params={"stato": stato, "ricerca": ricerca, "limite": limite}
    )


def leggi_articolo(articolo_id: int) -> dict:
    """Un articolo per intero: testo, categorie, tag e campi SEO."""
    return _chiama("GET", f"blog/articoli/{articolo_id}")


def carica_immagine_blog(percorso: str, alt: str) -> dict:
    """Carica un'immagine nella libreria media di WordPress (percorso sul computer
    dove gira il server MCP) con il suo testo ALT e restituisce `{ id, url, alt }`:
    `url` serve per metterla nel testo (<img src=...>), `id` per l'immagine in evidenza."""
    if not alt.strip():
        return {"errore": "Serve il testo ALT dell'immagine."}
    file = Path(percorso)
    if not file.is_file():
        return {
            "errore": f"Immagine non trovata: {percorso}. I percorsi vanno indicati come sono "
            "sul computer dove gira il server MCP."
        }
    site = os.environ["WP_SITE_URL"]
    mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    try:
        risposta = requests.post(
            f"{site}/wp-json/wp/v2/media",
            headers={
                "Content-Disposition": f'attachment; filename="{file.name}"',
                "Content-Type": mime,
            },
            data=file.read_bytes(),
            auth=_auth(),
            verify=False,
            timeout=60,
        )
        risposta.raise_for_status()
        media = risposta.json()
        requests.post(
            f"{site}/wp-json/wp/v2/media/{media['id']}",
            json={"alt_text": alt},
            auth=_auth(),
            verify=False,
            timeout=30,
        ).raise_for_status()
    except requests.RequestException as errore:
        return {"errore": f"Caricamento dell'immagine non riuscito: {_dettaglio(errore)}"}
    return {"id": media["id"], "url": media.get("source_url"), "alt": alt}


def valida_articolo(
    contenuto: str,
    frase_chiave_focus: str = "",
    titolo_seo: str = "",
    meta_description: str = "",
    lunghezza_attesa: int | None = None,
    n_link_interni: int | None = None,
    n_link_esterni: int | None = None,
    ha_immagine_evidenza: bool = True,
    n_parole: int | None = None,
) -> list[str]:
    """Controlli on-page che non servono all'AI: frase chiave nel testo e nei sottotitoli,
    struttura, lunghezze di titolo SEO e meta description, link interni ed esterni,
    segnaposto dimenticati. Restituisce gli avvisi da correggere (vuota se va bene)."""
    avvisi: list[str] = []
    testo = re.sub(r"<[^>]+>", " ", contenuto)
    parole = n_parole if n_parole is not None else len(testo.split())
    frase = frase_chiave_focus.strip().lower()

    if frase:
        presenze = testo.lower().count(frase)
        if presenze < 2:
            avvisi.append(
                f"La frase chiave '{frase_chiave_focus}' compare {presenze} volta/e: "
                "usala almeno due volte in modo naturale."
            )
        sottotitoli = re.findall(r"<h[23][^>]*>(.*?)</h[23]>", contenuto, re.IGNORECASE | re.DOTALL)
        if not any(frase in s.lower() for s in sottotitoli):
            avvisi.append(f"Nessun H2/H3 contiene la frase chiave '{frase_chiave_focus}'.")
    else:
        avvisi.append("Manca la frase chiave: serve per il SEO dell'articolo.")

    if not re.search(r"<h2\b", contenuto, re.IGNORECASE):
        avvisi.append("Nessun sottotitolo H2: dividi il testo in sezioni con titoli chiari.")
    if re.search(r"<h1\b", contenuto, re.IGNORECASE):
        avvisi.append("Nel testo c'e' un H1: il titolo dell'articolo e' gia' l'H1, usa H2 e H3.")

    if lunghezza_attesa and parole < lunghezza_attesa * QUOTA_LUNGHEZZA_MIN:
        avvisi.append(
            f"Il testo ha circa {parole} parole, il brief ne chiede circa {lunghezza_attesa}."
        )

    if not titolo_seo.strip():
        avvisi.append("Manca il titolo SEO.")
    elif len(titolo_seo) > TITOLO_SEO_MAX:
        avvisi.append(
            f"Il titolo SEO ha {len(titolo_seo)} caratteri: oltre {TITOLO_SEO_MAX} viene tagliato."
        )
    if not meta_description.strip():
        avvisi.append("Manca la meta description.")
    elif not META_MIN <= len(meta_description) <= META_MAX:
        avvisi.append(
            f"La meta description ha {len(meta_description)} caratteri: "
            f"meglio fra {META_MIN} e {META_MAX}."
        )

    if n_link_interni == 0:
        avvisi.append(
            "Nessun link interno: collega almeno un prodotto o una categoria del negozio."
        )
    if n_link_esterni == 0:
        avvisi.append("Nessun link esterno: cita almeno una fonte autorevole (Yoast lo chiede).")
    if not ha_immagine_evidenza:
        avvisi.append("Manca l'immagine in evidenza.")
    if _SEGNAPOSTO.search(contenuto):
        avvisi.append(
            "Nel testo c'e' un segnaposto da completare (lorem ipsum, [inserire...], TODO)."
        )

    return avvisi


def _con_avvisi(
    risultato: dict,
    contenuto: str,
    frase_chiave_focus: str,
    titolo_seo: str,
    meta_description: str,
    lunghezza_attesa: int | None,
    ha_immagine_evidenza: bool,
) -> dict:
    """Aggiunge `avvisi` a una risposta riuscita del plugin."""
    if "errore" not in risultato:
        risultato["avvisi"] = valida_articolo(
            contenuto,
            frase_chiave_focus,
            titolo_seo,
            meta_description,
            lunghezza_attesa,
            risultato.get("n_link_interni"),
            risultato.get("n_link_esterni"),
            ha_immagine_evidenza,
            risultato.get("n_parole"),
        )
    return risultato


def _corpo(**campi) -> dict:
    """I campi valorizzati: quelli a None non si mandano (il plugin cambia solo quelli presenti)."""
    return {nome: valore for nome, valore in campi.items() if valore is not None}


def _lunghezza_del_brief() -> int | None:
    brief = leggi_brief_blog()
    valore = brief.get("lunghezza_parole") if isinstance(brief, dict) else None
    return valore if isinstance(valore, int) else None


def crea_articolo_bozza(
    titolo: str,
    contenuto: str,
    frase_chiave_focus: str,
    titolo_seo: str,
    meta_description: str,
    categoria: str | None = None,
    tag: list[str] | None = None,
    estratto: str | None = None,
    immagine_evidenza_id: int | None = None,
    prodotti_ids: list[int] | None = None,
    consenti_duplicato: bool = False,
) -> dict:
    """Crea un articolo del blog in BOZZA (mai pubblicato) e restituisce `articolo_id`,
    `url_modifica`, i conteggi di parole e link e `avvisi` (controlli on-page da correggere
    con aggiorna_articolo_bozza prima di consegnare). Un titolo gia' usato da un altro
    articolo viene rifiutato (`articolo_id` dell'esistente nell'errore)."""
    risultato = _chiama(
        "POST",
        "blog/articoli",
        json=_corpo(
            titolo=titolo,
            contenuto=contenuto,
            titolo_seo=titolo_seo,
            meta_description=meta_description,
            parola_chiave_focus=frase_chiave_focus,
            categoria=categoria,
            tag=tag,
            estratto=estratto,
            immagine_evidenza_id=immagine_evidenza_id,
            prodotti_ids=prodotti_ids,
            consenti_duplicato=consenti_duplicato or None,
        ),
    )
    return _con_avvisi(
        risultato,
        contenuto,
        frase_chiave_focus,
        titolo_seo,
        meta_description,
        _lunghezza_del_brief(),
        immagine_evidenza_id is not None,
    )


def aggiorna_articolo_bozza(
    articolo_id: int,
    titolo: str | None = None,
    contenuto: str | None = None,
    frase_chiave_focus: str | None = None,
    titolo_seo: str | None = None,
    meta_description: str | None = None,
    categoria: str | None = None,
    tag: list[str] | None = None,
    estratto: str | None = None,
    immagine_evidenza_id: int | None = None,
    prodotti_ids: list[int] | None = None,
) -> dict:
    """Modifica una BOZZA (solo i campi passati); un articolo pubblicato viene rifiutato.
    Rilegge l'articolo e restituisce gli `avvisi` aggiornati sul testo completo."""
    risultato = _chiama(
        "POST",
        f"blog/articoli/{articolo_id}",
        json=_corpo(
            titolo=titolo,
            contenuto=contenuto,
            titolo_seo=titolo_seo,
            meta_description=meta_description,
            parola_chiave_focus=frase_chiave_focus,
            categoria=categoria,
            tag=tag,
            estratto=estratto,
            immagine_evidenza_id=immagine_evidenza_id,
            prodotti_ids=prodotti_ids,
        ),
    )
    if "errore" in risultato:
        return risultato
    completo = leggi_articolo(articolo_id)
    if "errore" in completo:
        return risultato
    return _con_avvisi(
        risultato,
        completo.get("contenuto") or "",
        completo.get("parola_chiave_focus") or "",
        completo.get("titolo_seo") or "",
        completo.get("meta_description") or "",
        _lunghezza_del_brief(),
        completo.get("immagine_evidenza_id") is not None,
    )
