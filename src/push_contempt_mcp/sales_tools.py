"""Report vendite per prodotto: client sottile della REST API del plugin
push_contempt (vedi includes/Rest/VenditeController.php) - stesso principio
di inventory_tools.py: la logica vive nel plugin PHP, non qui.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def report_vendite_prodotti(periodo: str = "1_mese") -> dict:
    """Report vendite per prodotto in uno dei periodi predefiniti
    (1_mese/3_mesi/6_mesi/1_anno), via la REST API del plugin push_contempt:
    più venduti con quantità e ricavo netto, più i prodotti pubblicati mai
    venduti (su tutta la storia del negozio).
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/vendite",
        params={"periodo": periodo},
        auth=(os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"]),
        # Certificato self-signed in locale, vedi inventory_tools.py.
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()
