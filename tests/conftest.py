import pytest


@pytest.fixture(autouse=True)
def _senza_rete_per_le_categorie(monkeypatch):
    """La scansione delle cartelle confronta le categorie col sito: nei test non si
    chiama mai il sito vero. Ogni percorso risulta tutto da creare; i test che
    vogliono un'altra risposta sostituiscono questa funzione."""
    from push_contempt_mcp import product_tools

    def finta(percorsi):
        return {
            "percorsi": [
                {
                    "percorso": p,
                    "livelli": [
                        {
                            "nome": n,
                            "stato": "da_creare",
                            "id": None,
                            "percorso": " > ".join(p[: i + 1]),
                        }
                        for i, n in enumerate(p)
                    ],
                    "errori": [],
                }
                for p in percorsi
            ],
            "conflitti_tra_percorsi": [],
            "conflitti": [],
        }

    monkeypatch.setattr(product_tools, "verifica_categorie", finta)
