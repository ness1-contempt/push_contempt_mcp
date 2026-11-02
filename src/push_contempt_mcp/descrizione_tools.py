"""Lettura/scrittura della descrizione dei prodotti WooCommerce: client sottile
della REST API del plugin push_contempt (vedi
includes/Rest/DescrizioneProdottoController.php), stesso schema di seo_tools.py.

Solo I/O: il testo lo scrive chi chiama il tool. Il plugin tiene per ogni
prodotto la base (stato prima del primo intervento) e il precedente, e passa
l'HTML da wp_kses_post.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

CAMPI = ("descrizione", "descrizione_breve")


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def _url(percorso: str) -> str:
    return f"{os.environ['WP_SITE_URL']}/wp-json/push-contempt/v1/{percorso}"


def leggi_descrizione_prodotto(prodotto_id: int) -> dict:
    """Descrizione lunga e breve attuali, con le versioni conservate dal plugin."""
    risposta = requests.get(
        _url("descrizione/prodotto"),
        params={"id": prodotto_id},
        auth=_auth(),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=10,
    )
    if risposta.status_code == 404:
        return {"errore": f"Nessun prodotto con id {prodotto_id}"}
    risposta.raise_for_status()
    return risposta.json()


def aggiorna_descrizione_prodotto(
    prodotto_id: int,
    descrizione_html: str,
    descrizione_breve: str | None = None,
    origine: str = "",
) -> dict:
    """Scrive la descrizione (e, se data, quella breve) di un prodotto.

    Sovrascrive i valori esistenti; `descrizione_breve` assente = quella breve
    resta com'e'. Restituisce il prima/dopo: l'effetto e' pubblico. Il plugin
    tiene base e precedente, si tornano a mettere con ripristina_descrizione_prodotti.
    """
    prima = leggi_descrizione_prodotto(prodotto_id)
    if "errore" in prima:
        return prima

    corpo = {"id": prodotto_id, "descrizione": descrizione_html}
    if descrizione_breve is not None:
        corpo["descrizione_breve"] = descrizione_breve
    if origine:
        corpo["origine"] = origine
    risposta = requests.post(
        _url("descrizione/prodotto"),
        json=corpo,
        auth=_auth(),
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()

    return {
        "stato": "aggiornato",
        "prodotto_id": prodotto_id,
        "prima": {campo: prima[campo] for campo in CAMPI},
        "dopo": risposta.json(),
    }


def ripristina_descrizione_prodotti(prodotto_ids: list[int], versione: str = "base") -> dict:
    """Rimette descrizione e descrizione breve come nella versione scelta fra
    quelle conservate dal plugin: "base" o "precedente". La versione che si
    lascia diventa il "precedente". Restituisce per ogni id l'esito:
    "ripristinato", "gia_in_uso", "nessuno_snapshot" (mai modificata via plugin,
    non toccata) o "non_trovato"."""
    if versione not in ("base", "precedente"):
        return {"errore": 'La versione va scelta fra "base" e "precedente".'}
    risposta = requests.post(
        _url("descrizione/ripristina"),
        json={"ids": prodotto_ids, "versione": versione},
        auth=_auth(),
        verify=False,
        timeout=30,
    )
    risposta.raise_for_status()
    return risposta.json()
