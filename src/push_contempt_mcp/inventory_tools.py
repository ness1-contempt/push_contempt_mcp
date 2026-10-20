"""Alert scorte: client sottile della REST API del plugin push_contempt.

La logica (soglia, cosa conta come "esaurito", gestione scorte attiva o
no) vive nel plugin PHP (push_contempt/includes/Rest/ScorteController.php),
che usa l'API nativa di WooCommerce e il DB di WordPress senza bisogno di
raggiungibilita' esterna del DB. Questo modulo si limita a chiamare quella
REST API via Application Password - niente logica di business qui, per
evitare di mantenerla due volte in due linguaggi.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def prodotti_sotto_scorta(soglia: float = 5) -> list[dict]:
    """Prodotti pubblicati esauriti o con scorte sotto `soglia` (solo quelli
    con gestione scorte attiva in WooCommerce), via la REST API del plugin
    push_contempt. Esauriti per primi, poi per scorte crescenti.
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/scorte",
        params={"soglia": soglia},
        auth=(os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"]),
        # Certificato self-signed in locale (stesso motivo di
        # ignore_https_errors in browser_tools.py) - NON disattivare la
        # verifica contro un sito di produzione reale.
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()
