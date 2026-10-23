"""Lettura/scrittura dei campi SEO di Yoast sui prodotti WooCommerce: client
sottile della REST API del plugin push_contempt (vedi
includes/Rest/SeoStatoController.php e SeoProdottoController.php) - stesso
principio di inventory_tools.py e pricing_tools.py.

Solo I/O qui: non c'e' nessuna logica di "cosa scrivere" (lunghezza ideale,
keyword density, ecc.) - quella la fa l'AI che chiama questi tool,
ragionando sui dati del prodotto.
"""

import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()


def _auth() -> tuple[str, str]:
    return (os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"])


def lista_stato_seo_prodotti() -> list[dict]:
    """Vista d'insieme: per ogni prodotto pubblicato o in bozza, titolo SEO/meta
    description impostati o mancanti, le loro lunghezze, stato e data di
    creazione (utile per capire dove intervenire, e per distinguere i
    prodotti appena inseriti da quelli del catalogo consolidato).
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/seo/stato",
        auth=_auth(),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()


def leggi_seo_prodotto(prodotto_id: int) -> dict:
    """Stato SEO dettagliato di un prodotto, più titolo/descrizione/prezzo come
    contesto per chi deve scrivere i nuovi testi."""
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/seo/prodotto",
        params={"id": prodotto_id},
        auth=_auth(),
        verify=False,
        timeout=10,
    )
    if risposta.status_code == 404:
        return {"errore": f"Nessun prodotto con id {prodotto_id}"}
    risposta.raise_for_status()
    return risposta.json()


def leggi_seo_prodotti_selezionati(prodotto_ids: list[int]) -> list[dict]:
    """Stato SEO di una selezione di prodotti in un'unica chiamata (stesso
    contenuto di leggi_seo_prodotto, per ciascun id).

    Pensato per il bottone "ottimizza SEO" del plugin: l'utente seleziona i
    prodotti su cui intervenire (anche caricati prima del plugin, non c'e'
    alcun legame con la creazione), e si evita una chiamata per prodotto.
    """
    return [leggi_seo_prodotto(pid) for pid in prodotto_ids]


def aggiorna_seo_prodotto(
    prodotto_id: int,
    titolo_seo: str,
    meta_description: str,
    parola_chiave_focus: str,
    origine: str = "",
) -> dict:
    """Scrive titolo SEO, meta description e parola chiave focus di un prodotto.

    Sovrascrive i valori esistenti. Restituisce il prima/dopo per poterlo
    controllare: l'effetto e' pubblico (quello che Google mostra in SERP).
    Il plugin conserva i valori precedenti alla prima modifica (si tornano a
    mettere con ripristina_seo_prodotti); `origine` dice chi ha scritto e
    compare nella tab SEO accanto al valore conservato.
    """
    prima = leggi_seo_prodotto(prodotto_id)
    if "errore" in prima:
        return prima

    site = os.environ["WP_SITE_URL"]
    corpo = {
        "id": prodotto_id,
        "titolo_seo": titolo_seo,
        "meta_description": meta_description,
        "parola_chiave_focus": parola_chiave_focus,
    }
    if origine:
        corpo["origine"] = origine
    risposta = requests.post(
        f"{site}/wp-json/push-contempt/v1/seo/prodotto",
        json=corpo,
        auth=_auth(),
        verify=False,
        timeout=10,
    )
    risposta.raise_for_status()
    dopo = risposta.json()

    return {
        "stato": "aggiornato",
        "prodotto_id": prodotto_id,
        "prima": {
            "titolo_seo": prima["titolo_seo"],
            "meta_description": prima["meta_description"],
            "parola_chiave_focus": prima["parola_chiave_focus"],
        },
        "dopo": dopo,
    }


def ripristina_seo_prodotti(prodotto_ids: list[int]) -> dict:
    """Rimette titolo SEO, meta description e parola chiave focus come erano
    prima del primo intervento (valori conservati dal plugin). Restituisce per
    ogni id l'esito: "ripristinato", "nessuno_snapshot" (mai modificato, non
    toccato) o "non_trovato"."""
    site = os.environ["WP_SITE_URL"]
    risposta = requests.post(
        f"{site}/wp-json/push-contempt/v1/seo/ripristina",
        json={"ids": prodotto_ids},
        auth=_auth(),
        verify=False,
        timeout=30,
    )
    risposta.raise_for_status()
    return risposta.json()


def valida_contenuto_seo(descrizione: str, parola_chiave_focus: str) -> list[str]:
    """Controlli on-page sugli stessi criteri usati da Yoast: densita' della
    frase chiave, presenza nei sottotitoli H2/H3, presenza di almeno un link
    interno. Solo lettura: non modifica nulla, restituisce gli avvisi da
    correggere (lista vuota se tutto ok).
    """
    avvisi = []
    testo = descrizione.lower()
    frase = parola_chiave_focus.lower().strip()

    occorrenze = testo.count(frase) if frase else 0
    if occorrenze < 2:
        avvisi.append(
            f"Frase chiave '{parola_chiave_focus}' presente solo {occorrenze} volta/e nel "
            "testo: aggiungine almeno un'altra menzione naturale (minimo 2 per Yoast)."
        )

    sottotitoli = re.findall(r"<h[23][^>]*>(.*?)</h[23]>", descrizione, re.IGNORECASE | re.DOTALL)
    if frase and not any(frase in s.lower() for s in sottotitoli):
        avvisi.append(
            f"Nessun sottotitolo H2/H3 contiene la frase chiave '{parola_chiave_focus}': "
            "aggiungila in almeno un H2/H3 (es. '<Frase Chiave>: scheda tecnica completa')."
        )

    if "<a href=" not in testo:
        avvisi.append(
            "Nessun link interno nella descrizione: aggiungi almeno un link a un prodotto "
            "correlato o alla pagina categoria (es. /prodotto/<slug>/ o "
            "/categoria-prodotto/<slug>/)."
        )

    return avvisi
