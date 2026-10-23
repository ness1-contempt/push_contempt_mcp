# push_contempt_mcp

Server MCP in Python (SDK `mcp` 2.x, classe `MCPServer`) per gestire un
catalogo WooCommerce da un assistente AI (Claude Code e altri client MCP),
in coppia con il plugin WordPress `push_contempt` (repo separato). La
maggior parte dei tool sono client sottili della REST API di quel plugin
(nessun accesso diretto al DB, funziona anche su hosting che blocca
connessioni MySQL esterne); un numero ridotto di operazioni passa invece
da automazione browser (Playwright) su wp-admin, quando serve poter
rivedere una modifica prima che diventi effettiva; la lettura veloce del
catalogo (`lista_prodotti`) resta su accesso diretto al DB.

Per l'installazione completa (plugin + server + collegamento con
l'assistente AI, in ordine) vedi [`HOWTO.md`](HOWTO.md).

## Configurazione

Copia `.env.example` in `.env` e compila:

- `WP_SITE_URL` — URL del sito WordPress.
- `WP_APP_USER` / `WP_APP_PASSWORD` — Application Password di WordPress
  (wp-admin → Utenti → Profilo → Password per le applicazioni), usata dalla
  maggior parte dei tool per chiamare la REST API del plugin
  `push_contempt`. Il plugin la genera in automatico dal tab
  "Impostazioni" (un click, non serve WP-CLI). Le Application Password
  native di WordPress non scadono da sole.
- `WP_DB_*` — credenziali MySQL dirette, usate solo da `lista_prodotti`
  (lettura) e dalla scansione della cartella prodotti (confronto nomi).
- `WP_ADMIN_USER` / `WP_ADMIN_PASSWORD` — credenziali di login wp-admin,
  usate solo dai tool che passano da automazione browser (modifica prezzo
  singolo con anteprima, SEO categoria). Il browser Playwright gira in
  modalità **headed** (non headless): su alcuni host la build Chromium
  "fallback" (OS non ufficialmente supportato) ha problemi di rendering in
  headless, vedi i commenti in `browser_tools.py`. Serve quindi un display
  disponibile (`DISPLAY`).

  **Sessione e captcha:** il login passa da una sessione salvata in
  `.auth/wp_admin_state.json` (permessi 600, in `.gitignore`): finche' il
  cookie e' valido non si rifa' il login, nemmeno dopo un riavvio del server.
  Se serve un nuovo login, la somma Jetpack Protect viene risolta da sola,
  mentre il reCAPTCHA "Non sono un robot" va spuntato a mano nella finestra
  del browser (si aspetta fino a 2 minuti).

## Tool disponibili

**Catalogo**
- `lista_prodotti` — ricerca testuale nel catalogo (lettura diretta dal DB:
  titolo, sku, prezzo, scorte).
- `controllo_salute_catalogo` — prodotti pubblicati ma incompleti (nessuna
  immagine in evidenza, nessuna categoria, prezzo non valido, descrizione
  troppo corta).
- `prodotti_sotto_scorta` — prodotti esauriti o sotto una soglia di scorte.
- `report_vendite_prodotti` — più venduti e mai venduti in un periodo.

**Ordini** (sola lettura, richiedono il plugin ≥ della versione che include
`/ordini`)
- `lista_ordini` — ordini filtrabili per stato WooCommerce (`pending`,
  `processing`, `on-hold`, `completed`, `cancelled`, `refunded`, `failed`; non
  esiste uno stato "evaso") e per finestra temporale (`ultime_ore`,
  `piu_vecchi_di_ore`, `da`/`a`). L'elenco non contiene dati personali oltre
  alla città di spedizione.
- `dettaglio_ordine` — un singolo ordine con righe, importi, date e dati del
  cliente (nome, email, telefono, indirizzi).

**Creazione prodotti**
- `scansiona_cartella_prodotti` — confronta una cartella locale
  (`<Categoria>/<Prodotto>/`, foto + `.txt`) con il catalogo, separa i
  prodotti nuovi da quelli già presenti.
- `crea_prodotto` — crea un prodotto WooCommerce **in bozza** (titolo,
  descrizione, prezzo, categoria, immagini: la prima diventa quella in
  evidenza, le altre vanno in galleria), con SEO e ALT delle immagini già
  impostati nella stessa chiamata. Non viene mai pubblicato in automatico:
  resta da rivedere e pubblicare da wp-admin. La risposta include
  `avvisi_seo` (densità frase chiave, sottotitoli H2/H3, link interni) da
  controllare prima di considerare il prodotto pronto.
- `prodotti_in_bozza` — elenco dei prodotti creati e non ancora pubblicati.

**Prezzi**
- `calcola_aggiornamento_prezzi` / `applica_aggiornamento_prezzi` —
  aggiornamento prezzi in blocco per categoria (percentuale o delta fisso),
  con anteprima da far approvare prima di scrivere.
- `prepara_modifica_prezzo_prodotto` / `conferma_modifica_in_corso` /
  `annulla_modifica_in_corso` — modifica prezzo di un singolo prodotto in
  due fasi via browser (compila e mostra uno screenshot da controllare,
  poi salva o scarta).

**SEO**
- `lista_stato_seo_prodotti` — vista d'insieme: titolo SEO e meta
  description impostati o mancanti su tutto il catalogo.
- `leggi_seo_prodotto` / `leggi_seo_prodotti_selezionati` /
  `aggiorna_seo_prodotto` — lettura/scrittura dei campi Yoast (titolo SEO,
  meta description, parola chiave focus) di uno o più prodotti. Solo I/O:
  l'ottimizzazione dei testi la fa chi chiama i tool.
- `aggiorna_seo_categoria` — stessa cosa per le categorie prodotto
  (tassonomia `product_cat`), via browser: per i termini di tassonomia
  Yoast non rilegge i campi scritti via REST/DB diretto (vedi Note).
- `analizza_seo_sito` — analisi a campione del sito di un altro negozio per
  capire come è fatta la sua SEO e come descrive i prodotti (home, sitemap,
  qualche categoria, una decina di prodotti). Oltre ai campi SEO (titoli,
  meta description, H1/H2, dati strutturati) analizza il testo: vocabolario
  (parole e coppie di parole ricorrenti, unità di misura), segnali di stile
  e intenzione ogni 1000 parole (inviti all'acquisto, fiducia e servizio,
  offerte, confronto e guida, tono "tu"/"noi", tecnicismo, lunghezza delle
  frasi), struttura delle descrizioni e un breve estratto per pagina
  (`caratteri_per_pagina`, 600 di default: è quello che pesa sui token), così
  l'assistente giudica intenzione e tono. Le formule ripetute su tutto il sito
  (spedizioni, resi, "aggiungi al carrello") sono separate dai contenuti. Gira
  sul tuo PC, non sul sito WordPress; rispetta `robots.txt`, fa una pausa fra le
  richieste. Metodi, dal più leggero: HTTP; se la home risponde 403/429 o è
  costruita con JavaScript e il browser è attivo (`SEO_ANALISI_USA_BROWSER=1` o
  `usa_browser`), dopo aver aspettato il `Retry-After` si passa a un Chromium vero in
  locale; se non basta, `analizza_pagine_salvate`. Il report dice il `metodo` usato.
  Con `usa_curl` (scelta esplicita dell'utente) fa
  le richieste con il programma `curl`, sempre con il nostro User-Agent dichiarato; se
  il sito risponde ancora 429 si ferma, non aggira i blocchi. Rifiuta reti private; per provarlo su un
  sito locale `SEO_ANALISI_CONSENTI_RETE_PRIVATA=1`. Vocabolario ed estratti
  servono ad analizzare: i testi nostri vanno scritti con parole proprie.
- `analizza_pagine_salvate` — la stessa analisi su pagine `.html` salvate
  dall'utente dal proprio browser (file o cartelle), senza nessuna richiesta
  di rete: per i siti che bloccano gli strumenti automatici o si costruiscono
  con JavaScript.
- `controlla_somiglianza` — misura quanto un testo nostro somiglia ai testi di
  un sito analizzato con `analizza_seo_sito` (salvati in locale dopo ogni
  analisi) o a testi dati a mano, su una scala da 0 (nessuna somiglianza) a 9
  (copia). Si basa su sequenze di almeno 5 parole consecutive in comune e
  restituisce punteggio, significato, passaggi coincidenti e fonti più simili.
  La `soglia` (0-9) è il massimo che l'utilizzatore accetta: con essa il
  risultato dice anche se il testo è accettabile. Specifiche tecniche uguali
  alzano un po' il punteggio anche in testi originali, per questo i passaggi
  sono elencati e il giudizio finale resta all'utilizzatore. Il punteggio è solo
  un riferimento, non vincolante: va mostrato all'utente e il livello accettato
  scelto da lui prima di applicare qualsiasi modifica ai prodotti.
- La `valutazione` che `analizza_seo_sito` e `analizza_pagine_salvate` aggiungono al report
  (modulo `seo_scorecard.py`) dà alla struttura SEO del sito analizzato un punteggio da 0 a 9
  per area (titoli, meta description, intestazioni, dati strutturati, contenuto, aspetti
  tecnici) e complessivo, con la prova di ogni criterio. Dice se il sito è un buon modello
  da cui prendere spunto: è solo un riferimento, e un sito scadente può essere buono su
  un'area. Le soglie (lunghezze di titolo e meta, parole minime) sono costanti in testa al
  modulo. Prima di proporre testi, all'utente vanno mostrati punteggio e aree, e lui decide
  se e per quali aree usare il sito come ispirazione.

**Manutenzione**
- `purga_cache_sito` — invalida manualmente la cache del sito (gli altri
  tool di scrittura la chiamano già in automatico dove serve).

## Comandi

| Cosa | Comando |
|---|---|
| Installare/aggiornare le dipendenze | `uv sync` |
| Avviare il server (stdio) | `uv run push_contempt_mcp` |
| Test | `uv run pytest` |
| Lint / format | `uv run ruff check --fix . && uv run ruff format .` |
| Provarlo con MCP Inspector (UI web) | `npx -y @modelcontextprotocol/inspector uv run push_contempt_mcp` |
| Aggiungere una dipendenza | `uv add <pacchetto>` |

## Struttura

- `src/push_contempt_mcp/server.py` — registrazione dei tool, resource e prompt MCP
- `src/push_contempt_mcp/db.py` — connessione MySQL diretta, usata solo dove serve davvero (lettura veloce, scansione cartella)
- `src/push_contempt_mcp/product_tools.py` — creazione prodotto: client REST + upload immagini su `/wp/v2/media`
- `src/push_contempt_mcp/pricing_tools.py` — aggiornamento prezzi in blocco: client REST
- `src/push_contempt_mcp/inventory_tools.py` — scorte: client REST
- `src/push_contempt_mcp/order_tools.py` — ordini: client REST
- `src/push_contempt_mcp/sales_tools.py` — report vendite: client REST
- `src/push_contempt_mcp/catalog_health.py` — salute catalogo: client REST
- `src/push_contempt_mcp/seo_tools.py` — lettura/scrittura campi SEO Yoast: client REST
- `src/push_contempt_mcp/competitor_seo.py` — scarico e campione di pagine di un sito concorrente, campi SEO (solo libreria standard + `requests`)
- `src/push_contempt_mcp/seo_scorecard.py` — valutazione 0-9 per area della struttura SEO di un sito analizzato
- `src/push_contempt_mcp/text_similarity.py` — controllo di somiglianza 0-9 fra un nostro testo e quelli analizzati (cache locale dei testi dei concorrenti)
- `src/push_contempt_mcp/competitor_text.py` — analisi del testo di quelle pagine: template, vocabolario, segnali di stile e intenzione
- `src/push_contempt_mcp/product_sync.py` — scansione cartella prodotti locale (lettura diretta dal DB, solo confronto nomi)
- `src/push_contempt_mcp/browser_tools.py` — automazione Playwright per le operazioni ancora manuali (prezzo singolo con anteprima, SEO categoria)
- `src/push_contempt_mcp/cache_tools.py` — invalidazione cache del sito dopo una scrittura
- `src/push_contempt_mcp/__init__.py` — `main()`, entry point
- `tests/` — test in-process con `mcp.Client(mcp)` per il server, test unitari a `requests` mockato per i client REST
- `.mcp.json` — registra il server in Claude Code quando apri questa cartella

## Note

- Con trasporto stdio **non usare `print()`**: stdout è riservato al protocollo. Usa `logging`.
- SDK 2.x: `FastMCP` è stato rinominato `MCPServer` (`from mcp.server.mcpserver import MCPServer`).
  Molti esempi online sono ancora per la v1.
- Per Claude Desktop aggiungi lo stesso blocco di `.mcp.json` a `~/.config/Claude/claude_desktop_config.json`.
- Per i **termini di tassonomia** (categorie prodotto) `wp yoast index --reindex`
  non basta: l'indicizzabile Yoast del termine resta vuoto anche dopo, a
  prescindere da reindex/cache flush/`wp term update`. L'unico modo affidabile
  trovato è salvare davvero dalla UI di modifica categoria (da cui
  `aggiorna_seo_categoria`, via browser) — i campi titolo/meta
  description lì sono editor Draft.js, non `<input>`, vanno riempiti
  cliccando + selezionando tutto + ridigitando, non con `.fill()`.
