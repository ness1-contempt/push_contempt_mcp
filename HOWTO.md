# Come installare tutto, da zero

Guida end-to-end: plugin WordPress `push_contempt` + server MCP
`push_contempt_mcp` + collegamento con l'assistente AI. Per i dettagli di
ciascun pezzo (tool disponibili, endpoint REST, struttura del codice) vedi
il `README.md` del repo corrispondente — questa guida copre solo l'ordine
dei passi.

## Prerequisiti

- WordPress 6.4+ con WooCommerce attivo (e idealmente [Yoast SEO](https://wordpress.org/plugins/wordpress-seo/),
  altrimenti i campi SEO restano inutilizzati).
- [`uv`](https://docs.astral.sh/uv/) per installare ed eseguire il server
  MCP (Python 3.13+ viene gestito da `uv` stesso, non serve installarlo a
  parte). Istruzioni di installazione per sistema:

  **Windows** (PowerShell):
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

  **macOS / Linux** (terminale):
  ```sh
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

- Un assistente AI con supporto MCP (Claude Code, Claude Desktop, Cursor,
  Windsurf, ...).
- Serve `git`/`node`/`npm` **solo** se si installa il plugin da sorgente
  (vedi passo 1, opzione B) — con lo zip pronto dalla pagina Releases non
  sono necessari.

## 1. Installare il plugin WordPress

**Opzione A — da wp-admin, senza terminale (consigliata):**

Dalla pagina **Releases** del repo `push_contempt` scarica
`push_contempt.zip` (già compilato). Poi wp-admin → Plugin → Aggiungi
nuovo → Carica plugin → seleziona lo zip → Installa → Attiva.

> Non funziona con "Code → Download ZIP" dalla pagina principale del
> repo: quello scarica il solo codice sorgente, senza la build dell'admin
> React — il plugin si attiva ma la sua pagina resta vuota. Va preso lo
> zip dalla pagina Releases.

**Opzione B — da sorgente** (per sviluppo, identica su Windows/macOS/Linux
una volta aperto un terminale nella cartella `wp-content/plugins`):

```sh
cd wp-content/plugins
git clone <url-repo-push_contempt> push_contempt
cd push_contempt
npm install
npm run build
```

In entrambi i casi, attiva "Push Contempt" da wp-admin → Plugin. Compare
la voce di menu "Push Contempt" (richiede la capability
`manage_woocommerce`).

## 2. Generare le credenziali

Nel menu "Push Contempt" → tab **Impostazioni**, premi "Genera
credenziali". Compaiono tre valori (`WP_SITE_URL`, `WP_APP_USER`,
`WP_APP_PASSWORD`): teneteli a portata, servono al passo 3. Sono
un'Application Password nativa di WordPress e non scadono da sole.

## 3. Installare il server MCP

Stessi comandi su Windows (PowerShell/CMD), macOS e Linux, da terminale:

```sh
git clone <url-repo-push_contempt_mcp>
cd push_contempt_mcp
uv sync
```

Copia `.env.example` in `.env`:

- Windows (PowerShell): `copy .env.example .env`
- macOS / Linux: `cp .env.example .env`

Apri `.env` e incolla i tre valori del passo 2 (`WP_SITE_URL`,
`WP_APP_USER`, `WP_APP_PASSWORD`). Gli altri campi (`WP_DB_*`,
`WP_ADMIN_*`) sono necessari solo per alcuni tool specifici — vedi la
sezione "Configurazione" del `README.md` di questo repo.

Se userai i tool che passano da automazione browser (modifica prezzo
singolo, SEO categoria), installa anche il browser di Playwright (stesso
comando su tutti i sistemi):

```sh
uv run playwright install chromium
```

## 4. Collegare l'assistente AI

Il repo contiene già un `.mcp.json` pronto: aprendo la cartella
`push_contempt_mcp` con **Claude Code**, il server viene rilevato in
automatico — su qualsiasi sistema operativo.

Per **Claude Desktop** o altri client, aggiungi lo stesso blocco al file
di configurazione del client. Il percorso del file cambia per sistema:

| Sistema | Percorso (Claude Desktop) |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "push_contempt_mcp": {
      "command": "uv",
      "args": ["run", "--directory", "<percorso-assoluto-a-push_contempt_mcp>", "push_contempt_mcp"]
    }
  }
}
```

Il `<percorso-assoluto-a-push_contempt_mcp>` va scritto nel formato del
proprio sistema, es. `C:\Utenti\nome\push_contempt_mcp` su Windows o
`/home/nome/push_contempt_mcp` su macOS/Linux.

## 5. Verifica

Chiedi all'assistente AI di controllare le scorte sotto soglia o lo stato
SEO del catalogo (tool `prodotti_sotto_scorta` / `lista_stato_seo_prodotti`):
se risponde con dati reali del sito, il collegamento funziona.
