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

## Tool disponibili

**Catalogo**
- `lista_prodotti` — ricerca testuale nel catalogo (lettura diretta dal DB:
  titolo, sku, prezzo, scorte).
- `controllo_salute_catalogo` — prodotti pubblicati ma incompleti (nessuna
  immagine in evidenza, nessuna categoria, prezzo non valido, descrizione
  troppo corta).
- `prodotti_sotto_scorta` — prodotti esauriti o sotto una soglia di scorte.
- `report_vendite_prodotti` — più venduti e mai venduti in un periodo.

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
- `src/push_contempt_mcp/sales_tools.py` — report vendite: client REST
- `src/push_contempt_mcp/catalog_health.py` — salute catalogo: client REST
- `src/push_contempt_mcp/seo_tools.py` — lettura/scrittura campi SEO Yoast: client REST
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
