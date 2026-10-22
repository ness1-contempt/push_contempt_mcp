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

from push_contempt_mcp import (
    browser_tools,
    cache_tools,
    catalog_health,
    inventory_tools,
    pricing_tools,
    product_sync,
    product_tools,
    sales_tools,
    seo_tools,
)

logger = logging.getLogger(__name__)

mcp = MCPServer(
    name="push_contempt_mcp",
    instructions=(
        "Server MCP di esempio: somma numeri, saluta, fornisce l'ora corrente, "
        "legge il catalogo prodotti WooCommerce via REST, crea nuovi prodotti "
        "in bozza via REST e modifica prezzi/SEO via REST o browser "
        "automation su wp-admin."
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
    """Elenca i prodotti WooCommerce via REST (titolo, sku, prezzo, scorte).

    `ricerca` filtra per titolo (sottostringa, case-insensitive); vuoto = tutti.
    """
    return product_tools.elenco_prodotti(ricerca, limite)


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
    alt_immagini: list[str],
    frase_chiave_focus: str,
    titolo_seo: str,
    meta_description: str,
) -> dict:
    """Crea un nuovo prodotto WooCommerce IN BOZZA (titolo, descrizione, prezzo,
    categoria, immagini), con SEO e ALT immagini gia' impostati in automatico:
    non serve piu' chiamare aggiorna_seo_prodotto dopo. La prima immagine
    diventa quella in evidenza, le altre vanno nella galleria. Il prezzo va
    scritto con il punto come decimale. `alt_immagini` deve avere un elemento
    per ogni immagine (stesso ordine di percorsi_immagini). La risposta include
    `avvisi_seo`: se non vuoto, la descrizione non rispetta ancora densita'
    della frase chiave, sottotitoli o link interni - da sistemare. Non viene
    pubblicato: resta da rivedere e pubblicare da wp-admin (vedi
    prodotti_in_bozza e la tab "Carica prodotti" del plugin), quindi non
    serve invalidare la cache del sito.
    """
    return product_tools.crea_prodotto(
        titolo,
        descrizione,
        prezzo_regolare,
        categoria,
        percorsi_immagini,
        alt_immagini,
        frase_chiave_focus,
        titolo_seo,
        meta_description,
    )


@mcp.tool()
def prodotti_in_bozza() -> list[dict]:
    """Prodotti creati con crea_prodotto e non ancora pubblicati, piu'
    recenti prima: promemoria di cosa resta da rivedere su wp-admin.
    """
    return product_tools.prodotti_in_bozza()


@mcp.tool()
def conferma_modifica_in_corso() -> dict:
    """Salva (click su 'Aggiorna') la modifica lasciata in sospeso da un tool
    prepara_*, e invalida la cache del sito (altrimenti la modifica non si
    vedrebbe online)."""
    risultato = browser_tools.conferma_modifica_in_corso()
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def annulla_modifica_in_corso() -> dict:
    """Scarta la modifica in sospeso da un tool prepara_*, senza salvare."""
    return browser_tools.annulla_modifica_in_corso()


@mcp.tool()
def controllo_salute_catalogo(soglia_descrizione: int = 50) -> list[dict]:
    """Prodotti pubblicati ma incompleti: nessuna immagine in evidenza,
    nessuna categoria, prezzo mancante/zero/non valido (solo prodotti
    semplici - quelli variabili non hanno un prezzo proprio), descrizione
    più corta di `soglia_descrizione` caratteri. Prodotti senza problemi
    non compaiono nel risultato.
    """
    return catalog_health.controllo_salute_catalogo(soglia_descrizione)


@mcp.tool()
def report_vendite_prodotti(periodo: str = "1_mese") -> dict:
    """Report vendite per prodotto: più venduti con quantità e ricavo netto,
    più i prodotti pubblicati mai venduti (su tutta la storia del negozio).
    `periodo`: uno tra "1_mese", "3_mesi", "6_mesi", "1_anno".
    """
    return sales_tools.report_vendite_prodotti(periodo)


@mcp.tool()
def prodotti_sotto_scorta(soglia: float = 5) -> list[dict]:
    """Prodotti pubblicati esauriti o con scorte sotto `soglia` (solo quelli
    con gestione scorte attiva in WooCommerce - per gli altri conta solo lo
    stato esaurito/in attesa, non c'è un numero di scorte attendibile).
    Esauriti per primi, poi per scorte crescenti: utile per capire cosa
    rifornire con più urgenza.
    """
    return inventory_tools.prodotti_sotto_scorta(soglia)


@mcp.tool()
def scansiona_cartella_prodotti(percorso_cartella: str) -> dict:
    """Confronta una cartella locale (`<Categoria>/<Prodotto>/` con foto + .txt)
    con il catalogo WooCommerce: separa i prodotti già presenti (ignorati) da
    quelli nuovi. Non crea né modifica nulla - per i prodotti nuovi restituisce
    categoria, percorsi immagini e testo grezzo del .txt, da cui vanno estratti
    prezzo e descrizione (leggendo il testo) prima di chiamare crea_prodotto
    per ciascuno. Pensato per il bottone "carica prodotti" del plugin.
    """
    return product_sync.scansiona_cartella_prodotti(percorso_cartella)


@mcp.tool()
def leggi_seo_prodotti_selezionati(prodotto_ids: list[int]) -> list[dict]:
    """Stato SEO di una selezione di prodotti in un'unica chiamata (stesso
    contenuto di leggi_seo_prodotto, per ciascun id). Pensato per il bottone
    "ottimizza SEO" del plugin: funziona anche su prodotti caricati prima
    del plugin, non solo su quelli appena creati con scansiona_cartella_prodotti.
    """
    return seo_tools.leggi_seo_prodotti_selezionati(prodotto_ids)


@mcp.tool()
def calcola_aggiornamento_prezzi(
    categoria: str, percentuale: float | None = None, delta: float | None = None
) -> dict:
    """Prodotti semplici di una categoria con prezzo attuale e quello
    calcolato (percentuale, es. 10/-15, oppure delta fisso in valuta,
    es. -5: specificarne solo uno). Solo lettura - da far rivedere all'utente
    prima di chiamare applica_aggiornamento_prezzi. I prodotti variabili
    della categoria sono elencati a parte, esclusi dal calcolo.
    """
    return pricing_tools.calcola_aggiornamento_prezzi(categoria, percentuale, delta)


@mcp.tool()
def applica_aggiornamento_prezzi(aggiornamenti: list[dict]) -> dict:
    """Scrive i nuovi prezzi (lista approvata, stessa forma dell'output di
    calcola_aggiornamento_prezzi: ogni elemento serve `id` e
    `prezzo_regolare_nuovo`). Scrittura diretta sul DB, aggiorna anche la
    lookup table di WooCommerce, e invalida la cache del sito (altrimenti il
    prezzo nuovo non si vedrebbe online pur essendo corretto nel DB).
    """
    risultato = pricing_tools.applica_aggiornamento_prezzi(aggiornamenti)
    return {**risultato, **cache_tools.purga_cache()}


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
    perché l'effetto è pubblico (quello che Google mostra in SERP). Invalida
    anche la cache del sito.
    """
    risultato = seo_tools.aggiorna_seo_prodotto(
        prodotto_id, titolo_seo, meta_description, parola_chiave_focus
    )
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def aggiorna_seo_categoria(term_id: int, titolo_seo: str, meta_description: str) -> dict:
    """Scrive titolo SEO e meta description di una categoria prodotto, via wp-admin.

    A differenza dei prodotti, per le categorie Yoast non rilegge i campi SEO
    scritti via DB diretto: questo tool passa dalla UI reale di modifica
    categoria, l'unico modo affidabile di aggiornarli. Invalida anche la
    cache del sito.
    """
    risultato = browser_tools.aggiorna_seo_categoria(term_id, titolo_seo, meta_description)
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def purga_cache_sito() -> dict:
    """Invalida manualmente la cache del sito (stessa procedura che gli altri
    tool di scrittura chiamano già in automatico). Utile se qualcosa è stato
    modificato fuori da questi tool e il frontend mostra ancora contenuti
    vecchi.
    """
    return cache_tools.purga_cache()


@mcp.resource("info://ora")
def ora_corrente() -> str:
    """Data e ora corrente del server."""
    return datetime.now().isoformat(timespec="seconds")


@mcp.prompt()
def rivedi_codice(codice: str) -> str:
    """Chiede una revisione del codice fornito."""
    return f"Rivedi questo codice e segnala bug e miglioramenti:\n\n{codice}"
