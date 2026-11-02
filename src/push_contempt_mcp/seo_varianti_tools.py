"""SEO delle varianti di un prodotto variabile: client sottile della REST API
del plugin push_contempt (vedi includes/Rest/SeoVariantiController.php), stesso
schema di alt_tools.py, piu' il controllo dei testi di un variabile.

Solo I/O e controlli: cosa scrivere nelle descrizioni lo decide chi chiama il
tool. Una variante non ha un indirizzo suo: la pagina che si posiziona e' quella
del padre, quindi i testi delle varianti servono alla pagina e ai dati
strutturati (che il plugin genera da solo, senza tool).
"""

import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def _url() -> str:
    return f"{os.environ['WP_SITE_URL']}/wp-json/push-contempt/v1/seo/varianti"


def _messaggio(risposta: requests.Response) -> str:
    try:
        return risposta.json().get("message", risposta.text)
    except ValueError:
        return risposta.text


def leggi_seo_varianti(prodotto_id: int) -> dict:
    """Attributi e varianti di un prodotto variabile (prezzo, SKU, immagine,
    descrizione) con i problemi SEO trovati dal plugin."""
    risposta = requests.get(
        _url(),
        params={"id": prodotto_id},
        auth=_auth(),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=15,
    )
    if risposta.status_code in (400, 404):
        return {"errore": _messaggio(risposta)}
    risposta.raise_for_status()
    return risposta.json()


def aggiorna_seo_varianti(
    prodotto_id: int, varianti: list[dict], solo_anteprima: bool = False
) -> dict:
    """Riscrive descrizione e/o SKU delle varianti indicate, ognuna
    `{"id": int, "descrizione": str, "sku": str}` (descrizione e sku sono
    facoltativi; gli id vengono da leggi_seo_varianti). Se una variante non e'
    del prodotto o uno SKU e' gia' in uso non si scrive niente. Restituisce
    prima/dopo per ogni campo cambiato."""
    for variante in varianti:
        if not isinstance(variante.get("id"), int):
            return {"errore": 'Ogni variante va data come {"id": numero, "descrizione": testo}.'}
        if "descrizione" not in variante and "sku" not in variante:
            return {
                "errore": f"La variante {variante['id']} non ha niente da scrivere: "
                "servono `descrizione` e/o `sku`."
            }
        for campo in ("descrizione", "sku"):
            if campo in variante and not isinstance(variante[campo], str):
                return {
                    "errore": f"`{campo}` della variante {variante['id']} deve essere un testo."
                }
    risposta = requests.post(
        _url(),
        json={"id": prodotto_id, "varianti": varianti, "solo_anteprima": solo_anteprima},
        auth=_auth(),
        verify=False,
        timeout=30,
    )
    if risposta.status_code in (400, 404, 409):
        return {"errore": _messaggio(risposta)}
    risposta.raise_for_status()
    return {"stato": "anteprima" if solo_anteprima else "aggiornato", **risposta.json()}


def _contiene_parola(testo: str, valore: str) -> bool:
    """Il valore come parola intera ("L" non e' in "felpa"), senza badare alle maiuscole."""
    return (
        re.search(r"(?<![\w])" + re.escape(valore.strip()) + r"(?![\w])", testo, re.IGNORECASE)
        is not None
    )


def valida_testi_variabile(
    descrizione: str,
    titolo_seo: str,
    frase_chiave_focus: str,
    attributi: list[dict],
) -> list[str]:
    """Avvisi sui testi di un variabile prima di crearlo: gli stessi due
    problemi che il plugin segnala poi sul prodotto vivo (valori che nella
    descrizione non compaiono; titolo SEO o parola chiave che citano una sola
    variante). `attributi` e' `[{"nome": "Colore", "valori": ["Nero", "Bianco"]}]`.
    Lista vuota se va tutto bene."""
    avvisi: list[str] = []
    testo = re.sub(r"<[^>]+>", " ", descrizione)

    mancano = [
        f"{a['nome']}: {valore}"
        for a in attributi
        for valore in a["valori"]
        if valore.strip() and not _contiene_parola(testo, valore)
    ]
    if mancano:
        avvisi.append(
            "Valori delle varianti che nella descrizione non compaiono ("
            + "; ".join(mancano)
            + "): chi li cerca non trova parole corrispondenti. Citali nel testo, in modo naturale."
        )

    for nome_campo, campo in (
        ("Il titolo SEO", titolo_seo),
        ("La parola chiave focus", frase_chiave_focus),
    ):
        citati = [
            valore.strip().lower()
            for a in attributi
            if len(a["valori"]) > 1
            for valore in a["valori"]
            if valore.strip() and _contiene_parola(campo, valore)
        ]
        if citati:
            avvisi.append(
                f"{nome_campo} cita solo una variante ({', '.join(citati)}): la pagina e' una sola "
                "per tutte le varianti, quel testo la farebbe sembrare solo quella."
            )
    return avvisi
