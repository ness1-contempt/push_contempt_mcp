"""Controllo salute catalogo: client sottile della REST API del plugin
push_contempt (vedi includes/Rest/SaluteCatalogoController.php e
includes/CatalogHealth.php) - stesso principio di inventory_tools.py.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def controllo_salute_catalogo(soglia_descrizione: int = 50) -> list[dict]:
    """Prodotti pubblicati con almeno un problema tra: nessuna immagine in
    evidenza, nessuna categoria, prezzo mancante/zero/non valido (solo
    prodotti semplici), descrizione più corta di `soglia_descrizione`
    caratteri (tag HTML esclusi dal conteggio), via la REST API del plugin
    push_contempt.
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/salute-catalogo",
        params={"soglia_descrizione": soglia_descrizione},
        auth=(os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"]),
        # Certificato self-signed in locale, vedi inventory_tools.py.
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()
