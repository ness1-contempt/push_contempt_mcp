"""Server MCP di esempio.

Contiene un esempio per ciascuna primitiva MCP:
- tool:     funzioni che il modello può chiamare
- resource: dati in sola lettura identificati da un URI
- prompt:   template di messaggi riutilizzabili

IMPORTANTE (trasporto stdio): non usare print() su stdout, corrompe il protocollo.
Per i log usa il modulo logging (va su stderr).
"""

import logging
from datetime import datetime

from mcp.server.mcpserver import MCPServer

from mio_mcp_server import browser_tools, seo_tools
from mio_mcp_server.db import TABLE_PREFIX, get_connection

logger = logging.getLogger(__name__)

mcp = MCPServer(
    name="mio-mcp-server",
    instructions=(
        "Server MCP di esempio: somma numeri, saluta, fornisce l'ora corrente, "
        "legge il catalogo prodotti WooCommerce direttamente dal DB e crea/modifica "
        "prodotti via browser automation su wp-admin."
    ),
)


@mcp.tool()
def somma(a: float, b: float) -> float:
    """Somma due numeri."""
    return a + b


@mcp.tool()
def saluta(nome: str, formale: bool = False) -> str:
    """Restituisce un saluto per la persona indicata."""
    logger.info("saluto per %s", nome)
    return f"Buongiorno, {nome}." if formale else f"Ciao {nome}!"


@mcp.tool()
def lista_prodotti(ricerca: str = "", limite: int = 20) -> list[dict]:
    """Elenca i prodotti WooCommerce (lettura diretta dal DB: titolo, sku, prezzo, scorte).

    `ricerca` filtra per titolo (sottostringa, case-insensitive); vuoto = tutti.
    """
    query = f"""
        SELECT
            p.ID AS id,
            p.post_title AS titolo,
            p.post_status AS stato,
            MAX(CASE WHEN pm.meta_key = '_sku' THEN pm.meta_value END) AS sku,
            MAX(CASE WHEN pm.meta_key = '_price' THEN pm.meta_value END) AS prezzo,
            MAX(CASE WHEN pm.meta_key = '_stock' THEN pm.meta_value END) AS scorte,
            MAX(CASE WHEN pm.meta_key = '_stock_status' THEN pm.meta_value END) AS stato_scorte
        FROM {TABLE_PREFIX}posts p
        LEFT JOIN {TABLE_PREFIX}postmeta pm ON pm.post_id = p.ID
        WHERE p.post_type = 'product' AND p.post_title LIKE %s
        GROUP BY p.ID
        ORDER BY p.post_title
        LIMIT %s
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(query, (f"%{ricerca}%", limite))
        return cursor.fetchall()


@mcp.tool()
def prepara_modifica_prezzo_prodotto(prodotto_id: int, nuovo_prezzo_regolare: str) -> dict:
    """Compila il nuovo prezzo regolare di un prodotto in wp-admin, senza salvare.

    Operazione sensibile: usa il browser (non il DB diretto) così l'utente
    puo' controllare lo screenshot prima che la modifica diventi effettiva.
    Dopo questo tool chiama conferma_modifica_in_corso oppure annulla_modifica_in_corso.
    """
    return browser_tools.prepara_modifica_prezzo_prodotto(prodotto_id, nuovo_prezzo_regolare)


@mcp.tool()
def crea_prodotto(
    titolo: str,
    descrizione: str,
    prezzo_regolare: str,
    categoria: str,
    percorsi_immagini: list[str],
) -> dict:
    """Crea e pubblica un nuovo prodotto WooCommerce (titolo, descrizione, prezzo,
    categoria, immagini). La prima immagine diventa quella in evidenza, le altre
    vanno nella galleria. Il prezzo va scritto con il punto come decimale.
    """
    return browser_tools.crea_prodotto(
        titolo, descrizione, prezzo_regolare, categoria, percorsi_immagini
    )


@mcp.tool()
def conferma_modifica_in_corso() -> dict:
    """Salva (click su 'Aggiorna') la modifica lasciata in sospeso da un tool prepara_*."""
    return browser_tools.conferma_modifica_in_corso()


@mcp.tool()
def annulla_modifica_in_corso() -> dict:
    """Scarta la modifica in sospeso da un tool prepara_*, senza salvare."""
    return browser_tools.annulla_modifica_in_corso()


@mcp.tool()
def lista_stato_seo_prodotti() -> list[dict]:
    """Vista d'insieme SEO su tutti i prodotti pubblicati: titolo SEO e meta
    description impostati o mancanti, con le rispettive lunghezze. Utile per
    capire da dove iniziare un'ottimizzazione SEO del catalogo.
    """
    return seo_tools.lista_stato_seo_prodotti()


@mcp.tool()
def leggi_seo_prodotto(prodotto_id: int) -> dict:
    """Stato SEO dettagliato di un prodotto (titolo SEO, meta description,
    parola chiave focus), più titolo/descrizione/prezzo come contesto per
    scrivere i nuovi testi.
    """
    return seo_tools.leggi_seo_prodotto(prodotto_id)


@mcp.tool()
def aggiorna_seo_prodotto(
    prodotto_id: int,
    titolo_seo: str,
    meta_description: str,
    parola_chiave_focus: str,
) -> dict:
    """Scrive titolo SEO, meta description e parola chiave focus di un prodotto
    (sovrascrive i valori esistenti). Restituisce prima/dopo per controllo,
    perché l'effetto è pubblico (quello che Google mostra in SERP).
    """
    return seo_tools.aggiorna_seo_prodotto(
        prodotto_id, titolo_seo, meta_description, parola_chiave_focus
    )


@mcp.resource("info://ora")
def ora_corrente() -> str:
    """Data e ora corrente del server."""
    return datetime.now().isoformat(timespec="seconds")


@mcp.prompt()
def rivedi_codice(codice: str) -> str:
    """Chiede una revisione del codice fornito."""
    return f"Rivedi questo codice e segnala bug e miglioramenti:\n\n{codice}"
