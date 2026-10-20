# push_contempt_mcp

Server MCP in Python (SDK `mcp` 2.x, classe `MCPServer`) per gestire un
catalogo WooCommerce: lettura dati via DB diretto, scritture sensibili
(prezzo, creazione prodotto) via browser automation su wp-admin, SEO via
i campi di Yoast.

## Configurazione

Copia `.env.example` in `.env` e compila le credenziali del DB WordPress
(`WP_DB_*`), l'URL del sito (`WP_SITE_URL`) e le credenziali admin per
l'automazione browser (`WP_ADMIN_USER`, `WP_ADMIN_PASSWORD`). Il browser
Playwright gira in modalità **headed** (non headless): su questo host la
build Chromium "fallback" (OS non ufficialmente supportato) ha problemi di
rendering in headless, vedi i commenti in `browser_tools.py`. Serve quindi
un display disponibile (`DISPLAY`).

## Tool disponibili

- `lista_prodotti` — lettura diretta dal DB: titolo, sku, prezzo, scorte.
- `crea_prodotto` — crea e pubblica un prodotto via wp-admin (titolo,
  descrizione, prezzo, categoria, immagini: la prima diventa quella in
  evidenza, le altre vanno in galleria). SEO (titolo SEO, meta description,
  parola chiave focus) e ALT delle immagini vengono impostati in automatico
  nella stessa chiamata, niente passi separati dopo la creazione. La risposta
  include `avvisi_seo` (densita' frase chiave, sottotitoli H2/H3, link
  interni) da controllare prima di considerare il prodotto finito.
- `prepara_modifica_prezzo_prodotto` / `conferma_modifica_in_corso` /
  `annulla_modifica_in_corso` — modifica prezzo in due fasi (compila e
  mostra uno screenshot da controllare, poi salva o scarta).
- `lista_stato_seo_prodotti` / `leggi_seo_prodotto` / `aggiorna_seo_prodotto`
  — lettura/scrittura di titolo SEO, meta description e parola chiave focus
  (campi Yoast) sui prodotti, via DB diretto. Solo I/O: l'ottimizzazione dei
  testi la fa chi chiama i tool.
- `aggiorna_seo_categoria` — stessa cosa ma per le categorie prodotto
  (tassonomia `product_cat`), via browser: per i termini di tassonomia Yoast
  non rilegge i campi scritti via DB diretto (vedi Note).

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
- `src/push_contempt_mcp/db.py` — connessione MySQL (letture dirette, a basso rischio)
- `src/push_contempt_mcp/browser_tools.py` — automazione Playwright per le scritture
  sensibili su wp-admin (prezzo, creazione prodotto)
- `src/push_contempt_mcp/seo_tools.py` — lettura/scrittura campi SEO Yoast
- `src/push_contempt_mcp/__init__.py` — `main()`, entry point
- `tests/` — test in-process con `mcp.Client(mcp)`
- `.mcp.json` — registra il server in Claude Code quando apri questa cartella

## Note

- Con trasporto stdio **non usare `print()`**: stdout è riservato al protocollo. Usa `logging`.
- SDK 2.x: `FastMCP` è stato rinominato `MCPServer` (`from mcp.server.mcpserver import MCPServer`).
  Molti esempi online sono ancora per la v1.
- Per Claude Desktop aggiungi lo stesso blocco di `.mcp.json` a `~/.config/Claude/claude_desktop_config.json`.
- Dopo scritture dirette sul DB (bypassano gli hook di WordPress) vanno svuotate
  a mano: la cache oggetti Redis (`redis-cli FLUSHALL`), la LiteSpeed Cache
  (`wp eval 'do_action("litespeed_purge_all");'`) e, se tocchi campi Yoast, la
  sua tabella indicizzata (`wp yoast index --reindex --skip-confirmation`) —
  altrimenti il sito continua a servire contenuti vecchi anche a dati aggiornati.
- Per i **termini di tassonomia** (categorie prodotto) `wp yoast index --reindex`
  non basta: l'indicizzabile Yoast del termine resta vuoto anche dopo, a
  prescindere da reindex/cache flush/`wp term update`. L'unico modo affidabile
  trovato è salvare davvero dalla UI di modifica categoria (da cui
  `aggiorna_seo_categoria`, via browser, non DB diretto) — i campi titolo/meta
  description li lì sono editor Draft.js, non `<input>`, vanno riempiti
  cliccando + selezionando tutto + ridigitando, non con `.fill()`.
- Per le **pagine** (es. la pagina Shop) il DB diretto funziona, ma a volte
  `wp yoast index --reindex` da solo non rigenera l'indicizzabile: in quel
  caso un `wp post update <id> --post_title=<stesso titolo>` (che attiva i
  hook reali di WordPress) forza la ricostruzione corretta.
