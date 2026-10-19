"""Lettura/scrittura dei campi SEO di Yoast sui prodotti WooCommerce.

Solo I/O: qui non c'e' nessuna logica di "cosa scrivere" (lunghezza ideale,
keyword density, ecc.) - quella la fa l'AI che chiama questi tool,
ragionando sui dati del prodotto. Scrittura diretta sul DB: i campi Yoast
sono testo semplice senza effetti collaterali/trigger, a differenza del
prezzo che passa dal browser.
"""

from mio_mcp_server.db import TABLE_PREFIX, get_connection

CAMPI_YOAST = {
    "titolo_seo": "_yoast_wpseo_title",
    "meta_description": "_yoast_wpseo_metadesc",
    "parola_chiave_focus": "_yoast_wpseo_focuskw",
}


def lista_stato_seo_prodotti() -> list[dict]:
    """Vista d'insieme: per ogni prodotto pubblicato, titolo SEO/meta description
    impostati o mancanti, e le loro lunghezze (utile per capire dove intervenire).
    """
    query = f"""
        SELECT
            p.ID AS id,
            p.post_title AS titolo,
            MAX(CASE WHEN pm.meta_key = '_yoast_wpseo_title' THEN pm.meta_value END)
                AS titolo_seo,
            MAX(CASE WHEN pm.meta_key = '_yoast_wpseo_metadesc' THEN pm.meta_value END)
                AS meta_description,
            MAX(CASE WHEN pm.meta_key = '_yoast_wpseo_focuskw' THEN pm.meta_value END)
                AS parola_chiave_focus
        FROM {TABLE_PREFIX}posts p
        LEFT JOIN {TABLE_PREFIX}postmeta pm ON pm.post_id = p.ID
        WHERE p.post_type = 'product' AND p.post_status = 'publish'
        GROUP BY p.ID
        ORDER BY p.post_title
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(query)
        righe = cursor.fetchall()

    for riga in righe:
        riga["lunghezza_titolo_seo"] = len(riga["titolo_seo"]) if riga["titolo_seo"] else 0
        riga["lunghezza_meta_description"] = (
            len(riga["meta_description"]) if riga["meta_description"] else 0
        )
    return righe


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
    nuovi_valori = {
        "titolo_seo": titolo_seo,
        "meta_description": meta_description,
        "parola_chiave_focus": parola_chiave_focus,
    }

    prima = leggi_seo_prodotto(prodotto_id)
    if "errore" in prima:
        return prima

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

    return {
        "stato": "aggiornato",
        "prodotto_id": prodotto_id,
        "prima": {
            "titolo_seo": prima["titolo_seo"],
            "meta_description": prima["meta_description"],
            "parola_chiave_focus": prima["parola_chiave_focus"],
        },
        "dopo": nuovi_valori,
    }
