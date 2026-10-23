import json

from mcp import Client

from push_contempt_mcp.server import mcp


async def test_list_tools():
    async with Client(mcp) as client:
        result = await client.list_tools()
        assert {t.name for t in result.tools} == {
            "somma",
            "saluta",
            "lista_prodotti",
            "crea_prodotto",
            "prepara_modifica_prezzo_prodotto",
            "conferma_modifica_in_corso",
            "annulla_modifica_in_corso",
            "controllo_salute_catalogo",
            "report_vendite_prodotti",
            "prodotti_sotto_scorta",
            "prodotti_in_bozza",
            "scansiona_cartella_prodotti",
            "leggi_seo_prodotti_selezionati",
            "calcola_aggiornamento_prezzi",
            "applica_aggiornamento_prezzi",
            "purga_cache_sito",
            "lista_stato_seo_prodotti",
            "leggi_seo_prodotto",
            "aggiorna_seo_prodotto",
            "aggiorna_seo_categoria",
            "leggi_analisi_seo_yoast",
            "analizza_seo_sito",
            "controlla_somiglianza",
            "lista_ordini",
            "dettaglio_ordine",
        }


async def test_somma():
    async with Client(mcp) as client:
        result = await client.call_tool("somma", {"a": 2, "b": 3})
        assert not result.is_error
        assert result.structured_content == {"result": 5}


async def test_saluta_formale():
    async with Client(mcp) as client:
        result = await client.call_tool("saluta", {"nome": "Andrea", "formale": True})
        assert result.content[0].text == "Buongiorno, Andrea."


def _json(risultato) -> dict:
    """Risultato di un tool che restituisce un dict: l'SDK lo manda come testo JSON."""
    assert not risultato.is_error
    return json.loads(risultato.content[0].text)


async def test_controlla_somiglianza_via_mcp(monkeypatch, tmp_path):
    monkeypatch.setenv("SEO_ANALISI_CACHE_DIR", str(tmp_path / "vuota"))
    testo = "Il display amoled da 6,7 pollici a 120 hz rende fluida ogni schermata del telefono."
    async with Client(mcp) as client:
        copia = await client.call_tool(
            "controlla_somiglianza", {"testo": testo, "riferimenti": [testo], "soglia": 3}
        )
        assert not copia.is_error
        assert _json(copia)["punteggio"] == 9
        assert _json(copia)["accettabile"] is False
        assert _json(copia)["fonti_piu_simili"][0]["fonte"] == "riferimento 1"

        diverso = await client.call_tool(
            "controlla_somiglianza",
            {"testo": testo, "riferimenti": ["Tutt'altro argomento, nessuna parola uguale qui."]},
        )
        assert _json(diverso)["punteggio"] == 0
        assert "accettabile" not in _json(diverso)  # senza soglia nessun verdetto

        fuori_scala = await client.call_tool(
            "controlla_somiglianza", {"testo": testo, "riferimenti": [testo], "soglia": 10}
        )
        assert _json(fuori_scala) == {"errore": "La soglia va da 0 a 9."}

        senza_riferimenti = await client.call_tool("controlla_somiglianza", {"testo": testo})
        assert "analizza_seo_sito" in _json(senza_riferimenti)["errore"]
