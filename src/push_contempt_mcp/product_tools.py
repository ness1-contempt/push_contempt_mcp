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

    attachment_ids = [_carica_immagine(percorso) for percorso in percorsi_immagini]

    site = os.environ["WP_SITE_URL"]
    risposta = requests.post(
        f"{site}/wp-json/push-contempt/v1/prodotti",
        json={
            "titolo": titolo,
            "descrizione": descrizione,
            "prezzo_regolare": prezzo_regolare,
            "categoria": categoria,
            "immagine_evidenza_id": attachment_ids[0] if attachment_ids else None,
            "galleria_ids": attachment_ids[1:],
            "alt_immagini": dict(zip(attachment_ids, alt_immagini, strict=True)),
            "titolo_seo": titolo_seo,
            "meta_description": meta_description,
            "parola_chiave_focus": frase_chiave_focus,
        },
        auth=_auth(),
        verify=False,
        timeout=30,
    )
    risposta.raise_for_status()
    risultato = risposta.json()
    risultato["avvisi_seo"] = seo_tools.valida_contenuto_seo(descrizione, frase_chiave_focus)
    return risultato


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
