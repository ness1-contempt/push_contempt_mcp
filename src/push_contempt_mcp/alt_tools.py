"""Lettura/scrittura del testo ALT delle immagini di un prodotto (in evidenza e
galleria): client sottile della REST API del plugin push_contempt (vedi
includes/Rest/AltImmaginiController.php), stesso schema di seo_tools.py.

Solo I/O: che ALT scrivere lo decide chi chiama il tool. Il plugin rifiuta
gli allegati che non appartengono al prodotto.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def _url() -> str:
    return f"{os.environ['WP_SITE_URL']}/wp-json/push-contempt/v1/alt/prodotto"


def leggi_alt_immagini_prodotto(prodotto_id: int) -> dict:
    """Immagine in evidenza e galleria del prodotto, ciascuna con ALT, file e
    URL, piu' la parola chiave focus Yoast (di solito va nell'ALT)."""
    risposta = requests.get(
        _url(),
        params={"id": prodotto_id},
        auth=_auth(),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=10,
    )
    if risposta.status_code == 404:
        return {"errore": f"Nessun prodotto con id {prodotto_id}"}
    risposta.raise_for_status()
    return risposta.json()


def aggiorna_alt_immagini_prodotto(prodotto_id: int, immagini: list[dict]) -> dict:
    """Riscrive l'ALT delle immagini indicate, ognuna `{"allegato_id": int, "alt": str}`
    (gli id si leggono con leggi_alt_immagini_prodotto). ALT vuoto = lo toglie.
    Se un allegato non e' del prodotto non si scrive niente. Restituisce ALT
    prima/dopo per ogni immagine."""
    for immagine in immagini:
        if not isinstance(immagine.get("allegato_id"), int) or not isinstance(
            immagine.get("alt"), str
        ):
            return {"errore": 'Ogni immagine va data come {"allegato_id": numero, "alt": testo}.'}
    risposta = requests.post(
        _url(),
        json={"id": prodotto_id, "immagini": immagini},
        auth=_auth(),
        verify=False,
        timeout=15,
    )
    if risposta.status_code in (400, 404):
        return {"errore": risposta.json().get("message", risposta.text)}
    risposta.raise_for_status()
    return {"stato": "aggiornato", **risposta.json()}
