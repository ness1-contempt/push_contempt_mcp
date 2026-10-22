"""Consultazione ordini WooCommerce: client sottile della REST API del
plugin push_contempt (vedi includes/Rest/OrdiniController.php). Sola lettura.

Stessa impostazione di sales_tools.py/inventory_tools.py: filtri, stati e
formato dei dati vivono nel plugin PHP, qui si chiama solo l'endpoint.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def _get(percorso: str, params: dict | None = None) -> dict:
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/{percorso}",
        params=params,
        auth=(os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"]),
        # Certificato self-signed in locale, vedi inventory_tools.py.
        verify=False,
        timeout=15,
    )
    # Su 400/404 il plugin spiega il motivo (es. l'elenco degli stati validi):
    # lo si propaga com'e', non il generico "400 Client Error".
    if risposta.status_code in (400, 404):
        raise ValueError(risposta.json().get("message", risposta.text))
    risposta.raise_for_status()
    return risposta.json()


def lista_ordini(
    stato: str = "",
    ultime_ore: int | None = None,
    piu_vecchi_di_ore: int | None = None,
    da: str | None = None,
    a: str | None = None,
    ordina: str = "desc",
    limite: int = 50,
) -> dict:
    """Elenco ordini WooCommerce, filtrabile per stato e finestra temporale.

    `stato`: uno o piu' stati WooCommerce separati da virgola, con lo slug
    nativo (non esiste uno stato "evaso"): pending (in attesa di pagamento),
    processing (in lavorazione), on-hold (in sospeso), completed
    (completato), cancelled, refunded, failed. Vuoto = tutti gli stati.
    `ultime_ore`: solo ordini creati nelle ultime N ore (24 = ultima giornata).
    `piu_vecchi_di_ore`: solo ordini creati da piu' di N ore.
    `da`/`a`: estremi (YYYY-MM-DD o YYYY-MM-DDTHH:MM, fuso del sito); `a` con la
    sola data include tutta la giornata. I filtri di data si combinano
    (intersezione). `ordina`: "desc" (piu' recenti prima) o "asc".

    Restituisce totale_trovati (anche oltre `limite`, massimo 200) e, per ogni
    ordine, numero, stato, data, totale, pagamento, citta' e prodotti: nessun
    dato personale oltre alla citta'. Per i dettagli di un ordine usa
    dettaglio_ordine.
    """
    return _get(
        "ordini",
        {
            "stato": stato,
            "ultime_ore": ultime_ore,
            "piu_vecchi_di_ore": piu_vecchi_di_ore,
            "da": da,
            "a": a,
            "ordina": ordina,
            "limite": limite,
        },
    )


def dettaglio_ordine(ordine_id: int) -> dict:
    """Dettaglio completo di un ordine: righe con id prodotto, importi (subtotale,
    sconto, spedizione, tasse), date di pagamento e completamento, metodo di
    spedizione, nota del cliente e DATI PERSONALI del cliente (nome, email,
    telefono, indirizzi). Usalo solo quando serve davvero.
    """
    return _get(f"ordini/{int(ordine_id)}")
