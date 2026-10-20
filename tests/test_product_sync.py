from pathlib import Path

from push_contempt_mcp import product_sync
from push_contempt_mcp.product_sync import _normalizza_nome, scansiona_cartella_prodotti


def test_normalizza_nome_ignora_maiuscole_accenti_punteggiatura():
    assert _normalizza_nome("Sedia da Giardino") == _normalizza_nome("sedia-da-giardino")
    assert _normalizza_nome("Poltrona Relax") == _normalizza_nome("poltróna  relax!")


def _crea_prodotto(tmp_path: Path, categoria: str, nome: str, con_foto: bool, con_txt: bool):
    cartella = tmp_path / categoria / nome
    cartella.mkdir(parents=True)
    if con_foto:
        (cartella / "foto1.jpg").write_bytes(b"fake")
    if con_txt:
        (cartella / "specifiche.txt").write_text("Prezzo: 19.90\nDescrizione: ottimo prodotto.")


def test_scansiona_cartella_prodotti_separa_nuovi_e_esistenti(tmp_path, monkeypatch):
    _crea_prodotto(tmp_path, "Sedie", "Sedia da Giardino", con_foto=True, con_txt=True)
    _crea_prodotto(tmp_path, "Sedie", "Sedia Ufficio", con_foto=True, con_txt=True)

    monkeypatch.setattr(
        product_sync, "_nomi_prodotti_esistenti", lambda: {_normalizza_nome("Sedia Ufficio")}
    )

    risultato = scansiona_cartella_prodotti(str(tmp_path))

    assert risultato["gia_presenti"] == ["Sedia Ufficio"]
    assert len(risultato["nuovi"]) == 1
    nuovo = risultato["nuovi"][0]
    assert nuovo["nome"] == "Sedia da Giardino"
    assert nuovo["categoria"] == "Sedie"
    assert len(nuovo["percorsi_immagini"]) == 1
    assert "Prezzo: 19.90" in nuovo["testo_grezzo"]
    assert nuovo["avviso"] is None


def test_scansiona_cartella_prodotti_segnala_materiali_mancanti(tmp_path, monkeypatch):
    _crea_prodotto(tmp_path, "Tavoli", "Tavolo Rotondo", con_foto=False, con_txt=True)
    monkeypatch.setattr(product_sync, "_nomi_prodotti_esistenti", lambda: set())

    risultato = scansiona_cartella_prodotti(str(tmp_path))

    assert risultato["nuovi"][0]["avviso"] is not None


def test_scansiona_cartella_prodotti_cartella_inesistente():
    risultato = scansiona_cartella_prodotti("/percorso/che/non/esiste")
    assert "errore" in risultato
