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
    competitor_seo,
    inventory_tools,
    order_tools,
    pricing_tools,
    product_sync,
    product_tools,
    sales_tools,
    seo_tools,
    text_similarity,
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

    Se i testi nascono da un'analisi di un sito concorrente (analizza_seo_sito o
    analizza_pagine_salvate), PRIMA di chiamare questo tool: controllali con
    controlla_somiglianza, mostra all'utente punteggio e passaggi, spiegagli la
    scala 0-9 e fagli scegliere il livello che accetta; applica solo dopo la sua
    scelta. Il punteggio e' un riferimento, la responsabilita' e' sua.
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
    """Vista d'insieme SEO su tutti i prodotti pubblicati o in bozza: titolo SEO
    e meta description impostati o mancanti, con le rispettive lunghezze, stato
    e data di creazione. Utile per capire da dove iniziare un'ottimizzazione
    SEO del catalogo, distinguendo i prodotti appena inseriti da quelli del
    catalogo consolidato.
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

    Se i testi nascono da un'analisi di un sito concorrente (analizza_seo_sito o
    analizza_pagine_salvate), PRIMA di chiamare questo tool: controllali con
    controlla_somiglianza, mostra all'utente punteggio e passaggi, spiegagli la
    scala 0-9 e fagli scegliere il livello che accetta; applica solo dopo la sua
    scelta. Il punteggio e' un riferimento, la responsabilita' e' sua.
    """
    risultato = seo_tools.aggiorna_seo_prodotto(
        prodotto_id, titolo_seo, meta_description, parola_chiave_focus
    )
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def leggi_analisi_seo_yoast(prodotto_id: int) -> dict:
    """Legge il verdetto REALE di Yoast per un prodotto (problemi, miglioramenti,
    risultati buoni), cosi' come appare nell'editor di wp-admin - non
    un'approssimazione: e' l'analisi calcolata da Yoast stesso. Usalo dopo
    aggiorna_seo_prodotto per sapere se manca ancora qualcosa (es. un link in
    uscita, lunghezza minima del testo) prima di considerare chiuso il lavoro.
    """
    return browser_tools.leggi_analisi_seo_yoast(prodotto_id)


@mcp.tool()
def analizza_seo_sito(
    url: str,
    max_categorie: int = 3,
    max_prodotti: int = 10,
    caratteri_per_pagina: int = 600,
    usa_curl: bool = False,
    usa_browser: bool = False,
    browser_visibile: bool = False,
) -> dict:
    """Analizza a campione il sito di un altro negozio (di norma un concorrente)
    per capire come e' fatta la sua SEO e come descrive i prodotti: scarica la
    home, la sitemap, qualche categoria e una decina di prodotti (dura qualche
    decina di secondi: rispetta robots.txt e fa pause fra le richieste).

    Il report contiene, oltre ai campi SEO (titoli, meta description, H1/H2,
    dati strutturati, ALT), il TESTO analizzato: vocabolario (parole e coppie
    di parole ricorrenti, unita' di misura), segnali di stile e intenzione ogni
    1000 parole (inviti all'acquisto, fiducia e servizio, offerte, confronto e
    guida, tono "tu" o "noi", tecnicismo, lunghezza delle frasi), struttura
    delle descrizioni (paragrafi, elenchi, tabelle, video), i messaggi che il
    sito ripete ovunque (spedizione, resi, inviti) e, per ogni pagina, un
    breve `estratto` della descrizione. Non esegue JavaScript: se il sito
    costruisce le pagine cosi' o serve pagine segnaposto, lo dice negli `avvisi`.
    Rifiuta indirizzi di reti private.

    `url` puo' essere l'indirizzo del sito o di una sua SEZIONE (es.
    https://www.euronics.it/telefonia/): in quel caso sitemap e link restano dentro
    quella sezione e il report indica il `perimetro`. Utile per i grandi cataloghi. Se
    punta a una PAGINA di categoria (es. .../smartphone-1001.html) il campione si sceglie
    fra le sottocategorie e i prodotti che quella pagina elenca, senza usare la sitemap.

    COME USARLO: dal report ricava tu l'intenzione (informativa, comparativa,
    d'acquisto), il tono, cosa il sito enfatizza e come struttura le descrizioni,
    quali termini e misure usa per la categoria. Poi scrivi testi ORIGINALI per
    i nostri prodotti, con parole tue: gli estratti servono ad analizzare, non
    a riusare. Mai copiare frasi, titoli o description del concorrente, e solo
    cose vere sui nostri prodotti. Prima di applicare i testi con i tool SEO
    (aggiorna_seo_prodotto, crea_prodotto) passali a controlla_somiglianza, fai
    scegliere all'utente il livello di somiglianza che accetta e mostragli
    l'anteprima.

    `caratteri_per_pagina` e' la lunghezza dell'estratto di ogni pagina (0 =
    nessun estratto, massimo 2000): e' quello che pesa sui token del report.
    `max_categorie` e `max_prodotti` alzano il campione fino a un tetto (10 e 30).
    I testi analizzati restano salvati in locale per controlla_somiglianza.

    Il report ha una `valutazione` della struttura SEO del sito da 0 a 9, per area
    (titoli, meta description, intestazioni, dati strutturati, contenuto, aspetti
    tecnici) e complessiva, con la prova di ogni criterio: dice se il sito e' un buon
    modello. E' SOLO UN RIFERIMENTO: un sito scadente puo' essere buono su un'area.
    Prima di proporre testi ispirati al sito, mostra all'utente punteggio e aree e
    chiedigli se vuole usarlo come ispirazione e per quali aree; non decidere tu.

    `usa_curl`: fa le richieste con il programma curl invece che con la libreria
    Python (stesso User-Agent dichiarato, stesso rispetto di robots.txt, pause e
    Retry-After: se il sito risponde ancora 429 si ferma). Usalo SOLO se l'utente
    lo chiede esplicitamente, tipicamente per un sito che risponde 429 alla
    libreria ma non a curl: e' una sua scelta e una sua responsabilita'.
    Non cambiare User-Agent e non aggirare altri blocchi.

    `usa_browser`: attiva il metodo con un browser vero (Chromium in locale, con il
    suo User-Agent di serie, senza scaricare immagini e video). Funziona anche per i
    siti costruiti con JavaScript. L'utente puo' attivarlo una volta per tutte con
    SEO_ANALISI_USA_BROWSER=1; imposta questo parametro solo se l'utente lo chiede.
    Con il browser attivo la scala e': HTTP; se la home risponde 403/429 o sembra
    costruita con JavaScript, si aspetta il Retry-After e si passa al browser. Il
    report dice il `metodo` usato. Se nemmeno il browser basta, l'errore suggerisce
    analizza_pagine_salvate.

    `browser_visibile`: come `usa_browser` ma con la finestra del browser visibile sullo
    schermo dell'utente (SEO_ANALISI_BROWSER_VISIBILE=1 per averlo sempre). Alcuni siti
    rifiutano il browser senza finestra e non quello visibile. Usalo solo se l'utente lo
    chiede o lo approva dopo un rifiuto (403/429) anche con `usa_browser`: e' un tentativo
    in piu' contro un rifiuto del sito, non il metodo predefinito.
    """
    return competitor_seo.analizza_seo_sito(
        url,
        max_categorie,
        max_prodotti,
        caratteri_per_pagina,
        usa_curl,
        usa_browser,
        browser_visibile,
    )


@mcp.tool()
def analizza_pagine_salvate(
    percorsi: list[str], sito: str = "", caratteri_per_pagina: int = 600
) -> dict:
    """Stessa analisi di analizza_seo_sito (campi SEO, vocabolario, stile e
    intenzione, estratti) su pagine .html SALVATE dall'utente dal proprio
    browser (file singoli o cartelle), senza nessuna richiesta di rete. Serve per
    i siti che bloccano gli strumenti automatici o costruiscono le pagine con
    JavaScript (salvare la pagina gia' caricata). Il tipo di pagina (home,
    categoria, prodotto) si deduce dall'indirizzo che la pagina dichiara; `sito`
    e' solo un'etichetta per quelle che non lo dichiarano. Valgono le stesse
    regole d'uso di analizza_seo_sito: testi originali, mai copiati, e
    controlla_somiglianza prima di applicarli.
    """
    return competitor_seo.analizza_pagine_salvate(percorsi, sito, caratteri_per_pagina)


@mcp.tool()
def controlla_somiglianza(
    testo: str,
    sito: str = "",
    soglia: int | None = None,
    riferimenti: list[str] | None = None,
) -> dict:
    """Misura quanto un testo NOSTRO somiglia ai testi di un sito analizzato con
    analizza_seo_sito (o a testi dati a mano), su una scala da 0 a 9: 0 = nessuna
    somiglianza, 9 = copia. Usalo su ogni testo scritto prendendo spunto da un
    concorrente (descrizioni, titoli SEO, meta description) PRIMA di applicarlo.

    Come si calcola: sequenze di almeno 5 parole consecutive in comune (maiuscole
    e punteggiatura ignorate). Il punteggio e' il piu' alto fra la quota di parole
    del nostro testo coperta da quelle sequenze e la lunghezza della sequenza piu'
    lunga. Circa: 1-2 coincidenze occasionali, 3-4 qualche frase in comune, 5-6
    parti ricalcate, 7-8 riscrittura appena ritoccata, 9 copia. Specifiche
    tecniche e nomi di prodotto uguali alzano un po' il punteggio anche in un
    testo originale: guarda `passaggi_simili` per distinguere.

    Il punteggio e' SOLO UN RIFERIMENTO per l'utilizzatore, non e' vincolante e la
    responsabilita' dei testi pubblicati e' sua. Per questo: PRIMA di applicare
    qualsiasi modifica ai prodotti, mostragli punteggio, significato e passaggi
    simili, spiegagli la scala e chiedigli quale livello accetta (`soglia`, 0-9);
    non sceglierla tu e non applicare nulla finche' non ha deciso. Con la soglia
    il risultato include `accettabile`. Se il testo la supera, proponi una
    riscrittura con parole tue (cambiando la struttura delle frasi, non solo
    qualche parola) e ricontrolla; l'ultima parola e' dell'utente.
    `sito` limita il confronto a un sito (es. "casualbay.it"); vuoto = tutti quelli
    analizzati. `riferimenti` aggiunge testi da confrontare a mano.
    """
    if soglia is not None and not 0 <= soglia <= 9:
        return {"errore": "La soglia va da 0 a 9."}
    confronti = [
        {"fonte": f"riferimento {i}", "testo": t} for i, t in enumerate(riferimenti or [], 1)
    ]
    confronti += text_similarity.carica_riferimenti(sito or None)
    if not confronti:
        return {
            "errore": (
                "Nessun testo di riferimento: esegui prima analizza_seo_sito"
                + (f" su {sito}" if sito else "")
                + " oppure passa dei `riferimenti`."
            )
        }
    return text_similarity.controlla(testo, confronti, soglia)


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
def lista_ordini(
    stato: str = "",
    ultime_ore: int | None = None,
    piu_vecchi_di_ore: int | None = None,
    da: str | None = None,
    a: str | None = None,
    ordina: str = "desc",
    limite: int = 50,
) -> dict:
    """Elenco ordini WooCommerce, filtrabile per stato e finestra temporale.

    `stato`: uno o piu' stati WooCommerce separati da virgola, con lo slug
    nativo (non esiste uno stato "evaso"): pending (in attesa di pagamento),
    processing (in lavorazione), on-hold (in sospeso), completed
    (completato), cancelled, refunded, failed. Vuoto = tutti gli stati.
    `ultime_ore`: solo ordini creati nelle ultime N ore (24 = ultima giornata).
    `piu_vecchi_di_ore`: solo ordini creati da piu' di N ore.
    `da`/`a`: estremi (YYYY-MM-DD o YYYY-MM-DDTHH:MM, fuso del sito); `a` con la
    sola data include tutta la giornata. I filtri di data si combinano
    (intersezione). `ordina`: "desc" (piu' recenti prima) o "asc".

    Restituisce totale_trovati (anche oltre `limite`, massimo 200) e, per ogni
    ordine, numero, stato, data, totale, pagamento, citta' e prodotti: nessun
    dato personale oltre alla citta'. Per i dettagli di un ordine usa
    dettaglio_ordine.
    """
    return order_tools.lista_ordini(stato, ultime_ore, piu_vecchi_di_ore, da, a, ordina, limite)


@mcp.tool()
def dettaglio_ordine(ordine_id: int) -> dict:
    """Dettaglio completo di un ordine: righe con id prodotto, importi (subtotale,
    sconto, spedizione, tasse), date di pagamento e completamento, metodo di
    spedizione, nota del cliente e DATI PERSONALI del cliente (nome, email,
    telefono, indirizzi). Usalo solo quando serve davvero.
    """
    return order_tools.dettaglio_ordine(ordine_id)


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
