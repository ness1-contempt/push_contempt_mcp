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
