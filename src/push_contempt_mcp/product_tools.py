"""Creazione prodotto WooCommerce: client sottile della REST API del plugin
push_contempt (vedi includes/Rest/ProdottiController.php) - stesso principio
di inventory_tools.py e pricing_tools.py.

Il prodotto nasce sempre in BOZZA (status=draft): la creazione non pubblica
nulla, resta da rivedere e pubblicare da wp-admin (o, su richiesta esplicita
dell'utente e con la sua conferma, con `pubblica_prodotti`). `prodotti_in_bozza` legge
quella lista (lo stato "draft" stesso e' il promemoria persistente, nessun
tracciamento a parte).
"""

import mimetypes
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from push_contempt_mcp import seo_tools, seo_varianti_tools, varianti

load_dotenv()


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def _carica_immagine(percorso: str) -> int:
    """Carica un'immagine su /wp/v2/media (endpoint nativo di WordPress,
    stesso meccanismo gia' usato da Prodotti/carica_immagini.py nella vecchia
    skill sincronizza-prodotti-woocommerce) e restituisce l'attachment ID.
    """
    site = os.environ["WP_SITE_URL"]
    file_path = Path(percorso)
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    risposta = requests.post(
        f"{site}/wp-json/wp/v2/media",
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"',
            "Content-Type": mime_type,
        },
        data=file_path.read_bytes(),
        auth=_auth(),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=30,
    )
    risposta.raise_for_status()
    return risposta.json()["id"]


def crea_prodotto(
    titolo: str,
    descrizione: str,
    prezzo_regolare: str,
    categoria: str,
    percorsi_immagini: list[str],
    alt_immagini: list[str],
    frase_chiave_focus: str,
    titolo_seo: str,
    meta_description: str,
    percorso_categoria: list[str] | None = None,
) -> dict:
    """Crea un prodotto WooCommerce in BOZZA (titolo, descrizione, prezzo,
    categoria, immagini), con SEO e ALT immagini gia' impostati: resta solo
    da rivedere e pubblicare da wp-admin o con `pubblica_prodotti` (vedi `prodotti_in_bozza`).

    `percorsi_immagini[0]` diventa l'immagine in evidenza, le altre vanno
    nella galleria. `alt_immagini` deve avere un elemento per ogni immagine
    (stesso ordine di percorsi_immagini). Il prezzo va scritto con il punto
    come decimale. La risposta include `avvisi_seo`: se non vuoto, la
    descrizione non rispetta ancora densita' della frase chiave, sottotitoli
    o link interni - da sistemare prima di pubblicare.
    """
    if len(alt_immagini) != len(percorsi_immagini):
        raise ValueError(
            f"alt_immagini ({len(alt_immagini)} elementi) deve avere la stessa "
            f"lunghezza di percorsi_immagini ({len(percorsi_immagini)} elementi): "
            "un ALT per ogni immagine, stesso ordine."
        )

    attachment_ids, errore = _carica_immagini(percorsi_immagini)
    if errore:
        return errore

    corpo = {
        "titolo": titolo,
        "descrizione": descrizione,
        "prezzo_regolare": prezzo_regolare,
        "categoria": categoria,
        **_percorso(percorso_categoria),
        "galleria_ids": attachment_ids[1:],
        "alt_immagini": dict(zip(attachment_ids, alt_immagini, strict=True)),
        "titolo_seo": titolo_seo,
        "meta_description": meta_description,
        "parola_chiave_focus": frase_chiave_focus,
    }
    if attachment_ids:
        # Senza immagini la chiave non va mandata: un null non e' un intero (400 dal plugin).
        corpo["immagine_evidenza_id"] = attachment_ids[0]

    risultato = _invia_creazione(corpo)
    if "errore" not in risultato:
        risultato["avvisi_seo"] = seo_tools.valida_contenuto_seo(descrizione, frase_chiave_focus)
    return risultato


def _percorso(percorso_categoria: list[str] | None) -> dict:
    """Il percorso di categorie (dalla radice alla categoria del prodotto) da mandare al
    plugin, oppure niente se non c'e': allora vale la categoria singola di sempre."""
    return {"percorso_categoria": list(percorso_categoria)} if percorso_categoria else {}


def verifica_categorie(percorsi: list[list[str]]) -> dict:
    """Chiede al plugin cosa farebbe con questi percorsi di categorie rispetto all'albero
    del sito: per ognuno i livelli (esiste / da_creare / conflitto) e gli errori, piu' i nomi
    che compaiono in punti diversi. Sola lettura: non crea niente."""
    risposta = requests.post(
        f"{os.environ['WP_SITE_URL']}/wp-json/push-contempt/v1/categorie/verifica",
        json={"percorsi": percorsi},
        auth=_auth(),
        verify=False,
        timeout=30,
    )
    risposta.raise_for_status()
    return risposta.json()


def _carica_immagini(percorsi: list[str]) -> tuple[list[int], dict | None]:
    """Carica le immagini e restituisce i loro id, oppure un errore leggibile."""
    try:
        return [_carica_immagine(percorso) for percorso in percorsi], None
    except FileNotFoundError as errore:
        return [], {
            "errore": f"Immagine non trovata: {errore.filename}. I percorsi vanno indicati "
            "come sono sul computer dove gira il server MCP.",
            "creato": False,
        }
    except requests.RequestException as errore:
        return [], {
            "errore": f"Caricamento di un'immagine non riuscito: {_dettaglio(errore)}",
            "creato": False,
        }


def _invia_creazione(corpo: dict) -> dict:
    """Manda la richiesta di creazione al plugin: la risposta, o un errore con il
    messaggio vero di WordPress invece di un'eccezione generica."""
    site = os.environ["WP_SITE_URL"]
    try:
        risposta = requests.post(
            f"{site}/wp-json/push-contempt/v1/prodotti",
            json=corpo,
            auth=_auth(),
            verify=False,
            timeout=60,
        )
        risposta.raise_for_status()
    except requests.RequestException as errore:
        return {
            "errore": f"Creazione del prodotto non riuscita: {_dettaglio(errore)}",
            "creato": False,
        }
    return risposta.json()


def _dettaglio(errore: requests.RequestException) -> str:
    """Stato e messaggio che manda WordPress, non solo "400 Client Error"."""
    risposta = getattr(errore, "response", None)
    if risposta is None:
        return str(errore)
    try:
        messaggio = risposta.json().get("message", risposta.text)
    except ValueError:
        messaggio = risposta.text
    return f"HTTP {risposta.status_code}: {messaggio}"


def crea_prodotto_variabile(
    titolo: str,
    descrizione: str,
    prezzo_regolare: str,
    categoria: str,
    percorsi_immagini: list[str],
    alt_immagini: list[str],
    frase_chiave_focus: str,
    titolo_seo: str,
    meta_description: str,
    attributi: dict[str, list[str]] | None = None,
    riga_varianti: str | None = None,
    anteprima: bool = True,
    percorso_categoria: list[str] | None = None,
) -> dict:
    """Crea un prodotto WooCommerce VARIABILE in bozza, con una variante per ogni
    combinazione dei valori degli attributi, tutte allo stesso `prezzo_regolare`
    e senza gestione scorte. Gli attributi arrivano in uno di due modi (esattamente
    uno): `riga_varianti`, la riga del file di testo letta cosi' com'e', oppure
    `attributi`, un dizionario nome -> valori ricavato dall'assistente.

    Con `anteprima=True` (predefinito) NON si scrive niente, nemmeno immagini o
    categoria: si restituisce l'elenco delle varianti che nascerebbero. Con
    `anteprima=False` si crea davvero.
    """
    if (attributi is None) == (riga_varianti is None):
        return {
            "errore": "Indica gli attributi in uno solo dei due modi: "
            "`attributi` oppure `riga_varianti`.",
            "creato": False,
        }
    if len(alt_immagini) != len(percorsi_immagini):
        return {
            "errore": f"alt_immagini ({len(alt_immagini)} elementi) deve avere la stessa lunghezza "
            f"di percorsi_immagini ({len(percorsi_immagini)} elementi).",
            "creato": False,
        }

    if riga_varianti is not None:
        letti = varianti.analizza_riga_varianti(riga_varianti)
        if letti["errori"]:
            return {
                "errore": "La riga delle varianti non e' scritta nel formato previsto: "
                + " ".join(letti["errori"]),
                "formato": "varianti: Colore: Nero, Bianco | Memoria: 256 GB, 512 GB",
                "creato": False,
            }
        elenco = letti["attributi"]
        modalita = "riga"
    else:
        elenco = [{"nome": nome, "valori": valori} for nome, valori in attributi.items()]
        modalita = "attributi"

    corpo = {
        "tipo": "variable",
        "titolo": titolo,
        "descrizione": descrizione,
        "prezzo_regolare": prezzo_regolare,
        "categoria": categoria,
        "attributi": elenco,
        **_percorso(percorso_categoria),
        "titolo_seo": titolo_seo,
        "meta_description": meta_description,
        "parola_chiave_focus": frase_chiave_focus,
    }

    if anteprima:
        mancanti = [percorso for percorso in percorsi_immagini if not Path(percorso).is_file()]
        if mancanti:
            return {
                "errore": f"Immagine non trovata: {mancanti[0]}. I percorsi vanno indicati "
                "come sono sul computer dove gira il server MCP.",
                "creato": False,
            }
        risultato = _invia_creazione({**corpo, "solo_anteprima": True})
        if "errore" not in risultato:
            risultato["modalita"] = modalita
            risultato["immagini"] = len(percorsi_immagini)
            risultato["avvisi_seo"] = seo_tools.valida_contenuto_seo(
                descrizione, frase_chiave_focus
            ) + seo_varianti_tools.valida_testi_variabile(
                descrizione, titolo_seo, frase_chiave_focus, elenco
            )
            risultato["prossimo_passo"] = (
                "Nessun prodotto creato. Mostra all'utente queste varianti. "
                "Se le hai ricavate tu dal testo, aspetta il suo ok; "
                "poi richiama con anteprima=False."
            )
        return risultato

    attachment_ids, errore = _carica_immagini(percorsi_immagini)
    if errore:
        return errore
    corpo["galleria_ids"] = attachment_ids[1:]
    corpo["alt_immagini"] = dict(zip(attachment_ids, alt_immagini, strict=True))
    if attachment_ids:
        corpo["immagine_evidenza_id"] = attachment_ids[0]
    risultato = _invia_creazione(corpo)
    if "errore" not in risultato:
        risultato["avvisi_seo"] = seo_tools.valida_contenuto_seo(
            descrizione, frase_chiave_focus
        ) + seo_varianti_tools.valida_testi_variabile(
            descrizione, titolo_seo, frase_chiave_focus, elenco
        )
    return risultato


def prodotti_in_bozza() -> list[dict]:
    """Prodotti creati in bozza, in attesa di revisione/pubblicazione da
    wp-admin (piu' recenti prima)."""
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/prodotti/bozze",
        auth=_auth(),
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()


def elenco_prodotti(ricerca: str = "", limite: int = 20) -> list[dict]:
    """Catalogo WooCommerce (titolo, sku, prezzo, scorte) via la REST API del
    plugin push_contempt (vedi includes/Rest/ProdottiController.php),
    cosi' funziona anche dove il DB non e' raggiungibile dall'esterno
    (hosting condiviso di un cliente, es. Altervista).

    `ricerca` filtra per titolo (sottostringa, case-insensitive); vuoto =
    tutti. `limite` negativo = nessun limite.
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/prodotti",
        params={"ricerca": ricerca, "limite": limite},
        auth=_auth(),
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()
