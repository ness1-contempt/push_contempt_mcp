"""Creazione prodotto WooCommerce: client sottile della REST API del plugin
push_contempt (vedi includes/Rest/ProdottiController.php) - stesso principio
di inventory_tools.py e pricing_tools.py.

Il prodotto nasce sempre in BOZZA (status=draft): la REST API non pubblica
nulla, resta da rivedere e pubblicare da wp-admin. `prodotti_in_bozza` legge
quella lista (lo stato "draft" stesso e' il promemoria persistente, nessun
tracciamento a parte).
"""

import mimetypes
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from push_contempt_mcp import seo_tools

load_dotenv()


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def _carica_immagine(percorso: str) -> int:
    """Carica un'immagine su /wp/v2/media (endpoint nativo di WordPress,
    stesso meccanismo gia' usato da Prodotti/carica_immagini.py nella vecchia
    skill sincronizza-prodotti-woocommerce) e restituisce l'attachment ID.
    """
    site = os.environ["WP_SITE_URL"]
    file_path = Path(percorso)
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    risposta = requests.post(
        f"{site}/wp-json/wp/v2/media",
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"',
            "Content-Type": mime_type,
        },
        data=file_path.read_bytes(),
        auth=_auth(),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=30,
    )
    risposta.raise_for_status()
    return risposta.json()["id"]


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
    """Crea un prodotto WooCommerce in BOZZA (titolo, descrizione, prezzo,
    categoria, immagini), con SEO e ALT immagini gia' impostati: resta solo
    da rivedere e pubblicare da wp-admin (vedi `prodotti_in_bozza`).

    `percorsi_immagini[0]` diventa l'immagine in evidenza, le altre vanno
    nella galleria. `alt_immagini` deve avere un elemento per ogni immagine
    (stesso ordine di percorsi_immagini). Il prezzo va scritto con il punto
    come decimale. La risposta include `avvisi_seo`: se non vuoto, la
    descrizione non rispetta ancora densita' della frase chiave, sottotitoli
    o link interni - da sistemare prima di pubblicare.
    """
    if len(alt_immagini) != len(percorsi_immagini):
        raise ValueError(
            f"alt_immagini ({len(alt_immagini)} elementi) deve avere la stessa "
            f"lunghezza di percorsi_immagini ({len(percorsi_immagini)} elementi): "
            "un ALT per ogni immagine, stesso ordine."
        )

    try:
        attachment_ids = [_carica_immagine(percorso) for percorso in percorsi_immagini]
    except FileNotFoundError as errore:
        return {
            "errore": f"Immagine non trovata: {errore.filename}. I percorsi vanno indicati "
            "come sono sul computer dove gira il server MCP.",
            "creato": False,
        }
    except requests.RequestException as errore:
        return {
            "errore": f"Caricamento di un'immagine non riuscito: {_dettaglio(errore)}",
            "creato": False,
        }

    corpo = {
        "titolo": titolo,
        "descrizione": descrizione,
        "prezzo_regolare": prezzo_regolare,
        "categoria": categoria,
        "galleria_ids": attachment_ids[1:],
        "alt_immagini": dict(zip(attachment_ids, alt_immagini, strict=True)),
        "titolo_seo": titolo_seo,
        "meta_description": meta_description,
        "parola_chiave_focus": frase_chiave_focus,
    }
    if attachment_ids:
        # Senza immagini la chiave non va mandata: un null non e' un intero (400 dal plugin).
        corpo["immagine_evidenza_id"] = attachment_ids[0]

    site = os.environ["WP_SITE_URL"]
    try:
        risposta = requests.post(
            f"{site}/wp-json/push-contempt/v1/prodotti",
            json=corpo,
            auth=_auth(),
            verify=False,
            timeout=30,
        )
        risposta.raise_for_status()
    except requests.RequestException as errore:
        return {
            "errore": f"Creazione del prodotto non riuscita: {_dettaglio(errore)}",
            "creato": False,
        }
    risultato = risposta.json()
    risultato["avvisi_seo"] = seo_tools.valida_contenuto_seo(descrizione, frase_chiave_focus)
    return risultato


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


def prodotti_in_bozza() -> list[dict]:
    """Prodotti creati in bozza, in attesa di revisione/pubblicazione da
    wp-admin (piu' recenti prima)."""
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/prodotti/bozze",
        auth=_auth(),
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()


def elenco_prodotti(ricerca: str = "", limite: int = 20) -> list[dict]:
    """Catalogo WooCommerce (titolo, sku, prezzo, scorte) via la REST API del
    plugin push_contempt (vedi includes/Rest/ProdottiController.php),
    cosi' funziona anche dove il DB non e' raggiungibile dall'esterno
    (hosting condiviso di un cliente, es. Altervista).

    `ricerca` filtra per titolo (sottostringa, case-insensitive); vuoto =
    tutti. `limite` negativo = nessun limite.
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/prodotti",
        params={"ricerca": ricerca, "limite": limite},
        auth=_auth(),
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()
