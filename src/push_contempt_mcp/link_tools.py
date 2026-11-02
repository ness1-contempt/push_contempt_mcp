"""Link della descrizione di un prodotto: client sottile della REST API del
plugin push_contempt (vedi includes/Rest/LinkProdottoController.php), stesso
schema di seo_tools.py. Sola lettura: il plugin conosce il dominio del sito e
divide i link in interni, esterni e altri.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()


def _get(percorso: str, params: dict) -> requests.Response:
    return requests.get(
        f"{os.environ['WP_SITE_URL']}/wp-json/push-contempt/v1/{percorso}",
        params=params,
        auth=(os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"]),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=60,
    )


def analizza_link_prodotti(stato: str = "publish", solo_senza_link_in_uscita: bool = False) -> dict:
    """Riepilogo dei link di tutti i prodotti in un'unica chiamata: per ciascuno
    i totali (interni, esterni, ha_link_in_uscita), non gli indirizzi. In testa
    quanti prodotti sono stati analizzati, quanti senza link in uscita e quanti
    senza link interni. `stato`: publish, draft o any."""
    if stato not in ("publish", "draft", "any"):
        return {"errore": 'Lo stato va scelto fra "publish", "draft" e "any".'}
    risposta = _get(
        "link/prodotti",
        # requests manderebbe "True"/"False", che il plugin non legge come booleano.
        {
            "stato": stato,
            "solo_senza_link_in_uscita": "true" if solo_senza_link_in_uscita else "false",
        },
    )
    if risposta.status_code == 501:
        return {"errore": risposta.json().get("message", risposta.text)}
    risposta.raise_for_status()
    return risposta.json()


def analizza_link_prodotto(prodotto_id: int) -> dict:
    """Link della descrizione lunga di un prodotto, divisi in interni (stesso
    dominio del sito o relativi), esterni (altro dominio) e altri (ancore,
    mailto, tel), con i totali e `ha_link_in_uscita`."""
    risposta = _get("link/prodotto", {"id": prodotto_id})
    if risposta.status_code in (404, 501):
        return {"errore": risposta.json().get("message", risposta.text)}
    risposta.raise_for_status()
    return risposta.json()
