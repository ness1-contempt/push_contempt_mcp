from mcp import Client

from mio_mcp_server.server import mcp


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
            "lista_stato_seo_prodotti",
            "leggi_seo_prodotto",
            "aggiorna_seo_prodotto",
            "aggiorna_seo_categoria",
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
