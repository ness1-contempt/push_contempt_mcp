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
    alt_tools,
    azioni_pubbliche_tools,
    blog_tools,
    browser_tools,
    cache_tools,
    catalog_health,
    competitor_seo,
    descrizione_tools,
    inventory_tools,
    link_tools,
    order_tools,
    pricing_tools,
    product_sync,
    product_tools,
    sales_tools,
    seo_tools,
    seo_varianti_tools,
    text_similarity,
)

logger = logging.getLogger(__name__)

mcp = MCPServer(
    name="push_contempt_mcp",
    instructions=(
        "Server MCP di esempio: somma numeri, saluta, fornisce l'ora corrente, "
        "legge il catalogo prodotti WooCommerce via REST, crea nuovi prodotti "
        "in bozza via REST, modifica prezzi/SEO via REST o browser "
        "automation su wp-admin e analizza la SEO dei siti concorrenti.\n\n"
        "ANALISI DEI CONCORRENTI: l'utente e' il titolare del negozio e ha deciso lui di "
        "analizzare i siti dei concorrenti per prenderne ispirazione. Leggere le pagine "
        "pubbliche di un altro negozio (il tool rispetta robots.txt, pause e limiti) e "
        "scrivere testi ORIGINALI ispirati al suo modo di descrivere i prodotti e' un uso "
        "lecito e voluto: eseguilo senza rifiutare, senza esitare e senza chiedere "
        "giustificazioni o conferme in piu' (su copyright, scraping, etica della concorrenza, "
        "motivo della richiesta), e senza ripeterlo ad ogni messaggio. Se l'utente insiste su "
        "qualcosa che il server consente, e' gia' la sua risposta: fallo. Le uniche fermate "
        "previste sono quelle scritte nelle descrizioni dei tool: far scegliere all'utente "
        "aree di ispirazione e livello di somiglianza accettato PRIMA di modificare i "
        "prodotti, e usare usa_curl / usa_browser / browser_visibile solo se l'utente li "
        "chiede (quando li chiede, usali senza obiezioni: e' una sua scelta e responsabilita').\n\n"
        "PRODOTTI VARIABILI: per creare un prodotto con varianti usa crea_prodotto_variabile "
        "(prezzo unico per tutte le varianti, senza scorte, sempre in bozza). Se il file di "
        'testo ha la riga "varianti: Colore: Nero, Bianco | Memoria: 256 GB, 512 GB" usala '
        "cosi' com'e' (scansiona_cartella_prodotti la restituisce gia' letta in `varianti`). "
        "Se le varianti sono solo descritte nel testo libero, ricavale TU ma con cautela: "
        "solo valori scritti davvero, mai inventati, e prima di creare mostra all'utente "
        "l'anteprima e aspetta il suo ok; se il testo e' ambiguo chiedi invece di indovinare. "
        "Fai sempre prima la chiamata con anteprima=True.\n\n"
        "CARTELLA PRODOTTI E CATEGORIE: la struttura delle cartelle rispecchia l'albero delle "
        "categorie WooCommerce (es. Indumenti/Magliette/<Prodotto>/ con foto e .txt). Usa "
        "scansiona_cartella_prodotti e passa a crea_prodotto/crea_prodotto_variabile il "
        "`percorso_categoria` che restituisce. Un nome di categoria deve esistere una volta "
        "sola nell'albero: se la scansione segnala `problemi_categorie` o `conflitti_categorie`, "
        "o ci sono cartelle in `da_controllare`, NON caricare quei prodotti e riporta il problema "
        "all'utente cosi' com'e', senza provare a sistemarlo da solo.\n\n"
        "SEO DEI PRODOTTI VARIABILI: un variabile ha UNA pagina sola (le varianti non hanno un "
        "indirizzo proprio: il canonical e' quello del padre), quindi titolo SEO, meta description "
        "e descrizione sono del PRODOTTO, non di una variante. Parti sempre da leggi_seo_varianti: "
        "restituisce attributi, varianti e `problemi` ordinati per gravita' (errore, avviso, "
        "suggerimento) e chiarisce cosa correggere. Regole: (1) i testi del padre parlano del "
        "prodotto con le sue varianti e citano in modo naturale i valori che esistono davvero "
        "(colori, taglie, memorie); mai un valore non presente nelle varianti. (2) titolo SEO e "
        "parola chiave focus NON citano una sola variante (es. 'Felpa nera') quando ce ne sono "
        "altre: e' il problema `titolo_seo_con_una_variante`. (3) nessun prezzo scritto nei testi: "
        "cambia, e il testo resterebbe sbagliato; l'intervallo lo mostra la scheda. (4) "
        "aggiorna_seo_varianti per la descrizione di una variante solo quando aggiunge "
        "un'informazione vera (colore, taglia, differenza); mai SKU inventati, solo quelli che "
        "l'utente dà o che sono gia' nel suo catalogo. (5) ALT delle immagini di una variante: "
        "descrivono quella variante (es. 'Felpa in cotone nera') e contengono la parola chiave; "
        "si leggono e scrivono con leggi_alt_immagini_prodotto / aggiorna_alt_immagini_prodotto "
        "(ruolo 'variante'). (6) i dati strutturati (una voce per variante con prezzo, "
        "disponibilita', colore, taglia) li genera il plugin da solo: non esiste un tool, non "
        "scriverli tu nella descrizione. I problemi `variante_senza_prezzo`, "
        "`variante_qualsiasi` e `combinazione_duplicata` non si correggono da qui: sono errori di "
        "catalogo da sistemare in wp-admin, riportali all'utente.\n\n"
        "AZIONI VISIBILI A TUTTI - PUBBLICARE BOZZE E SPOSTARE CATEGORIE: pubblica_prodotti e "
        "sposta_categoria_prodotti cambiano il sito pubblico, quindi si fanno SOLO cosi': (1) "
        "chiami il tool con anteprima=True (e' il predefinito) e ottieni cosa succederebbe e "
        "un `codice_conferma`; (2) mostri all'utente il risultato per intero (per i prodotti: "
        "l'elenco, gli `avvisi` di ciascuno e quelli `non_pubblicabili` con i motivi; per la "
        "categoria: percorso prima e dopo, indirizzi, sottocategorie, prodotti coinvolti e "
        "avvisi) e gli chiedi esplicitamente se vuole procedere; (3) SOLO dopo un suo si "
        "chiaro a QUELLA lista richiami con anteprima=False e il `codice_conferma` ricevuto. "
        "Non dedurre il consenso da richieste generiche ('sistema tutto', 'metti online le "
        "bozze'): anche in quel caso fai l'anteprima e chiedi. Se cambia la lista o l'utente "
        "aggiunge qualcosa, rifai l'anteprima e richiedi il si; se il plugin risponde che il "
        "codice non vale piu', rifai l'anteprima. Non ripetere l'azione su elementi gia' "
        "fatti. Per trovare l'id di una categoria usa lista_categorie_prodotti; se la "
        "categoria di destinazione non esiste ancora creala con crea_categoria_prodotti "
        "(anteprima e ok dell'utente). Un prodotto con avvisi (niente immagine, campi SEO "
        "vuoti) si puo' pubblicare se l'utente lo vuole, ma diglielo; i bloccanti (niente "
        "prezzo, varianti sbagliate) si correggono in wp-admin. Spostare una categoria cambia "
        "il suo indirizzo: riporta sempre l'avviso sul redirect.\n\n"
        "BLOG: scrivi articoli per il blog del negozio, sempre in BOZZA (non pubblicarli mai: "
        "li pubblica l'utente da wp-admin). Flusso: (1) leggi_brief_blog; se `compilato` e' "
        "falso chiedi all'utente argomento, pubblico e tono (o ricavali dalla sua richiesta) e "
        "salvali con salva_brief_blog. (2) contesto_blog: negozio, categorie, prodotti con "
        "indirizzo e immagine, articoli gia' presenti. (3) Proponi all'utente il piano: per "
        "ogni articolo titolo, frase chiave, prodotti da linkare; non ripetere argomenti di "
        "`articoli_esistenti`; al massimo `n_articoli` del brief per volta; aspetta il suo ok. "
        "(4) Scrivi ogni articolo in HTML (H2/H3, niente H1), nella `lingua` e con il `tono` e le "
        "`note` del brief, lungo circa `lunghezza_parole`. Se il brief ha `ottimizza_aeo_geo` "
        "attivo, leggi_brief_blog e contesto_blog restituiscono `regole_aeo_geo`: applicale a "
        "ogni articolo (domande come sottotitoli con risposta di 40-60 parole, elenchi e "
        "tabelle vere, FAQ finale, contenuto originale); se "
        "una regola spingesse a scrivere qualcosa di non verificato vince la regola di non "
        "inventare. Regole sui contenuti: usa solo "
        "informazioni che puoi verificare (cerca fonti sul web se hai lo strumento) e linka "
        "almeno una fonte autorevole; mai inventare dati, statistiche, citazioni, premi o "
        "caratteristiche dei prodotti; se non sai una cosa non scriverla. Link interni solo agli "
        "indirizzi reali di contesto_blog, mai prezzi nel testo (cambiano). Testo ORIGINALE: se "
        "prendi spunto da un concorrente controlla_somiglianza e fai scegliere il livello "
        "all'utente prima di salvare. (5) Immagini: non generarne. Riusa `immagine_url` / "
        "`immagine_id` dei prodotti di contesto_blog oppure carica file dell'utente con "
        "carica_immagine_blog (ALT descrittivo obbligatorio); metti un'immagine in evidenza. "
        "(6) crea_articolo_bozza, poi correggi gli `avvisi` con aggiorna_articolo_bozza. Se "
        "rifiuta un titolo gia' usato non forzare con consenti_duplicato: dillo all'utente. "
        "(7) Alla fine riporta per ogni articolo titolo, parole, link e `url_modifica`, e gli "
        "avvisi che restano. Ricorda che le bozze vanno riviste da una persona prima di uscire."
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
    """Elenca i prodotti WooCommerce via REST (titolo, sku, tipo, prezzo, scorte).

    `ricerca` filtra per titolo (sottostringa, case-insensitive); vuoto = tutti.

    `tipo` e' il tipo WooCommerce (simple, variable, grouped, external). Il
    prezzo di un prodotto semplice e' `prezzo`; un variabile o raggruppato non
    ha un prezzo solo: `prezzo` e' null e vanno letti `prezzo_min` e
    `prezzo_max` (le varianti in vendita; `numero_varianti` dice quante ce
    ne sono). Per ogni tipo `prezzo_min`/`prezzo_max` ci sono sempre.
    """
    return product_tools.elenco_prodotti(ricerca, limite)


@mcp.tool()
def prepara_modifica_prezzo_prodotto(prodotto_id: int, nuovo_prezzo_regolare: str) -> dict:
    """Compila il nuovo prezzo regolare di un prodotto in wp-admin, senza salvare.

    Operazione sensibile: usa il browser (non il DB diretto) così l'utente
    puo' controllare lo screenshot prima che la modifica diventi effettiva.
    Il browser viene CHIUSO prima di tornare: la modifica resta ricordata (30
    minuti). Dopo questo tool chiama conferma_modifica_in_corso oppure
    annulla_modifica_in_corso.
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
    percorso_categoria: list[str] | None = None,
) -> dict:
    """Crea un nuovo prodotto WooCommerce IN BOZZA (titolo, descrizione, prezzo,
    categoria, immagini), con SEO e ALT immagini gia' impostati in automatico:
    non serve piu' chiamare aggiorna_seo_prodotto dopo. La prima immagine
    diventa quella in evidenza, le altre vanno nella galleria. Il prezzo va
    scritto con il punto come decimale. `alt_immagini` deve avere un elemento
    per ogni immagine (stesso ordine di percorsi_immagini). La risposta include
    `avvisi_seo`: se non vuoto, la descrizione non rispetta ancora densita'
    della frase chiave, sottotitoli o link interni - da sistemare. Non viene
    pubblicato: resta da rivedere e pubblicare da wp-admin o, solo se l'utente
    lo chiede e dopo la sua conferma, con pubblica_prodotti (vedi
    prodotti_in_bozza e la tab "Carica prodotti" del plugin), quindi non
    serve invalidare la cache del sito.

    CATEGORIE: le cartelle dei prodotti rispecchiano l'albero delle categorie di
    WooCommerce. Passa in `percorso_categoria` l'elenco dei nomi dalla radice alla
    categoria del prodotto (es. ["Indumenti", "Magliette"]; scansiona_cartella_prodotti
    te lo restituisce gia' pronto): le categorie che mancano vengono create una dentro
    l'altra, quelle che ci sono si riusano, e il prodotto va solo nella piu' in basso.
    Un nome di categoria esiste UNA volta sola in tutto l'albero: se sul sito c'e' gia'
    una categoria con quel nome in un altro punto (o ce n'e' piu' di una) il plugin
    risponde con un errore 409 e non crea niente, ne' prodotto ne' categorie: riporta
    il messaggio all'utente (dice dove sta la categoria e dove la vorrebbe la cartella)
    e NON aggirarlo creando la categoria altrove. Senza `percorso_categoria` vale la
    sola `categoria` (cercata per nome, o creata in cima).

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
        percorso_categoria,
    )


@mcp.tool()
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
    """Crea un prodotto VARIABILE (colori, memoria, taglie...) IN BOZZA: una variante
    per ogni combinazione dei valori, tutte allo STESSO prezzo (`prezzo_regolare`,
    punto come decimale) e SENZA gestione scorte. Il resto (descrizione, categoria,
    immagini, ALT, SEO, `avvisi_seo`) funziona come in crea_prodotto. Non viene
    pubblicato. Massimo 4 attributi e 50 varianti.

    DUE MODI per dare gli attributi (esattamente uno dei due):

    1) `riga_varianti` - MODO PRECISO. Se il file di testo del prodotto ha una riga
    che comincia con "varianti:" (scansiona_cartella_prodotti te la restituisce gia'
    letta nel campo `varianti`), passa qui il suo contenuto cosi' com'e', per esempio
    "Colore: Nero, Bianco | Memoria: 256 GB, 512 GB" (attributi separati da "|",
    valori separati da virgola). Il server la legge senza interpretarla: se e'
    scritta male torna un errore chiaro, e allora non indovinare, chiedi all'utente.

    2) `attributi` - MODO AUTOMATICO. Se la riga non c'e', ricavi tu gli attributi
    dal testo, per esempio {"Colore": ["Nero", "Bianco"], "Memoria": ["256 GB"]}. E'
    il modo a rischio d'errore: puoi leggere male un valore, inventarne uno o
    scambiare una frase descrittiva per una variante. Quindi: usa solo valori
    scritti davvero nel testo (nessuna deduzione, nessun valore "tipico" del
    modello), non creare varianti se il testo e' ambiguo (chiedi), e SEMPRE mostra
    all'utente l'anteprima e aspetta il suo ok prima di creare.

    `anteprima=True` (predefinito): NON scrive niente (nemmeno immagini o categoria)
    e restituisce le varianti che nascerebbero (`varianti`, con prezzo), il numero,
    gli attributi e se la categoria e' nuova. Fai sempre prima l'anteprima. Se hai
    usato `riga_varianti` e l'anteprima corrisponde alla riga puoi creare subito; se
    hai usato `attributi` mostrala all'utente e aspetta il suo ok. Poi richiama con
    `anteprima=False` per creare (resta in bozza, quindi non serve invalidare la
    cache). Se l'utente chiede di cambiare una variante, richiama l'anteprima.

    `percorso_categoria`: come per crea_prodotto (vedi la' per le regole sulle categorie).

    `avvisi_seo` segnala anche i testi che non vanno bene per un variabile: valori delle
    varianti che la descrizione non cita, titolo SEO o parola chiave focus che nominano
    una sola variante (vedi le regole sui prodotti variabili). Correggili prima di creare.

    Prezzi e scorte per singola variante, e le foto per variante, si cambiano dopo da
    wp-admin: questo tool non li gestisce.
    """
    return product_tools.crea_prodotto_variabile(
        titolo,
        descrizione,
        prezzo_regolare,
        categoria,
        percorsi_immagini,
        alt_immagini,
        frase_chiave_focus,
        titolo_seo,
        meta_description,
        attributi,
        riga_varianti,
        anteprima,
        percorso_categoria,
    )


@mcp.tool()
def prodotti_in_bozza() -> list[dict]:
    """Prodotti creati con crea_prodotto e non ancora pubblicati, piu'
    recenti prima: promemoria di cosa resta da rivedere su wp-admin. Per
    pubblicarle c'e' pubblica_prodotti (anteprima e conferma dell'utente).
    """
    return product_tools.prodotti_in_bozza()


@mcp.tool()
def leggi_brief_blog() -> dict:
    """Le indicazioni del negozio per il blog: argomento, pubblico, tono, lingua,
    lunghezza in parole, quanti articoli per volta, categorie di prodotti da far comparire
    e note libere. `compilato` e' falso finche' manca l'argomento."""
    return blog_tools.leggi_brief_blog()


@mcp.tool()
def salva_brief_blog(
    argomento: str | None = None,
    pubblico: str | None = None,
    tono: str | None = None,
    lingua: str | None = None,
    lunghezza_parole: int | None = None,
    n_articoli: int | None = None,
    categorie_prodotti: list[int] | None = None,
    note: str | None = None,
    ottimizza_aeo_geo: bool | None = None,
) -> dict:
    """Aggiorna il brief del blog: cambiano solo i campi passati. `lingua` e' un codice
    come "it" o "en-GB"; `lunghezza_parole` 300-3000; `n_articoli` 1-10 (quanti articoli
    scrivere per volta); `categorie_prodotti` sono gli id delle categorie prodotto da far
    comparire (lista_categorie_prodotti); `note` sono regole libere; `ottimizza_aeo_geo` (attivo
    di base) fa restituire le regole AEO/GEO da applicare agli articoli. Salva solo cio'
    che l'utente ha detto o confermato."""
    return blog_tools.salva_brief_blog(
        argomento,
        pubblico,
        tono,
        lingua,
        lunghezza_parole,
        n_articoli,
        categorie_prodotti,
        note,
        ottimizza_aeo_geo,
    )


@mcp.tool()
def contesto_blog() -> dict:
    """Il materiale per scrivere articoli coerenti col negozio: dati del sito, brief,
    categorie di prodotti e del blog, i prodotti piu' venduti (con `url`, `immagine_id` e
    `immagine_url` per linkarli e riusarne le foto) e gli articoli gia' presenti (per non
    ripetere gli argomenti). Chiamalo prima di proporre un piano di articoli."""
    return blog_tools.contesto_blog()


@mcp.tool()
def lista_articoli_blog(
    stato: str = "any", ricerca: str = "", limite: int = 50
) -> list[dict] | dict:
    """Articoli del blog, piu' recenti prima, con parole, link interni/esterni e prodotti
    collegati. `stato`: "any" (default), "draft" (bozze da rivedere) o "publish"."""
    return blog_tools.lista_articoli(stato, ricerca, limite)


@mcp.tool()
def leggi_articolo_blog(articolo_id: int) -> dict:
    """Un articolo per intero (testo HTML, categorie, tag, titolo SEO, meta description,
    frase chiave), per rivederlo o correggerlo."""
    return blog_tools.leggi_articolo(articolo_id)


@mcp.tool()
def carica_immagine_blog(percorso: str, alt: str) -> dict:
    """Carica un'immagine dell'utente (percorso sul computer dove gira questo server) nella
    libreria media con il suo testo ALT e restituisce `id` (per l'immagine in evidenza) e
    `url` (per metterla nel testo con <img>). L'ALT descrive cosa mostra l'immagine."""
    return blog_tools.carica_immagine_blog(percorso, alt)


@mcp.tool()
def crea_articolo_bozza(
    titolo: str,
    contenuto: str,
    frase_chiave_focus: str,
    titolo_seo: str,
    meta_description: str,
    categoria: str | None = None,
    tag: list[str] | None = None,
    estratto: str | None = None,
    immagine_evidenza_id: int | None = None,
    prodotti_ids: list[int] | None = None,
    consenti_duplicato: bool = False,
) -> dict:
    """Crea un articolo del blog in BOZZA: mai pubblicato, lo pubblica l'utente da wp-admin.
    `contenuto` e' HTML con H2/H3 (niente H1: il titolo lo e' gia'). `titolo_seo` fino a 60
    caratteri, `meta_description` 120-160. `prodotti_ids` sono i prodotti che l'articolo
    promuove. Restituisce `articolo_id`, `url_modifica`, parole, link e `avvisi` da correggere
    con aggiorna_articolo_bozza. Un titolo gia' usato viene rifiutato: non usare
    consenti_duplicato senza che l'utente lo voglia."""
    return blog_tools.crea_articolo_bozza(
        titolo,
        contenuto,
        frase_chiave_focus,
        titolo_seo,
        meta_description,
        categoria,
        tag,
        estratto,
        immagine_evidenza_id,
        prodotti_ids,
        consenti_duplicato,
    )


@mcp.tool()
def aggiorna_articolo_bozza(
    articolo_id: int,
    titolo: str | None = None,
    contenuto: str | None = None,
    frase_chiave_focus: str | None = None,
    titolo_seo: str | None = None,
    meta_description: str | None = None,
    categoria: str | None = None,
    tag: list[str] | None = None,
    estratto: str | None = None,
    immagine_evidenza_id: int | None = None,
    prodotti_ids: list[int] | None = None,
) -> dict:
    """Modifica una BOZZA di blog (solo i campi passati). Un articolo gia' pubblicato viene
    rifiutato: va cambiato da wp-admin. Restituisce gli `avvisi` aggiornati sul testo completo."""
    return blog_tools.aggiorna_articolo_bozza(
        articolo_id,
        titolo,
        contenuto,
        frase_chiave_focus,
        titolo_seo,
        meta_description,
        categoria,
        tag,
        estratto,
        immagine_evidenza_id,
        prodotti_ids,
    )


@mcp.tool()
def conferma_modifica_in_corso() -> dict:
    """Salva la modifica preparata da un tool prepara_*: riapre il browser,
    controlla che il prezzo non sia cambiato dopo la preparazione (altrimenti non
    salva niente e lo dice), clicca 'Aggiorna', CHIUDE il browser e invalida la
    cache del sito (altrimenti la modifica non si vedrebbe online)."""
    risultato = browser_tools.conferma_modifica_in_corso()
    if risultato.get("stato") != "salvato":
        return risultato
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def annulla_modifica_in_corso() -> dict:
    """Scarta la modifica preparata da un tool prepara_*, senza salvare (il browser
    e' gia' chiuso dopo prepara_*)."""
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

    Di un prodotto variabile compaiono anche le singole varianti pubblicate
    esaurite o sotto soglia (taglia, colore...): hanno lo stesso `id` del
    prodotto, con `variante` (es. "Taglia: L") e `variante_id` valorizzati.
    Una variante che eredita le scorte dal padre non si ripete: la copre la
    riga del padre.
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
    parola chiave focus), più titolo/descrizione/tipo/prezzo come contesto per
    scrivere i nuovi testi. Per un prodotto variabile o raggruppato `prezzo` e'
    null e il prezzo e' l'intervallo `prezzo_min`-`prezzo_max` (stessi campi di
    lista_prodotti). Se `tipo` e' "variable" usa anche leggi_seo_varianti: ha le
    varianti e i problemi SEO specifici (vedi le regole sui prodotti variabili).
    """
    return seo_tools.leggi_seo_prodotto(prodotto_id)


@mcp.tool()
def aggiorna_seo_prodotto(
    prodotto_id: int,
    titolo_seo: str,
    meta_description: str,
    parola_chiave_focus: str,
    origine: str = "",
) -> dict:
    """Scrive titolo SEO, meta description e parola chiave focus di un prodotto
    (sovrascrive i valori esistenti). Restituisce prima/dopo per controllo,
    perché l'effetto è pubblico (quello che Google mostra in SERP). Invalida
    anche la cache del sito. Il plugin tiene la base (stato prima del primo
    intervento) e il precedente: l'utente li ritrova nella tab SEO e puoi
    rimetterli con ripristina_seo_prodotti. Se i testi si ispirano a un concorrente, passa in
    `origine` il suo sito (es. "concorrente tomatosmartphone.it").

    Se i testi nascono da un'analisi di un sito concorrente (analizza_seo_sito o
    analizza_pagine_salvate), PRIMA di chiamare questo tool: controllali con
    controlla_somiglianza, mostra all'utente punteggio e passaggi, spiegagli la
    scala 0-9 e fagli scegliere il livello che accetta; applica solo dopo la sua
    scelta. Il punteggio e' un riferimento, la responsabilita' e' sua.
    """
    risultato = seo_tools.aggiorna_seo_prodotto(
        prodotto_id, titolo_seo, meta_description, parola_chiave_focus, origine
    )
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def ripristina_seo_prodotti(prodotto_ids: list[int], versione: str = "base") -> dict:
    """Rimette titolo SEO, meta description e parola chiave focus di uno o più
    prodotti come in una delle versioni conservate dal plugin: "base" (il punto
    di partenza, di norma lo stato originale di Yoast) o "precedente" (la
    versione da cui si viene, cioè quella sostituita dall'ultima scrittura).
    La versione che si lascia diventa il "precedente", quindi si può sempre
    tornare indietro. Un prodotto mai modificato non viene toccato. Restituisce
    l'esito per ogni id: "ripristinato", "gia_in_uso", "nessuno_snapshot" o
    "non_trovato". Invalida anche la cache del sito. Usalo solo su richiesta
    dell'utente: sovrascrive i testi attuali. Non esiste un tool per ridefinire
    la base: lo fa solo l'utente dalla tab SEO.
    """
    risultato = seo_tools.ripristina_seo_prodotti(prodotto_ids, versione)
    if "errore" in risultato:
        return risultato
    return {"esiti": risultato, **cache_tools.purga_cache()}


@mcp.tool()
def leggi_descrizione_prodotto(prodotto_id: int) -> dict:
    """Descrizione lunga e breve attuali di un prodotto (HTML), con le versioni
    base e precedente conservate dal plugin (null se non e' mai stata modificata
    con aggiorna_descrizione_prodotto)."""
    return descrizione_tools.leggi_descrizione_prodotto(prodotto_id)


@mcp.tool()
def aggiorna_descrizione_prodotto(
    prodotto_id: int,
    descrizione_html: str,
    descrizione_breve: str | None = None,
    origine: str = "",
) -> dict:
    """Scrive la descrizione di un prodotto (HTML, filtrato come in un articolo
    WordPress: niente script) e, se data, anche la descrizione breve; se
    `descrizione_breve` manca resta quella attuale. Sovrascrive i testi
    esistenti e restituisce prima/dopo per controllo, perche' l'effetto e'
    pubblico. Invalida anche la cache del sito. Il plugin tiene la base (stato
    prima del primo intervento) e il precedente: si rimettono con
    ripristina_descrizione_prodotti. `origine` (facoltativa) dice chi ha scritto.
    """
    risultato = descrizione_tools.aggiorna_descrizione_prodotto(
        prodotto_id, descrizione_html, descrizione_breve, origine
    )
    if "errore" in risultato:
        return risultato
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def ripristina_descrizione_prodotti(prodotto_ids: list[int], versione: str = "base") -> dict:
    """Rimette descrizione e descrizione breve di uno o piu' prodotti come in una
    delle versioni conservate dal plugin: "base" (lo stato prima del primo
    intervento) o "precedente" (quella sostituita dall'ultima scrittura). La
    versione che si lascia diventa il "precedente", quindi si puo' sempre
    tornare indietro. Un prodotto mai modificato con aggiorna_descrizione_prodotto
    non viene toccato. Esiti per id: "ripristinato", "gia_in_uso",
    "nessuno_snapshot" o "non_trovato". Invalida anche la cache del sito. Usalo
    solo su richiesta dell'utente: sovrascrive i testi attuali.
    """
    risultato = descrizione_tools.ripristina_descrizione_prodotti(prodotto_ids, versione)
    if "errore" in risultato:
        return risultato
    return {"esiti": risultato, **cache_tools.purga_cache()}


@mcp.tool()
def analizza_link_prodotto(prodotto_id: int) -> dict:
    """Elenca i link nella descrizione lunga di un prodotto, divisi in interni
    (verso il sito stesso), esterni (verso altri siti) e altri (ancore, mailto,
    tel), ciascuno con indirizzo, testo cliccabile e nofollow. Dice anche
    `ha_link_in_uscita`: e' la verifica che Yoast segnala piu' spesso come
    mancante. Sola lettura: per aggiungere un link riscrivi la descrizione con
    aggiorna_descrizione_prodotto.
    """
    return link_tools.analizza_link_prodotto(prodotto_id)


@mcp.tool()
def analizza_link_prodotti(stato: str = "publish", solo_senza_link_in_uscita: bool = False) -> dict:
    """Controlla i link della descrizione di TUTTI i prodotti in una chiamata:
    per ciascuno quanti link interni ed esterni ha e se ha link in uscita (la
    verifica che Yoast segnala piu' spesso come mancante). In testa i conteggi:
    prodotti analizzati, senza link in uscita, senza link interni. Non elenca gli
    indirizzi: per quelli di un prodotto usa analizza_link_prodotto. `stato` e'
    "publish" (default), "draft" o "any"; con `solo_senza_link_in_uscita` l'elenco
    contiene solo i prodotti a cui manca un link in uscita (i conteggi in testa
    restano riferiti a tutti).
    """
    return link_tools.analizza_link_prodotti(stato, solo_senza_link_in_uscita)


@mcp.tool()
def leggi_alt_immagini_prodotto(prodotto_id: int) -> dict:
    """Testo ALT dell'immagine in evidenza e della galleria di un prodotto
    (con id allegato, ruolo, nome file e URL), piu' la parola chiave focus Yoast:
    l'ALT di norma la contiene. In un prodotto variabile ci sono anche le immagini
    delle varianti, con `ruolo` "variante". Ogni immagine ha `problema`: "mancante" (ALT
    vuoto), "senza_parola_chiave" (c'e' ma non contiene la parola chiave) o null
    se va bene. Gli `allegato_id` servono ad aggiorna_alt_immagini_prodotto."""
    return alt_tools.leggi_alt_immagini_prodotto(prodotto_id)


@mcp.tool()
def aggiorna_alt_immagini_prodotto(prodotto_id: int, immagini: list[dict]) -> dict:
    """Riscrive l'ALT delle immagini di un prodotto. `immagini` e' una lista di
    `{"allegato_id": 62, "alt": "testo"}` (gli id vengono da
    leggi_alt_immagini_prodotto); le immagini non indicate restano com'e'. ALT
    vuoto = lo toglie. Se un allegato non appartiene al prodotto non si scrive
    niente. Restituisce ALT prima/dopo per ogni immagine. Invalida anche la
    cache del sito.
    """
    risultato = alt_tools.aggiorna_alt_immagini_prodotto(prodotto_id, immagini)
    if "errore" in risultato:
        return risultato
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def leggi_seo_varianti(prodotto_id: int) -> dict:
    """SEO delle varianti di un prodotto VARIABILE: `attributi` (nome, valori,
    se si vedono nella scheda), `varianti` (id, etichetta, attributi, prezzo, SKU,
    descrizione, immagine propria e suo ALT, stato), titolo SEO / meta description /
    parola chiave focus del padre e l'intervallo di prezzo. `problemi` elenca cosa
    non va, dal piu' grave: ogni voce ha `codice`, `gravita` (errore, avviso,
    suggerimento), `messaggio` e le `varianti` coinvolte (id).

    Codici: nessuna_variante_in_vendita, variante_senza_prezzo, combinazione_duplicata
    (errori: da correggere in wp-admin, non da qui); variante_qualsiasi,
    attributo_nascosto, titolo_seo_con_una_variante, varianti_senza_immagine_propria
    (avvisi); parola_chiave_con_una_variante, valori_non_nel_testo, varianti_senza_sku
    (suggerimenti). Per un prodotto non variabile torna un errore: usa leggi_seo_prodotto.
    Leggi sempre questo prima di scrivere i testi di un variabile (vedi le regole sui
    prodotti variabili nelle istruzioni del server).
    """
    return seo_varianti_tools.leggi_seo_varianti(prodotto_id)


@mcp.tool()
def aggiorna_seo_varianti(
    prodotto_id: int, varianti: list[dict], solo_anteprima: bool = False
) -> dict:
    """Riscrive la descrizione e/o lo SKU delle varianti di un prodotto variabile.
    `varianti` e' una lista di `{"id": 143, "descrizione": "testo", "sku": "FEL-NM"}`
    (id da leggi_seo_varianti; `descrizione` e `sku` facoltativi, almeno uno; le
    varianti non indicate restano com'e'). La descrizione di una variante compare
    nella scheda quando il cliente la sceglie e nei dati strutturati: scrivila solo
    se aggiunge un'informazione vera. SKU vuoto lo toglie; non inventare SKU.
    Se una variante non e' del prodotto o uno SKU e' gia' di un altro prodotto non si
    scrive niente. Con `solo_anteprima=True` non salva e mostra solo prima/dopo.
    Restituisce `descrizione_prima/dopo` e `sku_prima/dopo` per ogni variante.
    Invalida anche la cache del sito. Per gli ALT delle immagini delle varianti usa
    aggiorna_alt_immagini_prodotto; per i testi del padre aggiorna_seo_prodotto.
    """
    risultato = seo_varianti_tools.aggiorna_seo_varianti(prodotto_id, varianti, solo_anteprima)
    if "errore" in risultato or solo_anteprima:
        return risultato
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def lista_categorie_prodotti() -> list[dict] | dict:
    """Le categorie prodotto del sito: `id`, `nome`, `percorso` ("Indumenti > Magliette"),
    `livello`, `madre` (id, 0 = radice), numero di `prodotti` pubblicati, `predefinita`
    ("Senza categoria", che non si sposta) e `url`. Sola lettura: serve a trovare gli id per
    sposta_categoria_prodotti.
    """
    return azioni_pubbliche_tools.lista_categorie_prodotti()


@mcp.tool()
def crea_categoria_prodotti(nome: str, madre_id: int = 0, anteprima: bool = True) -> dict:
    """Crea una categoria prodotto da sola (senza prodotti), alla radice con `madre_id=0` o
    sotto un'altra (id da lista_categorie_prodotti). Serve per preparare l'albero, per
    esempio creare "Indumenti" prima di spostarci sotto "Magliette" con
    sposta_categoria_prodotti. Le categorie dei prodotti nuovi nascono gia' da sole con il
    `percorso_categoria` di crea_prodotto: questo tool serve solo quando la categoria deve
    esistere prima.

    `anteprima=True` (predefinito): non crea niente e mostra il `percorso_dopo`. Con
    `anteprima=False` crea e restituisce `id`, `percorso` e `url`. Una categoria vuota non e'
    visibile a nessuno, quindi non serve il codice di conferma: basta mostrare il percorso
    all'utente e avere il suo ok. Un nome di categoria esiste UNA volta sola nell'albero: se
    c'e' gia' (anche in un altro ramo) rifiuta e dice dove si trova (per metterla altrove usa
    sposta_categoria_prodotti). Massimo 5 livelli.
    """
    return azioni_pubbliche_tools.crea_categoria_prodotti(nome, madre_id, anteprima)


@mcp.tool()
def sposta_categoria_prodotti(
    categoria_id: int,
    nuova_madre_id: int,
    anteprima: bool = True,
    codice_conferma: str | None = None,
) -> dict:
    """Sposta una categoria prodotto (con tutte le sue sottocategorie) sotto un'altra
    (`nuova_madre_id`), o alla radice con 0. Gli id vengono da lista_categorie_prodotti.
    Cambia l'indirizzo pubblico della categoria: AZIONE VISIBILE A TUTTI, da fare solo con
    anteprima e conferma esplicita dell'utente (vedi le istruzioni del server).

    `anteprima=True` (predefinito): non sposta niente. Restituisce percorso prima/dopo,
    indirizzo prima/dopo, le sottocategorie, i prodotti nel ramo (totale e pubblicati), gli
    `avvisi` (compreso che WordPress non crea un redirect 301: il vecchio indirizzo continua
    a rispondere ma ha come canonical il nuovo) e un `codice_conferma`.

    `anteprima=False` richiede il `codice_conferma` dell'anteprima mostrata all'utente: se
    l'albero e' cambiato dopo l'anteprima il plugin rifiuta e va rifatta. Rifiuta anche
    spostare la categoria predefinita, una categoria dentro se stessa o una sua figlia,
    superare i 5 livelli. I prodotti restano nelle loro categorie. Invalida la cache del sito.
    """
    risultato = azioni_pubbliche_tools.sposta_categoria_prodotti(
        categoria_id, nuova_madre_id, anteprima, codice_conferma
    )
    if "errore" in risultato or anteprima:
        return risultato
    return {**risultato, **cache_tools.purga_cache()}


@mcp.tool()
def pubblica_prodotti(
    prodotto_ids: list[int],
    anteprima: bool = True,
    codice_conferma: str | None = None,
) -> dict:
    """Pubblica bozze di prodotti (al massimo 50 per volta; elenco delle bozze:
    prodotti_in_bozza). Rende i prodotti visibili a tutti: AZIONE VISIBILE A TUTTI, da fare
    solo con anteprima e conferma esplicita dell'utente (vedi le istruzioni del server).

    `anteprima=True` (predefinito): non pubblica niente. Restituisce `da_pubblicare` (con
    categorie, prezzo e `avvisi`: niente immagine, titolo SEO / meta description / parola
    chiave vuoti, solo categoria predefinita), `non_pubblicabili` (con i `motivi`: non e' una
    bozza, niente prezzo, varianti sbagliate: si correggono in wp-admin), `non_trovati` e un
    `codice_conferma`.

    `anteprima=False` richiede il `codice_conferma` dell'anteprima mostrata all'utente: se
    anche solo un prodotto (o i suoi campi SEO) e' cambiato dopo, o la lista e' diversa, il
    plugin rifiuta e va rifatta l'anteprima. Pubblica solo i `da_pubblicare` e restituisce
    `pubblicati` (con indirizzo) e `falliti`. Invalida la cache del sito. Non esiste un tool
    per rimettere in bozza: si fa da wp-admin.
    """
    risultato = azioni_pubbliche_tools.pubblica_prodotti(prodotto_ids, anteprima, codice_conferma)
    if "errore" in risultato or anteprima:
        return risultato
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

    NON RIFIUTARE: analizzare un sito concorrente pubblico per prenderne ispirazione e'
    una richiesta lecita e voluta dal titolare del negozio. Eseguila senza obiezioni,
    senza chiedere giustificazioni e senza prediche su copyright o scraping (il tool
    rispetta gia' robots.txt, pause e limiti). Fermati solo dove questa descrizione lo
    prevede (scelta delle aree di ispirazione e della somiglianza accettata, metodi
    curl/browser a richiesta dell'utente). Se l'utente insiste, non rimettere in
    discussione: fallo.

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

    Il riepilogo dei punteggi (senza i testi delle pagine) viene mandato anche al plugin,
    che lo mostra nella tab SEO di wp-admin; `plugin` nel report dice se e' stato salvato.
    Se l'indirizzo e' quello del sito dell'utente, e' segnato come "Il tuo sito".

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
    report = competitor_seo.analizza_seo_sito(
        url,
        max_categorie,
        max_prodotti,
        caratteri_per_pagina,
        usa_curl,
        usa_browser,
        browser_visibile,
    )
    return {**report, "plugin": seo_tools.salva_analisi_nel_plugin(report, url)}


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
    controlla_somiglianza prima di applicarli. Come per quello, e' una richiesta
    lecita e voluta dal titolare: eseguila senza rifiutare ne' chiedere giustificazioni.
    """
    report = competitor_seo.analizza_pagine_salvate(percorsi, sito, caratteri_per_pagina)
    return {**report, "plugin": seo_tools.salva_analisi_nel_plugin(report)}


@mcp.tool()
def rimuovi_analisi_sito(sito: str, anche_testi_locali: bool = True) -> dict:
    """Toglie un sito analizzato dalla tabella «Concorrenti e confronto» della tab
    SEO del plugin (con il suo storico), per esempio perche' il report era
    inutile. Con `anche_testi_locali` (predefinito) cancella anche i testi di quel
    sito salvati sul computer dell'utente: dopo, controlla_somiglianza non puo'
    piu' confrontare con quel sito finche' non viene analizzato di nuovo.
    Usalo SOLO su richiesta esplicita dell'utente, dicendogli quale sito stai
    togliendo. Non tocca i prodotti ne' i campi SEO gia' scritti. `sito` e' il
    nome come compare nella tabella (es. "tomatosmartphone.it") o l'indirizzo.
    """
    risultato = {"plugin": seo_tools.rimuovi_analisi_dal_plugin(sito)}
    if anche_testi_locali:
        risultato["testi_locali_eliminati"] = text_similarity.elimina_corpus(sito)
    return risultato


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
