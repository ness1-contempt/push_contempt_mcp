"""Lettura/scrittura dei campi SEO di Yoast sui prodotti WooCommerce.

Solo I/O: qui non c'e' nessuna logica di "cosa scrivere" (lunghezza ideale,
keyword density, ecc.) - quella la fa l'AI che chiama questi tool,
ragionando sui dati del prodotto. Scrittura diretta sul DB: i campi Yoast
sono testo semplice senza effetti collaterali/trigger, a differenza del
prezzo che passa dal browser.
"""

import os
import re

import requests
from dotenv import load_dotenv

from push_contempt_mcp.db import TABLE_PREFIX, get_connection

load_dotenv()

CAMPI_YOAST = {
    "titolo_seo": "_yoast_wpseo_title",
    "meta_description": "_yoast_wpseo_metadesc",
    "parola_chiave_focus": "_yoast_wpseo_focuskw",
}


def lista_stato_seo_prodotti() -> list[dict]:
    """Vista d'insieme: per ogni prodotto pubblicato, titolo SEO/meta description
    impostati o mancanti, e le loro lunghezze (utile per capire dove intervenire).

    Client sottile della REST API del plugin push_contempt (vedi
    includes/Rest/SeoStatoController.php) - stesso principio di
    inventory_tools.py. A differenza delle altre funzioni di questo modulo
    (lettura/scrittura di un singolo prodotto, usate dal flusso AI di
    ottimizzazione SEO), questa e' solo lettura aggregata, niente AI.
    """
    site = os.environ["WP_SITE_URL"]
    risposta = requests.get(
        f"{site}/wp-json/push-contempt/v1/seo/stato",
        auth=(os.environ["WP_APP_USER"], os.environ["WP_APP_PASSWORD"]),
        verify=False,  # certificato self-signed in locale, vedi inventory_tools.py
        timeout=10,
    )
    risposta.raise_for_status()
    return risposta.json()


def leggi_seo_prodotto(prodotto_id: int) -> dict:
    """Stato SEO dettagliato di un prodotto, più titolo/descrizione/prezzo come
    contesto per chi deve scrivere i nuovi testi."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                p.ID AS id, p.post_title AS titolo, p.post_content AS descrizione,
                MAX(CASE WHEN pm.meta_key = '_price' THEN pm.meta_value END) AS prezzo,
                MAX(CASE WHEN pm.meta_key = '_yoast_wpseo_title' THEN pm.meta_value END)
                    AS titolo_seo,
                MAX(CASE WHEN pm.meta_key = '_yoast_wpseo_metadesc' THEN pm.meta_value END)
                    AS meta_description,
                MAX(CASE WHEN pm.meta_key = '_yoast_wpseo_focuskw' THEN pm.meta_value END)
                    AS parola_chiave_focus
            FROM {TABLE_PREFIX}posts p
            LEFT JOIN {TABLE_PREFIX}postmeta pm ON pm.post_id = p.ID
            WHERE p.ID = %s
            GROUP BY p.ID
            """,
            (prodotto_id,),
        )
        riga = cursor.fetchone()

    if riga is None:
        return {"errore": f"Nessun prodotto con id {prodotto_id}"}
    return riga


def leggi_seo_prodotti_selezionati(prodotto_ids: list[int]) -> list[dict]:
    """Stato SEO di una selezione di prodotti in un'unica chiamata (stesso
    contenuto di leggi_seo_prodotto, per ciascun id).

    Pensato per il bottone "ottimizza SEO" del plugin: l'utente seleziona i
    prodotti su cui intervenire (anche caricati prima del plugin, non c'e'
    alcun legame con la creazione), e si evita una chiamata per prodotto.
    """
    return [leggi_seo_prodotto(pid) for pid in prodotto_ids]


def scrivi_campi_yoast(
    prodotto_id: int,
    titolo_seo: str,
    meta_description: str,
    parola_chiave_focus: str,
) -> dict:
    """Scrive titolo SEO, meta description e parola chiave focus di un prodotto
    (sovrascrive i valori esistenti). DB diretto, nessun effetto collaterale.

    Condivisa tra `aggiorna_seo_prodotto` (prodotto gia' pubblicato) e la
    creazione di un nuovo prodotto in browser_tools.py, cosi' un prodotto
    nuovo nasce gia' con la SEO impostata invece di richiedere un secondo
    passo separato.
    """
    nuovi_valori = {
        "titolo_seo": titolo_seo,
        "meta_description": meta_description,
        "parola_chiave_focus": parola_chiave_focus,
    }

    with get_connection() as conn, conn.cursor() as cursor:
        for campo, meta_key in CAMPI_YOAST.items():
            cursor.execute(
                "DELETE FROM wp_postmeta WHERE post_id = %s AND meta_key = %s",
                (prodotto_id, meta_key),
            )
            cursor.execute(
                "INSERT INTO wp_postmeta (post_id, meta_key, meta_value) VALUES (%s, %s, %s)",
                (prodotto_id, meta_key, nuovi_valori[campo]),
            )

    return nuovi_valori


def aggiorna_seo_prodotto(
    prodotto_id: int,
    titolo_seo: str,
    meta_description: str,
    parola_chiave_focus: str,
) -> dict:
    """Scrive titolo SEO, meta description e parola chiave focus di un prodotto.

    Sovrascrive i valori esistenti. Restituisce il prima/dopo per poterlo
    controllare: l'effetto e' pubblico (quello che Google mostra in SERP).
    """
    prima = leggi_seo_prodotto(prodotto_id)
    if "errore" in prima:
        return prima

    dopo = scrivi_campi_yoast(prodotto_id, titolo_seo, meta_description, parola_chiave_focus)

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
