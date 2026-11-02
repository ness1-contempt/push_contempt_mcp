"""Link della descrizione di un prodotto: client sottile della REST API del
plugin push_contempt (vedi includes/Rest/LinkProdottoController.php), stesso
schema di seo_tools.py. Sola lettura: il plugin conosce il dominio del sito e
divide i link in interni, esterni e altri.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def analizza_link_prodotto(prodotto_id: int) -> dict:
    """Link della descrizione lunga di un prodotto, divisi in interni (stesso
    dominio del sito o relativi), esterni (altro dominio) e altri (ancore,
    mailto, tel), con i totali e `ha_link_in_uscita`."""
    risposta = requests.get(
        f"{os.environ['WP_SITE_URL']}/wp-json/push-contempt/v1/link/prodotto",
        params={"id": prodotto_id},
        auth=(os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"]),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=10,
    )
    if risposta.status_code in (404, 501):
        return {"errore": risposta.json().get("message", risposta.text)}
    risposta.raise_for_status()
    return risposta.json()
