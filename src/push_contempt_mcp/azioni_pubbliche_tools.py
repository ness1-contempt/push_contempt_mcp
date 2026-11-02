"""Azioni che cambiano il sito in modo visibile a tutti - pubblicare bozze di
prodotti e spostare una categoria sotto un'altra: client sottile della REST API
del plugin push_contempt (vedi includes/Rest/PubblicaProdottiController.php e
CategorieController.php).

Si fanno sempre in due tempi. L'anteprima (predefinita) non cambia niente, dice
cosa succederebbe e restituisce un `codice_conferma` legato allo stato esatto
che l'utente vede. L'azione vera si accetta solo con quel codice, e il plugin la
rifiuta se nel frattempo qualcosa e' cambiato. Il codice garantisce che si agisca
su cio' che e' stato mostrato; che l'utente abbia detto si lo deve far rispettare
l'assistente (vedi le istruzioni del server).
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_PASSO_PUBBLICA = (
    "Nessun prodotto e' stato pubblicato. Mostra all'utente l'elenco `da_pubblicare` con gli "
    "`avvisi` di ciascuno e i `non_pubblicabili` con i motivi, poi chiedigli esplicitamente se "
    "vuole pubblicare QUESTI prodotti e aspetta il suo si. Solo dopo richiama con "
    "anteprima=False e il `codice_conferma` di questa risposta."
)
_PASSO_SPOSTA = (
    "Nessuna categoria e' stata spostata. Mostra all'utente `percorso_prima` e `percorso_dopo`, "
    "gli indirizzi (`url_prima` e `url_dopo`), le `sottocategorie`, i `prodotti_nel_ramo` e gli "
    "`avvisi`, poi chiedigli esplicitamente se vuole spostarla e aspetta il suo si. Solo dopo "
    "richiama con anteprima=False e il `codice_conferma` di questa risposta."
)


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def _url(percorso: str) -> str:
    return f"{os.environ['WP_SITE_URL']}/wp-json/push-contempt/v1/{percorso}"


def _messaggio(risposta: requests.Response) -> str:
    try:
        return risposta.json().get("message", risposta.text)
    except ValueError:
        return risposta.text


def _manca_il_codice(anteprima: bool, codice_conferma: str | None) -> dict | None:
    """Errore se si chiede l'azione vera senza il codice dell'anteprima."""
    if not anteprima and not codice_conferma:
        return {
            "errore": "Per agire davvero serve il `codice_conferma` dell'anteprima: fai prima "
            "l'anteprima (anteprima=True), falla vedere all'utente e aspetta il suo si.",
        }
    return None


def lista_categorie_prodotti() -> list[dict] | dict:
    """Le categorie prodotto con id, percorso, livello, numero di prodotti
    (pubblicati) e indirizzo, ordinate per percorso."""
    risposta = requests.get(_url("categorie"), auth=_auth(), verify=False, timeout=15)
    risposta.raise_for_status()
    return risposta.json()


def sposta_categoria_prodotti(
    categoria_id: int,
    nuova_madre_id: int,
    anteprima: bool = True,
    codice_conferma: str | None = None,
) -> dict:
    """Sposta una categoria (con le sue sottocategorie) sotto un'altra, o alla
    radice con `nuova_madre_id=0`. Anteprima di default: non sposta niente."""
    if errore := _manca_il_codice(anteprima, codice_conferma):
        return errore
    corpo = {
        "id": categoria_id,
        "nuova_madre": nuova_madre_id,
        "solo_anteprima": anteprima,
        "codice_conferma": codice_conferma or "",
    }
    risposta = requests.post(
        _url("categorie/sposta"), json=corpo, auth=_auth(), verify=False, timeout=30
    )
    if risposta.status_code in (400, 404, 409, 500):
        return {"errore": _messaggio(risposta)}
    risposta.raise_for_status()
    dati = risposta.json()
    if anteprima:
        dati["prossimo_passo"] = _PASSO_SPOSTA
    return dati


def pubblica_prodotti(
    prodotto_ids: list[int],
    anteprima: bool = True,
    codice_conferma: str | None = None,
) -> dict:
    """Pubblica bozze di prodotti. Anteprima di default: non pubblica niente."""
    if not prodotto_ids or not all(isinstance(i, int) for i in prodotto_ids):
        return {"errore": "Indica gli id dei prodotti come elenco di numeri."}
    if errore := _manca_il_codice(anteprima, codice_conferma):
        return errore
    corpo = {
        "ids": prodotto_ids,
        "solo_anteprima": anteprima,
        "codice_conferma": codice_conferma or "",
    }
    risposta = requests.post(
        _url("prodotti/pubblica"), json=corpo, auth=_auth(), verify=False, timeout=60
    )
    if risposta.status_code in (400, 409):
        return {"errore": _messaggio(risposta)}
    risposta.raise_for_status()
    dati = risposta.json()
    if anteprima:
        dati["prossimo_passo"] = (
            _PASSO_PUBBLICA
            if dati.get("codice_conferma")
            else "Nessuno dei prodotti indicati e' pubblicabile: riporta all'utente i motivi."
        )
    return dati
