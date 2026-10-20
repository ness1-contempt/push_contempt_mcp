"""Aggiornamento prezzi in blocco: client sottile della REST API del plugin
push_contempt (vedi includes/Rest/PrezziController.php) - stesso principio
di inventory_tools.py.

A differenza della vecchia versione a SQL diretto, qui la scrittura passa
dall'API nativa di WooCommerce (set_regular_price()->save()) lato plugin:
niente piu' bisogno di replicare a mano _price/sconto attivo o la lookup
table, e la cache del sito si invalida da sola tramite i hook di WooCommerce
(verificato: non serve piu' la purge manuale per i cambi di prezzo).
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def calcola_aggiornamento_prezzi(
    categoria: str, percentuale: float | None = None, delta: float | None = None
) -> dict:
    """Prodotti semplici di una categoria (slug) con prezzo attuale e quello
    calcolato (percentuale, es. 10/-15, oppure delta fisso in valuta,
    es. -5: specificarne solo uno). Solo lettura - da far rivedere
    all'utente prima di chiamare applica_aggiornamento_prezzi. I prodotti
    variabili della categoria sono elencati a parte, esclusi dal calcolo.
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/prezzi/calcola",
        params={"categoria": categoria, "percentuale": percentuale, "delta": delta},
        auth=_auth(),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()


def applica_aggiornamento_prezzi(aggiornamenti: list[dict]) -> dict:
    """Scrive i nuovi prezzi (lista approvata, stessa forma dell'output di
    calcola_aggiornamento_prezzi: ogni elemento serve `id` e
    `prezzo_regolare_nuovo`).
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.post(
        f"{site}/wp-json/push-contempt/v1/prezzi/applica",
        json={"aggiornamenti": aggiornamenti},
        auth=_auth(),
        verify=False,
        timeout=30,
    )
    risposta.raise_for_status()
    return risposta.json()
