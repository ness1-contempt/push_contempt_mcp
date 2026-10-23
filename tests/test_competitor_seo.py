import pytest
import requests

from push_contempt_mcp import competitor_seo, text_similarity
from push_contempt_mcp.competitor_seo import (
    ErroreAnalisi,
    _campiona,
    _controlla_destinazione,
    _estrai_pagina,
    _normalizza_url,
    _Risposta,
    _scarica_grezzo,
    _Scaricatore,
    _schema_titolo,
    _tipi_schema,
    analizza_seo_sito,
)


@pytest.fixture(autouse=True)
def _senza_pause_e_rete_privata(monkeypatch, tmp_path):
    monkeypatch.setattr(competitor_seo, "PAUSA_SECONDI", 0)
    monkeypatch.delenv("SEO_ANALISI_CONSENTI_RETE_PRIVATA", raising=False)
    monkeypatch.delenv("SEO_ANALISI_USA_BROWSER", raising=False)
    monkeypatch.setenv("SEO_ANALISI_CACHE_DIR", str(tmp_path / "cache"))  # mai la cache vera


# --- rete -------------------------------------------------------------------


class _RispostaHttpFinta:
    def __init__(self, status_code=200, headers=None, corpo=b"", encoding="utf-8"):
        self.status_code = status_code
        self.headers = {"Content-Type": "text/html", **(headers or {})}
        self.encoding = encoding
        self._corpo = corpo
        self.chiusa = False

    def iter_content(self, dimensione):
        for i in range(0, len(self._corpo), dimensione):
            yield self._corpo[i : i + dimensione]

    def close(self):
        self.chiusa = True


def _pubblico(monkeypatch):
    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: ["93.184.216.34"])


def test_normalizza_url_aggiunge_https_e_rifiuta_schemi_strani():
    assert _normalizza_url(" esempio.it ") == "https://esempio.it/"
    assert _normalizza_url("http://esempio.it/x") == "http://esempio.it/x"
    for url in ("", "ftp://esempio.it", "file:///etc/passwd"):
        with pytest.raises(ErroreAnalisi):
            _normalizza_url(url)


@pytest.mark.parametrize(
    "indirizzo", ["127.0.0.1", "192.168.1.10", "10.0.0.5", "169.254.169.254", "::1"]
)
def test_rifiuta_reti_private(monkeypatch, indirizzo):
    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: [indirizzo])
    with pytest.raises(ErroreAnalisi, match="rete privata"):
        _controlla_destinazione("https://esempio.it")


def test_rete_privata_consentita_solo_con_variabile_esplicita(monkeypatch):
    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: ["127.0.0.1"])
    monkeypatch.setenv("SEO_ANALISI_CONSENTI_RETE_PRIVATA", "1")
    _controlla_destinazione("https://localhost")  # non solleva


def test_scarica_grezzo_segue_redirect_sullo_stesso_dominio(monkeypatch):
    _pubblico(monkeypatch)
    risposte = iter(
        [
            _RispostaHttpFinta(301, {"Location": "https://www.esempio.it/ciao"}),
            _RispostaHttpFinta(200, corpo=b"<html>ok</html>"),
        ]
    )
    richieste = []

    def get_finto(url, **kwargs):
        richieste.append((url, kwargs["allow_redirects"], kwargs["headers"]["User-Agent"]))
        return next(risposte)

    monkeypatch.setattr(requests, "get", get_finto)

    risposta = _scarica_grezzo("https://esempio.it/", "esempio.it")

    assert risposta.status == 200
    assert risposta.url == "https://www.esempio.it/ciao"
    assert risposta.testo == "<html>ok</html>"
    assert [r[0] for r in richieste] == ["https://esempio.it/", "https://www.esempio.it/ciao"]
    assert all(r[1] is False and "push_contempt_mcp-seo" in r[2] for r in richieste)


def test_scarica_grezzo_rifiuta_redirect_verso_altro_dominio(monkeypatch):
    _pubblico(monkeypatch)
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, **kw: _RispostaHttpFinta(302, {"Location": "https://altro.example/"}),
    )
    with pytest.raises(ErroreAnalisi, match="altro dominio"):
        _scarica_grezzo("https://esempio.it/", "esempio.it")


def test_scarica_grezzo_ricontrolla_la_destinazione_a_ogni_redirect(monkeypatch):
    indirizzi = {"esempio.it": ["93.184.216.34"], "www.esempio.it": ["10.0.0.1"]}
    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: indirizzi[host])
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, **kw: _RispostaHttpFinta(301, {"Location": "https://www.esempio.it/"}),
    )
    with pytest.raises(ErroreAnalisi, match="rete privata"):
        _scarica_grezzo("https://esempio.it/", "esempio.it")


def test_scarica_grezzo_rifiuta_contenuti_non_testuali(monkeypatch):
    _pubblico(monkeypatch)
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, **kw: _RispostaHttpFinta(200, {"Content-Type": "image/png"}, b"\x89PNG"),
    )
    with pytest.raises(ErroreAnalisi, match="non testuale"):
        _scarica_grezzo("https://esempio.it/x.png", "esempio.it")


def test_scarica_grezzo_tronca_le_risposte_enormi(monkeypatch):
    _pubblico(monkeypatch)
    enorme = b"a" * (competitor_seo.MAX_BYTE * 2)
    monkeypatch.setattr(requests, "get", lambda url, **kw: _RispostaHttpFinta(200, corpo=enorme))
    risposta = _scarica_grezzo("https://esempio.it/", "esempio.it")
    assert len(risposta.testo) == competitor_seo.MAX_BYTE


def test_scarica_grezzo_chiude_sempre_la_risposta_e_traduce_gli_errori(monkeypatch):
    _pubblico(monkeypatch)
    finta = _RispostaHttpFinta(200, corpo=b"x")
    monkeypatch.setattr(requests, "get", lambda url, **kw: finta)
    _scarica_grezzo("https://esempio.it/", "esempio.it")
    assert finta.chiusa

    def get_che_fallisce(url, **kw):
        raise requests.ConnectTimeout()

    monkeypatch.setattr(requests, "get", get_che_fallisce)
    with pytest.raises(ErroreAnalisi, match="ConnectTimeout"):
        _scarica_grezzo("https://esempio.it/", "esempio.it")


# --- robots.txt -------------------------------------------------------------


def _sito_finto(monkeypatch, pagine: dict[str, tuple[int, str]]):
    """Sostituisce _scarica_grezzo con un dizionario url -> (status, testo);
    registra gli URL richiesti nell'ordine."""
    richieste: list[str] = []

    def finto(url, host_base):
        richieste.append(url)
        status, testo = pagine.get(url, (404, ""))
        return _Risposta(status, url, testo)

    monkeypatch.setattr(competitor_seo, "_scarica_grezzo", finto)
    return richieste


def test_robots_vieta_un_percorso(monkeypatch):
    _sito_finto(
        monkeypatch,
        {"https://esempio.it/robots.txt": (200, "User-agent: *\nDisallow: /privato/\n")},
    )
    scaricatore = _Scaricatore("https://esempio.it/")
    scaricatore.carica_robots()
    with pytest.raises(ErroreAnalisi, match="vietato da robots.txt"):
        scaricatore.get("https://esempio.it/privato/pagina")


def test_robots_assente_non_pone_restrizioni(monkeypatch):
    _sito_finto(monkeypatch, {"https://esempio.it/x": (200, "ciao")})
    scaricatore = _Scaricatore("https://esempio.it/")
    scaricatore.carica_robots()  # robots.txt -> 404
    assert scaricatore.get("https://esempio.it/x").testo == "ciao"


def test_robots_con_errore_del_server_ferma_l_analisi(monkeypatch):
    _sito_finto(monkeypatch, {"https://esempio.it/robots.txt": (503, "")})
    with pytest.raises(ErroreAnalisi, match="robots.txt non leggibile"):
        _Scaricatore("https://esempio.it/").carica_robots()


def test_robots_crawl_delay_alza_la_pausa_con_un_tetto(monkeypatch):
    monkeypatch.setattr(competitor_seo, "PAUSA_SECONDI", 1.0)
    _sito_finto(
        monkeypatch,
        {"https://esempio.it/robots.txt": (200, "User-agent: *\nCrawl-delay: 60\n")},
    )
    scaricatore = _Scaricatore("https://esempio.it/")
    scaricatore.carica_robots()
    assert scaricatore._pausa == competitor_seo.PAUSA_MASSIMA_SECONDI


def test_robots_elenca_le_sitemap_dichiarate(monkeypatch):
    _sito_finto(
        monkeypatch,
        {"https://esempio.it/robots.txt": (200, "Sitemap: https://esempio.it/mappa.xml\n")},
    )
    scaricatore = _Scaricatore("https://esempio.it/")
    scaricatore.carica_robots()
    assert scaricatore.sitemap_dichiarate == ["https://esempio.it/mappa.xml"]


# --- estrazione dalla pagina ------------------------------------------------

PAGINA = """<!doctype html>
<html lang="it"><head>
<title>Smartphone Nothing Phone 2 | Negozio Esempio</title>
<meta name="description" content="Scopri Nothing Phone 2: scheda tecnica e prezzo.">
<meta name="robots" content="index, follow">
<meta property="og:title" content="Nothing Phone 2">
<link rel="canonical" href="https://esempio.it/prodotto/nothing-phone-2/">
<script type="application/ld+json">
{"@context": "https://schema.org", "@graph": [
  {"@type": "Product", "name": "Nothing Phone 2", "offers": {"@type": "Offer"}},
  {"@type": ["BreadcrumbList"]}
]}
</script>
<script type="application/ld+json">{ rotto</script>
<style>.x { color: red }</style>
</head><body>
<header><nav><a href="/">Home</a> parole del menu da non contare</nav></header>
<main>
  <h1>Nothing Phone 2</h1>
  <h2>Scheda tecnica</h2><h2>Scheda   tecnica</h2><h3>Display</h3>
  <p>Un telefono con display luminoso e batteria che dura due giorni.</p>
  <img src="a.jpg" alt="Fronte"><img src="b.jpg"><img src="c.jpg" alt="  ">
  <a href="/categoria-prodotto/telefoni/">Telefoni</a>
  <a href="https://esempio.it/prodotto/altro/#recensioni">Altro</a>
  <a href="https://www.esempio.it/prodotto/altro/">Altro (www)</a>
  <a href="https://esterno.example/x">Esterno</a>
  <a href="mailto:a@b.it">Mail</a><a href="#su">Su</a>
</main>
<script>var parole_da_non_contare = 1;</script>
<footer>Copyright Negozio Esempio</footer>
</body></html>"""


def test_estrai_pagina_campi_seo():
    pagina, interni = _estrai_pagina(
        PAGINA, "https://esempio.it/prodotto/nothing-phone-2/", "prodotto", "esempio.it"
    )

    assert pagina["titolo"] == "Smartphone Nothing Phone 2 | Negozio Esempio"
    assert pagina["lunghezza_titolo"] == len(pagina["titolo"])
    assert pagina["meta_description"] == "Scopri Nothing Phone 2: scheda tecnica e prezzo."
    assert pagina["meta_robots"] == "index, follow"
    assert pagina["canonical"] == "https://esempio.it/prodotto/nothing-phone-2/"
    assert pagina["open_graph"] is True
    assert pagina["lingua"] == "it"
    assert pagina["h1"] == ["Nothing Phone 2"]
    assert pagina["h2"] == ["Scheda tecnica", "Scheda tecnica"]
    assert pagina["n_h3"] == 1
    assert pagina["dati_strutturati"] == ["BreadcrumbList", "Offer", "Product"]
    assert (pagina["immagini"], pagina["immagini_senza_alt"]) == (3, 2)
    assert pagina["link_esterni"] == 1
    # link interni deduplicati (ancora e www esclusi dal conteggio dei duplicati)
    assert interni == [
        "https://esempio.it/",
        "https://esempio.it/categoria-prodotto/telefoni/",
        "https://esempio.it/prodotto/altro/",
        "https://www.esempio.it/prodotto/altro/",
    ]
    assert pagina["link_interni"] == 4


def test_estrai_pagina_conta_le_parole_del_contenuto_e_ne_tiene_i_blocchi():
    pagina, _ = _estrai_pagina(PAGINA, "https://esempio.it/p/", "prodotto", "esempio.it")

    # h1 (3) + h2 x2 (4) + h3 (1) + paragrafo (11) + testi dei link in main (7) = 26: niente
    # menu, script, footer, titolo
    assert pagina["n_parole"] == 26
    # Il testo resta nei blocchi interni, dopo l'H1: niente menu, footer, titolo.
    blocchi = pagina["_blocchi"]
    assert "Un telefono con display luminoso e batteria che dura due giorni." in blocchi
    assert blocchi[0] == "Scheda tecnica"
    assert not any("menu" in b or "Copyright" in b or "Smartphone" in b for b in blocchi)


PAGINA_STRUTTURA = """<html><head><title>X</title>
<script type="application/ld+json">{"@type": "Product", "name": "X",
 "description": "  Descrizione   dal markup. ", "brand": {"@type": "Brand", "name": "Nothing"},
 "offers": [{"@type": "Offer", "availability": "https://schema.org/InStock"}],
 "aggregateRating": {"ratingValue": 4.5}}</script></head>
<body><h1>X</h1>
<p>Un <strong>telefono</strong> con <a href="/x">schermo</a> grande.</p>
<ul><li>Uno</li><li>Due</li></ul>
<table><tr><td>RAM</td><td>12 GB</td></tr></table>
<iframe src="https://www.youtube.com/embed/abc"></iframe></body></html>"""


def test_estrai_pagina_i_tag_in_linea_restano_nello_stesso_blocco():
    pagina, _ = _estrai_pagina(PAGINA_STRUTTURA, "https://esempio.it/p/", "prodotto", "esempio.it")
    assert pagina["_blocchi"] == [
        "Un telefono con schermo grande.",
        "Uno",
        "Due",
        "RAM",
        "12 GB",
    ]


def test_estrai_pagina_struttura_e_dati_prodotto():
    pagina, _ = _estrai_pagina(PAGINA_STRUTTURA, "https://esempio.it/p/", "prodotto", "esempio.it")
    assert pagina["struttura"] == {
        "paragrafi": 1,
        "voci_di_elenco": 2,
        "tabelle_o_liste_specifiche": 1,
        "video": 1,
    }
    assert pagina["dati_prodotto"] == {
        "descrizione": "Descrizione dal markup.",
        "marca": "Nothing",
        "con_valutazioni": True,
        "disponibilita": "InStock",
    }


def test_estrai_pagina_senza_h1_usa_tutto_il_testo_e_senza_product_non_ha_dati_prodotto():
    html = (
        "<html><head><title>T</title></head>"
        "<body><p>Solo un paragrafo qualunque qui.</p></body></html>"
    )
    pagina, _ = _estrai_pagina(html, "https://esempio.it/", "home", "esempio.it")
    assert pagina["_blocchi"] == ["Solo un paragrafo qualunque qui."]
    assert pagina["dati_prodotto"] == {}


def test_tipi_schema_ignora_json_malformato():
    assert _tipi_schema(["{ rotto", '{"@type": "Organization"}', "[1, 2]"]) == ["Organization"]


# --- campionamento e schemi dei titoli --------------------------------------


def test_campiona_distribuisce_su_tutta_la_lista():
    urls = [f"u{i}" for i in range(100)]
    assert _campiona(urls, 5) == ["u0", "u25", "u50", "u74", "u99"]
    assert _campiona(urls, 1) == ["u0"]
    assert _campiona(urls, 0) == []
    assert _campiona(urls[:3], 10) == ["u0", "u1", "u2"]


def test_schema_titolo_riconosce_separatore_e_brand():
    schema = _schema_titolo(
        [
            "Nothing Phone 2 | Negozio Esempio",
            "Samsung Galaxy S24 | Negozio Esempio",
            "iPhone 15 Pro Max 256GB Titanio Naturale | negozio esempio",
        ]
    )
    assert schema["separatore_piu_comune"] == "|"
    assert schema["suffisso_ricorrente"] == "negozio esempio"
    assert schema["percentuale_tra_30_e_60_caratteri"] == 100
    assert _schema_titolo(["Solo titolo"])["suffisso_ricorrente"] == ""


# --- flusso completo --------------------------------------------------------


SPEDIZIONE = "Spedizione gratuita in 24 ore per tutti gli ordini."


def _pagina_html(titolo, h1, h2=("Caratteristiche", "Pagamento"), schema="Product"):
    """Pagina con un paragrafo proprio (diverso per ogni titolo) e una frase di
    template identica su tutte le pagine."""
    return f"""<html lang="it"><head><title>{titolo} | Negozio Esempio</title>
<meta name="description" content="Descrizione di {titolo} con tutte le informazioni utili.">
<script type="application/ld+json">{{"@type": "{schema}"}}</script></head>
<body><h1>{h1}</h1>{"".join(f"<h2>{t}</h2>" for t in h2)}
<p>Il {titolo} offre una descrizione propria con dettagli unici.</p>
<p>{SPEDIZIONE}</p>
<img src="a.jpg" alt="foto"></body></html>"""


def _negozio_finto() -> dict[str, tuple[int, str]]:
    base = "https://esempio.it"
    indice = (
        "<sitemapindex><sitemap><loc>https://esempio.it/post-sitemap.xml</loc></sitemap>"
        "<sitemap><loc>https://esempio.it/product-sitemap.xml</loc></sitemap>"
        "<sitemap><loc>https://esempio.it/product_cat-sitemap.xml</loc></sitemap></sitemapindex>"
    )
    prodotti = [f"{base}/prodotto/telefono-{i}/" for i in range(1, 21)]
    categorie = [f"{base}/categoria-prodotto/cat-{i}/" for i in range(1, 6)]
    sito = {
        f"{base}/robots.txt": (200, "User-agent: *\nDisallow: /prodotto/telefono-5/\n"),
        f"{base}/sitemap.xml": (200, indice),
        f"{base}/product-sitemap.xml": (
            200,
            "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in prodotti) + "</urlset>",
        ),
        f"{base}/product_cat-sitemap.xml": (
            200,
            "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in categorie) + "</urlset>",
        ),
        f"{base}/": (200, _pagina_html("Home", "Il tuo negozio di telefoni", schema="WebSite")),
    }
    for i, url in enumerate(prodotti, 1):
        # "Scheda tecnica" solo su alcuni prodotti: un'intestazione di contenuto che ricorre
        h2 = ("Caratteristiche", "Pagamento") + (("Scheda tecnica",) if i in (1, 3, 7) else ())
        sito[url] = (200, _pagina_html(f"Telefono {i}", f"Telefono {i}", h2))
    for i, url in enumerate(categorie, 1):
        sito[url] = (200, _pagina_html(f"Categoria {i}", f"Categoria {i}", schema="CollectionPage"))
    return sito


def test_analizza_seo_sito_costruisce_il_report(monkeypatch):
    richieste = _sito_finto(monkeypatch, _negozio_finto())

    report = analizza_seo_sito("esempio.it")

    assert "errore" not in report
    assert report["sito"] == "https://esempio.it"
    assert report["sitemap"] == {
        "indirizzo": "https://esempio.it/sitemap.xml",
        "url_trovati": {"categorie": 5, "prodotti": 20},
    }
    campione = report["campione"]
    # home + 3 categorie + 10 prodotti, ma telefono-5 (nel campione) e' vietato da robots.txt
    assert (campione["categorie"], campione["prodotti"]) == (3, 9)
    assert report["campione"]["pagine_analizzate"] == 13
    assert [s["url"] for s in campione["pagine_saltate"]] == [
        "https://esempio.it/prodotto/telefono-5/"
    ]
    assert "robots.txt" in campione["pagine_saltate"][0]["motivo"]
    # le sitemap non pertinenti (articoli) non vengono nemmeno scaricate
    assert "https://esempio.it/post-sitemap.xml" not in richieste

    prodotti = report["riepilogo_per_tipo"]["prodotto"]
    assert prodotti["pagine_analizzate"] == 9
    assert prodotti["titolo"]["separatore_piu_comune"] == "|"
    assert prodotti["titolo"]["suffisso_ricorrente"] == "negozio esempio"
    assert prodotti["meta_description"]["presente_percentuale"] == 100
    assert prodotti["con_un_solo_h1_percentuale"] == 100
    assert prodotti["dati_strutturati"] == {"Product": 9}
    # "Caratteristiche" e "Pagamento" sono su tutte le pagine: template, non contenuto
    assert prodotti["h2_ricorrenti"] == [{"testo": "scheda tecnica", "pagine": 3}]
    assert report["riepilogo_per_tipo"]["categoria"]["dati_strutturati"] == {"CollectionPage": 3}
    assert {"termine": "negozio", "pagine": 13} in report["parole_nei_titoli"]
    assert "originali" in report["nota_uso"]


def test_il_report_ha_estratti_vocabolario_e_stile_senza_il_template(monkeypatch):
    _sito_finto(monkeypatch, _negozio_finto())

    report = analizza_seo_sito("https://esempio.it")

    prodotti = [p for p in report["pagine"] if p["tipo"] == "prodotto"]
    assert len(prodotti) == 9
    for pagina in prodotti:
        assert "descrizione propria con dettagli unici" in pagina["estratto"]
        assert "Spedizione gratuita" not in pagina["estratto"]  # e' template, non contenuto
    # la frase ripetuta ovunque diventa un messaggio del sito
    assert report["messaggi_ripetuti_sul_sito"] == [{"testo": SPEDIZIONE.lower(), "pagine": 13}]
    vocabolario = report["riepilogo_per_tipo"]["prodotto"]["vocabolario"]
    assert {"termine": "dettagli", "pagine": 9} in vocabolario["termini"]
    assert {"coppia": "descrizione propria", "pagine": 9} in vocabolario["coppie_di_parole"]
    assert "spedizione" not in [v["termine"] for v in vocabolario["termini"]]
    stile = report["riepilogo_per_tipo"]["prodotto"]["stile_e_intenzione"]
    # la spedizione gratuita nel template conta comunque come messaggio di servizio
    assert stile["ogni_1000_parole"]["fiducia_e_servizio"] > 0
    assert stile["ogni_1000_parole"]["inviti_all_azione"] == 0
    assert stile["lunghezza_media_frase_in_parole"] > 0


def test_caratteri_per_pagina_limita_o_toglie_gli_estratti(monkeypatch):
    _sito_finto(monkeypatch, _negozio_finto())

    corto = analizza_seo_sito("https://esempio.it", caratteri_per_pagina=20)
    estratti = [p["estratto"] for p in corto["pagine"] if p["estratto"]]
    assert estratti and all(len(e) <= 21 for e in estratti)  # 20 + "…"

    nessuno = analizza_seo_sito("https://esempio.it", caratteri_per_pagina=0)
    assert all(p["estratto"] == "" for p in nessuno["pagine"])
    # vocabolario e stile restano: il testo si analizza comunque
    assert nessuno["riepilogo_per_tipo"]["prodotto"]["vocabolario"]["termini"]

    tetto = analizza_seo_sito("https://esempio.it", caratteri_per_pagina=10**6)
    assert all(len(p["estratto"]) <= competitor_seo.TETTO_CARATTERI + 1 for p in tetto["pagine"])


def test_analizza_seo_sito_rispetta_i_limiti_e_il_tetto(monkeypatch):
    richieste = _sito_finto(monkeypatch, _negozio_finto())

    report = analizza_seo_sito("https://esempio.it", max_categorie=1, max_prodotti=2)
    assert (report["campione"]["categorie"], report["campione"]["prodotti"]) == (1, 2)

    richieste.clear()
    report = analizza_seo_sito("https://esempio.it", max_categorie=999, max_prodotti=999)
    assert report["campione"]["categorie"] == 5  # tutte quelle che ci sono (tetto 10)
    assert report["campione"]["prodotti"] + len(report["campione"]["pagine_saltate"]) == 20


def test_analizza_seo_sito_senza_sitemap_usa_i_link_della_home(monkeypatch):
    home = (
        "<html><head><title>Home | Negozio</title></head><body><h1>Benvenuti</h1>"
        '<a href="/product-category/audio/">Audio</a><a href="/product/cuffie/">Cuffie</a>'
        '<a href="/chi-siamo/">Chi siamo</a></body></html>'
    )
    base = "https://esempio.it"
    _sito_finto(
        monkeypatch,
        {
            f"{base}/": (200, home),
            f"{base}/product-category/audio/": (200, _pagina_html("Audio", "Audio")),
            f"{base}/product/cuffie/": (200, _pagina_html("Cuffie", "Cuffie")),
        },
    )

    report = analizza_seo_sito(base)

    assert report["sitemap"]["indirizzo"] is None
    assert any("Nessuna sitemap" in a for a in report["avvisi"])
    assert (report["campione"]["categorie"], report["campione"]["prodotti"]) == (1, 1)


def test_analizza_seo_sito_ignora_sitemap_su_altro_dominio(monkeypatch):
    richieste = _sito_finto(
        monkeypatch,
        {
            "https://esempio.it/robots.txt": (200, "Sitemap: https://altro.example/sitemap.xml\n"),
            "https://esempio.it/": (200, _pagina_html("Home", "Home")),
        },
    )
    report = analizza_seo_sito("https://esempio.it")
    assert "https://altro.example/sitemap.xml" not in richieste
    assert report["sitemap"]["indirizzo"] is None


def test_analizza_seo_sito_segnala_siti_costruiti_con_javascript(monkeypatch):
    _sito_finto(
        monkeypatch,
        {
            "https://esempio.it/": (
                200,
                "<html><head><title>App</title></head><body><div id=root></div></body></html>",
            )
        },
    )
    report = analizza_seo_sito("https://esempio.it")
    assert any("JavaScript" in a for a in report["avvisi"])


def test_analizza_seo_sito_errori_prevedibili_diventano_un_risultato(monkeypatch):
    # home vietata da robots.txt
    _sito_finto(
        monkeypatch,
        {"https://esempio.it/robots.txt": (200, "User-agent: *\nDisallow: /\n")},
    )
    assert "vietato da robots.txt" in analizza_seo_sito("https://esempio.it")["errore"]

    # home che risponde 500
    _sito_finto(monkeypatch, {"https://esempio.it/": (500, "")})
    assert analizza_seo_sito("https://esempio.it") == {"errore": "Pagina iniziale: HTTP 500"}

    # URL non valido
    assert "errore" in analizza_seo_sito("ftp://esempio.it")


def test_analizza_seo_sito_rifiuta_localhost(monkeypatch):
    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: ["127.0.0.1"])
    chiamate = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: chiamate.append(a))

    risultato = analizza_seo_sito("http://localhost:8080")

    assert "rete privata" in risultato["errore"]
    assert chiamate == []


def test_analizza_seo_sito_segnala_pagine_segnaposto(monkeypatch):
    """Es. WooCommerce in modalita' "in arrivo": titoli giusti ma stesso corpo ovunque."""
    sito = _negozio_finto()
    segnaposto = (
        "<html><head><title>{t} | Negozio Esempio</title></head><body>"
        "<h1>Grandi cose all'orizzonte</h1><p>Il negozio aprira presto.</p></body></html>"
    )
    for i in range(1, 21):
        sito[f"https://esempio.it/prodotto/telefono-{i}/"] = (
            200,
            segnaposto.format(t=f"Telefono {i}"),
        )

    _sito_finto(monkeypatch, sito)
    report = analizza_seo_sito("https://esempio.it")

    avviso = next(a for a in report["avvisi"] if "segnaposto" in a)
    assert "Grandi cose all'orizzonte" in avviso


def test_analizza_seo_sito_non_segnala_segnaposto_su_pagine_normali(monkeypatch):
    _sito_finto(monkeypatch, _negozio_finto())
    report = analizza_seo_sito("https://esempio.it")
    assert not any("segnaposto" in a for a in report["avvisi"])


def _sito_con_limiti(monkeypatch, risposte: dict[str, list[_Risposta]]):
    """Come _sito_finto, ma ogni URL ha una lista di risposte da servire in ordine."""
    richieste: list[str] = []

    def finto(url, host_base):
        richieste.append(url)
        coda = risposte.get(url)
        if not coda:
            return _Risposta(404, url, "")
        return coda.pop(0) if len(coda) > 1 else coda[0]

    monkeypatch.setattr(competitor_seo, "_scarica_grezzo", finto)
    pause: list[float] = []
    monkeypatch.setattr(competitor_seo.time, "sleep", pause.append)
    return richieste, pause


def test_429_con_retry_after_aspetta_e_ritenta_una_volta(monkeypatch):
    pagina_ok = _Risposta(200, "https://esempio.it/", _pagina_html("Home", "Home"))
    richieste, pause = _sito_con_limiti(
        monkeypatch,
        {
            "https://esempio.it/": [_Risposta(429, "https://esempio.it/", "", 60.0), pagina_ok],
        },
    )

    report = analizza_seo_sito("https://esempio.it")

    assert "errore" not in report
    assert richieste.count("https://esempio.it/") == 2
    assert 60.0 in pause


def test_429_che_continua_sulla_home_da_un_errore_chiaro_senza_insistere(monkeypatch):
    limitata = _Risposta(429, "https://esempio.it/", "", 60.0)
    richieste, pause = _sito_con_limiti(monkeypatch, {"https://esempio.it/": [limitata]})

    errore = analizza_seo_sito("https://esempio.it")["errore"]

    assert "429" in errore
    assert "SEO_ANALISI_USA_BROWSER" in errore and "analizza_pagine_salvate" in errore
    assert richieste.count("https://esempio.it/") == 2  # una richiesta + un solo nuovo tentativo
    assert pause == [60.0]


def test_429_senza_retry_after_o_troppo_lungo_non_viene_ritentato(monkeypatch):
    for attesa in (None, 3600.0):
        limitata = _Risposta(429, "https://esempio.it/", "", attesa)
        richieste, pause = _sito_con_limiti(monkeypatch, {"https://esempio.it/": [limitata]})
        assert "429" in analizza_seo_sito("https://esempio.it")["errore"]
        assert richieste.count("https://esempio.it/") == 1
        assert pause == []


def test_429_a_meta_analisi_ferma_il_campione_e_restituisce_il_parziale(monkeypatch):
    sito = {url: [_Risposta(stato, url, testo)] for url, (stato, testo) in _negozio_finto().items()}
    cat = "https://esempio.it/categoria-prodotto/cat-3/"  # la seconda categoria del campione
    sito[cat] = [_Risposta(429, cat, "", None)]
    richieste, _ = _sito_con_limiti(monkeypatch, sito)

    report = analizza_seo_sito("https://esempio.it")

    assert any("mi sono fermato" in a for a in report["avvisi"])
    assert report["campione"]["prodotti"] == 0  # non ha proseguito oltre il 429
    assert report["campione"]["pagine_saltate"][-1]["url"] == cat
    assert not any("/prodotto/" in r for r in richieste)


def test_l_analisi_salva_i_testi_per_il_controllo_di_somiglianza(monkeypatch):
    _sito_finto(monkeypatch, _negozio_finto())

    report = analizza_seo_sito("https://esempio.it")

    assert "Testi salvati in locale" in report["controllo_somiglianza"]
    riferimenti = text_similarity.carica_riferimenti("esempio.it")
    prodotto = next(
        r for r in riferimenti if r["fonte"] == "https://esempio.it/prodotto/telefono-1/"
    )
    assert "descrizione propria con dettagli unici" in prodotto["testo"]
    assert "Spedizione gratuita" not in prodotto["testo"]  # il template non e' un riferimento
    assert any(r["fonte"].endswith("telefono-1/ (titolo)") for r in riferimenti)

    # un testo ricalcato da una pagina analizzata viene riconosciuto, uno originale no
    copiato = text_similarity.controlla(
        "Il Telefono 1 offre una descrizione propria con dettagli unici.", riferimenti
    )
    originale = text_similarity.controlla(
        "Schermo luminoso, batteria generosa e una fotocamera che non delude mai.", riferimenti
    )
    assert copiato["punteggio"] >= 8
    assert originale["punteggio"] == 0


def test_se_la_cache_non_e_scrivibile_l_analisi_riesce_e_lo_dice(monkeypatch, tmp_path):
    _sito_finto(monkeypatch, _negozio_finto())
    bloccata = tmp_path / "file"
    bloccata.write_text("")
    monkeypatch.setenv("SEO_ANALISI_CACHE_DIR", str(bloccata / "sotto"))  # non e' una cartella

    report = analizza_seo_sito("https://esempio.it")

    assert "errore" not in report
    assert "Testi non salvati" in report["controllo_somiglianza"]


# --- trasporto curl (scelta esplicita dell'utente) --------------------------


def test_separa_risposta_curl_stato_intestazioni_e_corpo():
    grezzo = (
        b"HTTP/2 200 \r\nContent-Type: text/html; charset=ISO-8859-1\r\nRetry-After: 60\r\n\r\n"
        b"<html>ciao</html>"
    )
    stato, intestazioni, corpo, codifica = competitor_seo._separa_risposta_curl(grezzo)
    assert stato == 200
    assert intestazioni == {"content-type": "text/html; charset=ISO-8859-1", "retry-after": "60"}
    assert corpo == b"<html>ciao</html>"
    assert codifica == "ISO-8859-1"


def test_separa_risposta_curl_salta_le_risposte_provvisorie():
    grezzo = b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 301 Moved\r\nLocation: /x\r\n\r\n"
    stato, intestazioni, corpo, _ = competitor_seo._separa_risposta_curl(grezzo)
    assert (stato, intestazioni["location"], corpo) == (301, "/x", b"")


def test_separa_risposta_curl_rifiuta_output_non_http():
    with pytest.raises(ErroreAnalisi, match="non riconosciuta"):
        competitor_seo._separa_risposta_curl(b"qualcosa che non e' http")


class _ProcessoFinto:
    def __init__(self, comando, uscita=b"HTTP/2 200\r\nContent-Type: text/html\r\n\r\nciao"):
        self.comando = comando
        self.stdout = type("S", (), {"read": lambda _, n: uscita})()
        self.stderr = type("E", (), {"read": lambda _: b""})()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def kill(self):
        pass

    def wait(self):
        pass


def test_richiesta_curl_usa_user_agent_dichiarato_senza_shell(monkeypatch):
    lanciati = []

    def popen_finto(comando, **kwargs):
        lanciati.append((comando, kwargs))
        return _ProcessoFinto(comando)

    monkeypatch.setattr(competitor_seo.subprocess, "Popen", popen_finto)

    stato, _, corpo, _ = competitor_seo._richiesta_curl("https://esempio.it/x")

    comando, kwargs = lanciati[0]
    assert isinstance(comando, list) and comando[0] == "curl"  # lista, niente shell
    assert "shell" not in kwargs
    assert comando[comando.index("-A") + 1] == competitor_seo.USER_AGENT
    assert "push_contempt_mcp-seo" in competitor_seo.USER_AGENT
    assert comando[-1] == "https://esempio.it/x"
    assert "-L" not in comando  # i redirect li gestiamo noi, restando sul dominio
    assert (stato, corpo) == (200, b"ciao")


def test_richiesta_curl_senza_curl_installato(monkeypatch):
    def popen_che_fallisce(comando, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(competitor_seo.subprocess, "Popen", popen_che_fallisce)
    with pytest.raises(ErroreAnalisi, match="curl non e' installato"):
        competitor_seo._richiesta_curl("https://esempio.it/")


def test_usa_curl_sceglie_il_trasporto_solo_se_richiesto(monkeypatch):
    sito = _negozio_finto()
    chiamate = {"requests": 0, "curl": 0}

    def trasporto(nome):
        def scarica(url, host_base):
            chiamate[nome] += 1
            stato, testo = sito.get(url, (404, ""))
            return _Risposta(stato, url, testo)

        return scarica

    monkeypatch.setattr(competitor_seo, "_scarica_grezzo", trasporto("requests"))
    monkeypatch.setattr(competitor_seo, "_scarica_grezzo_curl", trasporto("curl"))

    assert "errore" not in analizza_seo_sito("https://esempio.it")
    assert chiamate["requests"] > 0 and chiamate["curl"] == 0

    chiamate.update(requests=0, curl=0)
    assert "errore" not in analizza_seo_sito("https://esempio.it", usa_curl=True)
    assert chiamate["curl"] > 0 and chiamate["requests"] == 0


def test_con_curl_valgono_ancora_robots_e_stop_al_429(monkeypatch):
    sito = _negozio_finto()
    sito["https://esempio.it/robots.txt"] = (200, "User-agent: *\nDisallow: /\n")
    monkeypatch.setattr(
        competitor_seo,
        "_scarica_grezzo_curl",
        lambda url, host: _Risposta(*(lambda s: (s[0], url, s[1]))(sito.get(url, (404, "")))),
    )
    assert (
        "vietato da robots.txt" in analizza_seo_sito("https://esempio.it", usa_curl=True)["errore"]
    )

    limitata = _Risposta(429, "https://esempio.it/", "", None)
    monkeypatch.setattr(competitor_seo, "_scarica_grezzo_curl", lambda url, host: limitata)
    assert "429" in analizza_seo_sito("https://esempio.it", usa_curl=True)["errore"]


# --- pagine salvate dall'utente ---------------------------------------------


def _salva(cartella, nome, url, html):
    html = html.replace("</head>", f'<link rel="canonical" href="{url}"></head>')
    (cartella / nome).write_text(html, encoding="utf-8")


def _cartella_pagine(tmp_path):
    cartella = tmp_path / "salvate"
    cartella.mkdir()
    base = "https://esempio.it"
    _salva(
        cartella, "home.html", f"{base}/", _pagina_html("Home", "Il tuo negozio", schema="WebSite")
    )
    _salva(
        cartella,
        "cat.html",
        f"{base}/categoria-prodotto/telefoni/",
        _pagina_html("Telefoni", "Telefoni"),
    )
    for i in range(1, 5):
        _salva(
            cartella,
            f"p{i}.htm",
            f"{base}/prodotto/telefono-{i}/",
            _pagina_html(f"Telefono {i}", f"Telefono {i}"),
        )
    return cartella


def test_pagine_salvate_analisi_senza_rete(monkeypatch, tmp_path):
    def senza_rete(*args, **kwargs):
        raise AssertionError("nessuna richiesta di rete in questa modalita'")

    monkeypatch.setattr(requests, "get", senza_rete)
    monkeypatch.setattr(competitor_seo, "_scarica_grezzo", senza_rete)

    report = competitor_seo.analizza_pagine_salvate([str(_cartella_pagine(tmp_path))])

    assert "errore" not in report
    assert report["sito"] == "https://esempio.it"
    assert (report["campione"]["categorie"], report["campione"]["prodotti"]) == (1, 4)
    assert {p["tipo"] for p in report["pagine"]} == {"home", "categoria", "prodotto"}
    assert any("pagine salvate" in a for a in report["avvisi"])
    prodotto = next(p for p in report["pagine"] if p["url"].endswith("telefono-1/"))
    assert "descrizione propria con dettagli unici" in prodotto["estratto"]
    assert "Spedizione gratuita" not in prodotto["estratto"]
    assert report["messaggi_ripetuti_sul_sito"][0]["testo"] == SPEDIZIONE.lower()
    # anche qui i testi restano disponibili per il controllo di somiglianza
    assert text_similarity.carica_riferimenti("esempio.it")


def test_pagine_salvate_accetta_anche_file_singoli_e_deduce_il_tipo_dai_dati(tmp_path):
    cartella = tmp_path / "x"
    cartella.mkdir()
    pagina = _pagina_html("Telefono 9", "Telefono 9").replace("</head>", "</head>")
    (cartella / "senza_indirizzo.html").write_text(pagina, encoding="utf-8")

    report = competitor_seo.analizza_pagine_salvate(
        [str(cartella / "senza_indirizzo.html")], sito="https://esempio.it"
    )

    assert report["sito"] == "https://esempio.it"
    assert report["pagine"][0]["tipo"] == "prodotto"  # dal JSON-LD Product
    assert report["pagine"][0]["url"].startswith("file://")
    assert any("non dichiarano il proprio indirizzo" in a for a in report["avvisi"])


def test_pagine_salvate_errori_prevedibili(tmp_path):
    assert (
        "non e' un file .html"
        in competitor_seo.analizza_pagine_salvate([str(tmp_path / "non_esiste.html")])["errore"]
    )
    altro = tmp_path / "note.txt"
    altro.write_text("non e' html")
    assert "errore" in competitor_seo.analizza_pagine_salvate([str(altro)])
    vuota = tmp_path / "vuota"
    vuota.mkdir()
    assert "Nessun file .html" in competitor_seo.analizza_pagine_salvate([str(vuota)])["errore"]


def test_varianti_di_lingua_non_occupano_il_campione():
    urls = [
        "https://esempio.it/collections/velluto",
        "https://esempio.it/en/collections/velluto",
        "https://esempio.it/fr/collections/velluto",
        "https://esempio.it/en/collections/solo-inglese",  # non ha l'equivalente senza prefisso
        "https://esempio.it/collections/lana",
        "https://esempio.it/it/collections/lana",
        "https://esempio.it/products/ab",  # "ab" non e' un prefisso di lingua: e' un prodotto
    ]
    assert competitor_seo._senza_varianti_lingua(urls) == [
        "https://esempio.it/collections/velluto",
        "https://esempio.it/en/collections/solo-inglese",
        "https://esempio.it/collections/lana",
        "https://esempio.it/products/ab",
    ]


def test_l_analisi_non_campiona_le_varianti_di_lingua(monkeypatch):
    sito = _negozio_finto()
    base = "https://esempio.it"
    categorie = [f"{base}/categoria-prodotto/cat-{i}/" for i in range(1, 4)]
    con_varianti = categorie + [u.replace(base, f"{base}/en") for u in categorie]
    sito[f"{base}/product_cat-sitemap.xml"] = (
        200,
        "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in con_varianti) + "</urlset>",
    )
    _sito_finto(monkeypatch, sito)

    report = analizza_seo_sito(base)

    assert report["sitemap"]["url_trovati"]["categorie"] == 3
    assert not any("/en/" in p["url"] for p in report["pagine"])


# --- scala dei metodi: HTTP, poi browser, poi pagine salvate ----------------


def _installa_browser(monkeypatch, sito, errore_avvio=None):
    """Sostituisce _Browser con uno che serve le pagine di `sito` ({url: (status, testo)})."""
    uso = {"istanze": 0, "richieste": [], "chiuso": 0, "visibile": []}

    class BrowserFinto:
        def __init__(self, visibile=False):
            uso["istanze"] += 1
            uso["visibile"].append(visibile)

        def scarica(self, url, host_base):
            if errore_avvio:
                raise ErroreAnalisi(errore_avvio)
            uso["richieste"].append(url)
            stato, testo = sito.get(url, (404, ""))
            return _Risposta(stato, url, testo)

        def chiudi(self):
            uso["chiuso"] += 1

    monkeypatch.setattr(competitor_seo, "_Browser", BrowserFinto)
    return uso


def _http_limitato(monkeypatch, home_http: _Risposta):
    """HTTP semplice: robots.txt assente, home = `home_http`, nient'altro."""
    return _sito_con_limiti(monkeypatch, {"https://esempio.it/": [home_http]})


def test_http_che_basta_non_avvia_il_browser(monkeypatch):
    uso = _installa_browser(monkeypatch, _negozio_finto())
    _sito_finto(monkeypatch, _negozio_finto())

    report = analizza_seo_sito("https://esempio.it", usa_browser=True)

    assert report["metodo"] == "http"
    assert uso["istanze"] == 0


def test_429_con_browser_attivo_aspetta_il_retry_after_e_passa_al_browser(monkeypatch):
    uso = _installa_browser(monkeypatch, _negozio_finto())
    richieste, pause = _http_limitato(monkeypatch, _Risposta(429, "https://esempio.it/", "", 60.0))

    report = analizza_seo_sito("https://esempio.it", usa_browser=True)

    assert "errore" not in report
    assert report["metodo"] == "browser"
    assert any("perche' il sito rifiuta" in a for a in report["avvisi"])
    assert richieste.count("https://esempio.it/") == 1  # HTTP: una richiesta, senza nuovo tentativo
    assert pause == [60.0]  # si aspetta quanto chiesto dal sito prima del browser
    assert uso["istanze"] == 1 and uso["chiuso"] == 1
    assert len(report["pagine"]) > 5  # l'analisi e' completa


def test_il_browser_si_attiva_anche_con_la_variabile_d_ambiente(monkeypatch):
    monkeypatch.setenv("SEO_ANALISI_USA_BROWSER", "1")
    uso = _installa_browser(monkeypatch, _negozio_finto())
    _http_limitato(monkeypatch, _Risposta(403, "https://esempio.it/", ""))

    report = analizza_seo_sito("https://esempio.it")

    assert report["metodo"] == "browser" and uso["istanze"] == 1


def test_senza_browser_un_429_da_il_suggerimento_e_il_vecchio_comportamento(monkeypatch):
    uso = _installa_browser(monkeypatch, _negozio_finto())
    richieste, pause = _http_limitato(monkeypatch, _Risposta(429, "https://esempio.it/", "", 60.0))

    errore = analizza_seo_sito("https://esempio.it")["errore"]

    assert "SEO_ANALISI_USA_BROWSER" in errore
    assert richieste.count("https://esempio.it/") == 2  # senza browser si ritenta una volta
    assert uso["istanze"] == 0


def test_se_anche_il_browser_e_respinto_si_suggeriscono_le_pagine_salvate(monkeypatch):
    sito = {"https://esempio.it/": (429, "")}
    uso = _installa_browser(monkeypatch, sito)
    _http_limitato(monkeypatch, _Risposta(429, "https://esempio.it/", "", None))

    errore = analizza_seo_sito("https://esempio.it", usa_browser=True)["errore"]

    assert "Anche con un browser" in errore and "analizza_pagine_salvate" in errore
    assert uso["chiuso"] == 1  # il browser si chiude comunque


def test_home_costruita_con_javascript_passa_al_browser(monkeypatch):
    vuota = "<html><head><title>App</title></head><body><div id=root></div></body></html>"
    _installa_browser(monkeypatch, _negozio_finto())
    _sito_finto(monkeypatch, {"https://esempio.it/": (200, vuota)})

    report = analizza_seo_sito("https://esempio.it", usa_browser=True)

    assert report["metodo"] == "browser"
    assert not any(a.startswith("La home ha quasi nessun testo") for a in report["avvisi"])
    assert any("sembrano costruite con JavaScript" in a for a in report["avvisi"])
    assert report["campione"]["prodotti"] > 0


def test_se_il_browser_non_riesce_resta_il_report_http_con_un_avviso(monkeypatch):
    vuota = "<html><head><title>App</title></head><body><div id=root></div></body></html>"
    _installa_browser(monkeypatch, {}, errore_avvio="Browser non disponibile: Error")
    _sito_finto(monkeypatch, {"https://esempio.it/": (200, vuota)})

    report = analizza_seo_sito("https://esempio.it", usa_browser=True)

    assert report["metodo"] == "http"
    assert any("Provato anche con il browser, senza riuscirci" in a for a in report["avvisi"])
    assert any("JavaScript" in a for a in report["avvisi"])


# --- il trasporto browser (con una pagina finta) ----------------------------


class _RispostaPlaywrightFinta:
    def __init__(self, status, headers, testo):
        self.status, self.headers, self._testo = status, headers, testo

    def text(self):
        return self._testo


class _PaginaFinta:
    def __init__(self, destinazioni):
        self.destinazioni = destinazioni  # url -> (url finale, status, headers, testo)
        self.url = ""
        self.visitati = []
        self.html = ""

    def goto(self, url, wait_until, timeout):
        self.visitati.append(url)
        self.url, status, headers, testo = self.destinazioni[url]
        self.html = testo
        return _RispostaPlaywrightFinta(status, headers, testo)

    def wait_for_load_state(self, *args, **kwargs):
        pass

    def wait_for_timeout(self, ms):
        pass

    def content(self):
        return self.html


def _browser_con_pagina(monkeypatch, destinazioni):
    pagina = _PaginaFinta(destinazioni)
    chiuso = []
    monkeypatch.setattr(
        competitor_seo, "_avvia_playwright", lambda: (lambda: chiuso.append(1), pagina)
    )
    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: ["93.184.216.34"])
    return pagina, chiuso


def test_browser_html_xml_e_retry_after(monkeypatch):
    pagina, chiuso = _browser_con_pagina(
        monkeypatch,
        {
            "https://esempio.it/": (
                "https://esempio.it/",
                200,
                {"content-type": "text/html"},
                "<html>costruito</html>",
            ),
            "https://esempio.it/sitemap.xml": (
                "https://esempio.it/sitemap.xml",
                200,
                {"content-type": "application/xml"},
                "<urlset><url><loc>x</loc></url></urlset>",
            ),
            "https://esempio.it/limitata": (
                "https://esempio.it/limitata",
                429,
                {"content-type": "text/html", "retry-after": "30"},
                "troppe richieste",
            ),
        },
    )
    browser = competitor_seo._Browser()

    html = browser.scarica("https://esempio.it/", "esempio.it")
    xml = browser.scarica("https://esempio.it/sitemap.xml", "esempio.it")
    limitata = browser.scarica("https://esempio.it/limitata", "esempio.it")
    browser.chiudi()

    assert (html.status, html.testo) == (200, "<html>costruito</html>")  # HTML gia' costruito
    assert "<loc>x</loc>" in xml.testo  # non HTML: il corpo della risposta
    assert (limitata.status, limitata.retry_after) == (429, 30.0)
    assert chiuso == [1]
    assert len(pagina.visitati) == 3


def test_browser_rifiuta_redirect_verso_altro_dominio_e_reti_private(monkeypatch):
    _browser_con_pagina(
        monkeypatch,
        {
            "https://esempio.it/vai": (
                "https://altro.example/",
                200,
                {"content-type": "text/html"},
                "<html></html>",
            )
        },
    )
    browser = competitor_seo._Browser()
    with pytest.raises(ErroreAnalisi, match="altro dominio"):
        browser.scarica("https://esempio.it/vai", "esempio.it")

    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: ["10.0.0.5"])
    with pytest.raises(ErroreAnalisi, match="rete privata"):
        browser.scarica("https://interno.example/", "interno.example")


def test_browser_non_disponibile_da_un_errore_chiaro(monkeypatch):
    def avvio_che_fallisce():
        raise RuntimeError("Executable doesn't exist")

    monkeypatch.setattr(competitor_seo, "_avvia_playwright", avvio_che_fallisce)
    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: ["93.184.216.34"])
    with pytest.raises(ErroreAnalisi, match="Browser non disponibile"):
        competitor_seo._Browser().scarica("https://esempio.it/", "esempio.it")


def test_il_report_include_la_valutazione_per_area(monkeypatch):
    _sito_finto(monkeypatch, _negozio_finto())

    report = analizza_seo_sito("https://esempio.it")

    valutazione = report["valutazione"]
    assert 0 <= valutazione["punteggio"] <= 9
    assert set(valutazione["aree"]) == {
        "titoli",
        "meta_description",
        "intestazioni",
        "dati_strutturati",
        "contenuto",
        "tecnico",
    }
    assert valutazione["pagine_valutate"] == len(report["pagine"])
    assert "non e' vincolante" in valutazione["nota"]
    criteri_tecnici = [c["criterio"] for c in valutazione["aree"]["tecnico"]["criteri"]]
    assert "sitemap" in criteri_tecnici and "HTTPS" in criteri_tecnici
    # le prove sono quelle dei dati: titoli tutti diversi, ma di 28 caratteri (sotto i 30)
    n = len(report["pagine"])
    prove = {c["criterio"]: c["evidenza"] for c in valutazione["aree"]["titoli"]["criteri"]}
    assert prove["titoli diversi fra loro"] == f"titoli distinti: {n} su {n}"
    assert "titoli fra 30 e 60 caratteri: 0 su" in prove["lunghezza adatta"]


def test_la_valutazione_delle_pagine_salvate_salta_sitemap_e_https(tmp_path):
    report = competitor_seo.analizza_pagine_salvate([str(_cartella_pagine(tmp_path))])

    criteri_tecnici = [c["criterio"] for c in report["valutazione"]["aree"]["tecnico"]["criteri"]]
    assert "sitemap" not in criteri_tecnici and "HTTPS" not in criteri_tecnici
    assert "indirizzo canonico" in criteri_tecnici


def test_le_parole_proprie_escludono_il_template(monkeypatch):
    _sito_finto(monkeypatch, _negozio_finto())
    report = analizza_seo_sito("https://esempio.it")
    # il paragrafo proprio ha 9 parole: la frase di spedizione (template) non conta
    prodotto = next(p for p in report["pagine"] if p["url"].endswith("telefono-1/"))
    assert prodotto["n_parole"] > 9


# --- siti con indirizzi dei prodotti non riconoscibili (es. concessionarie) ---


def test_gruppo_dominante_trova_le_schede_senza_un_indirizzo_noto():
    schede = [f"https://esempio.it/scheda-auto/{i}-audi-a3.html" for i in range(1, 8)]
    altre = ["https://esempio.it/chi-siamo.html", "https://esempio.it/contatti.html"]
    gruppo, tratto = competitor_seo._gruppo_dominante(altre + schede)
    assert gruppo == schede and tratto == "/scheda-auto/"


def test_gruppo_dominante_non_scambia_blog_e_piccoli_gruppi_per_prodotti():
    articoli = [f"https://esempio.it/blog/articolo-{i}" for i in range(40)]
    assert competitor_seo._gruppo_dominante(articoli) == ([], "")
    pochi = [f"https://esempio.it/auto/{i}" for i in range(4)]  # meno di 5
    assert competitor_seo._gruppo_dominante(pochi) == ([], "")
    sparsi = [f"https://esempio.it/{x}/{i}" for i, x in enumerate("abcdefghij")]
    assert competitor_seo._gruppo_dominante(sparsi) == ([], "")
    assert competitor_seo._gruppo_dominante([]) == ([], "")


def _concessionaria():
    base = "https://esempio.it"
    schede = [f"{base}/scheda-auto/{i}-modello-{i}.html" for i in range(1, 21)]
    voci = ["<url><loc>" + u + "</loc></url>" for u in schede]
    voci += [
        f"<url><loc>{base}/chi-siamo.html</loc></url>",
        "<url><loc>http://altro-dominio.example/privacy.html</loc></url>",  # altro dominio
        "<url><loc>http://altro-dominio.example/scheda-auto/1-estranea.html</loc></url>",
    ]
    sito = {
        f"{base}/sitemap.xml": (200, "<urlset>" + "".join(voci) + "</urlset>"),
        f"{base}/": (200, _pagina_html("Home", "Auto usate", schema="AutoDealer")),
    }
    for i, u in enumerate(schede, 1):
        sito[u] = (200, _pagina_html(f"Auto {i}", f"Auto {i}"))
    return sito, schede


def test_senza_indirizzi_noti_si_campiona_il_gruppo_piu_numeroso_della_sitemap(monkeypatch):
    sito, schede = _concessionaria()
    richieste = _sito_finto(monkeypatch, sito)

    report = analizza_seo_sito("https://esempio.it")

    assert report["campione"]["prodotti"] == 10
    assert report["sitemap"]["url_trovati"]["prodotti"] == 20  # le 2 di un altro dominio no
    assert any(
        "gruppo piu' numeroso della sitemap (/scheda-auto/, 20" in a for a in report["avvisi"]
    )
    assert all(p["url"] in schede or p["tipo"] == "home" for p in report["pagine"])
    assert report["valutazione"]["affidabilita"] == "adeguata"
    assert not any("altro-dominio" in r for r in richieste)  # non si esce dal dominio indicato


def test_le_sitemap_non_portano_fuori_dal_dominio_nemmeno_con_indirizzi_riconosciuti(monkeypatch):
    sito = _negozio_finto()
    base = "https://esempio.it"
    estranei = [f"http://altro-dominio.example/prodotto/estraneo-{i}/" for i in range(10)]
    sito[f"{base}/product-sitemap.xml"] = (
        200,
        "<urlset>"
        + "".join(f"<url><loc>{u}</loc></url>" for u in estranei)
        + f"<url><loc>{base}/prodotto/telefono-1/</loc></url></urlset>",
    )
    richieste = _sito_finto(monkeypatch, sito)

    report = analizza_seo_sito(base)

    assert report["sitemap"]["url_trovati"]["prodotti"] == 1
    assert not any("altro-dominio" in r for r in richieste)


def test_con_la_sola_home_il_report_non_da_un_punteggio_complessivo(monkeypatch):
    _sito_finto(monkeypatch, {"https://esempio.it/": (200, _pagina_html("Home", "Benvenuti"))})

    report = analizza_seo_sito("https://esempio.it")

    assert report["valutazione"]["punteggio"] is None
    assert report["valutazione"]["affidabilita"] == "bassa"
    assert report["valutazione"]["aree"]["titoli"]["punteggio"] is not None


def test_le_voci_dei_menu_a_tendina_non_si_incollano():
    html = (
        "<html><body><h1>iPhone 14</h1>"
        "<label>Colore</label><select><option>Scegli un'opzione</option><option>Blu</option>"
        "<option>Giallo</option></select>"
        "<p>Un <strong>telefono</strong> ricondizionato.</p></body></html>"
    )
    pagina, _ = _estrai_pagina(html, "https://esempio.it/p/", "prodotto", "esempio.it")
    assert pagina["_blocchi"] == [
        "Colore",
        "Scegli un'opzione",
        "Blu",
        "Giallo",
        "Un telefono ricondizionato.",
    ]


# --- analisi di una sola sezione del sito -----------------------------------


def test_perimetro_dal_percorso_dell_indirizzo():
    assert competitor_seo._perimetro("https://esempio.it/") == ""
    assert competitor_seo._perimetro("https://esempio.it") == ""
    assert competitor_seo._perimetro("https://esempio.it/Telefonia/") == "/telefonia"
    assert competitor_seo._nel_perimetro("https://esempio.it/telefonia/smartphone/x", "/telefonia")
    assert competitor_seo._nel_perimetro("https://esempio.it/telefonia", "/telefonia")
    assert not competitor_seo._nel_perimetro("https://esempio.it/telefonia-fissa/x", "/telefonia")
    assert not competitor_seo._nel_perimetro("https://esempio.it/tv/x", "/telefonia")
    assert competitor_seo._nel_perimetro("https://esempio.it/tv/x", "")


def _sito_con_sezioni():
    base = "https://esempio.it"
    prodotti = [f"{base}/prodotto/telefonia-{i}/" for i in range(1, 7)]
    prodotti += [f"{base}/telefonia/prodotto/smartphone-{i}/" for i in range(1, 9)]
    prodotti += [f"{base}/tv/prodotto/televisore-{i}/" for i in range(1, 9)]
    categorie = [f"{base}/telefonia/categoria-prodotto/{c}/" for c in ("android", "ios")]
    categorie += [f"{base}/tv/categoria-prodotto/{c}/" for c in ("oled", "led")]
    indice = (
        f"<sitemapindex><sitemap><loc>{base}/product-sitemap.xml</loc></sitemap>"
        f"<sitemap><loc>{base}/product_cat-sitemap.xml</loc></sitemap></sitemapindex>"
    )

    def mappa(urls):
        return "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"

    sito = {
        f"{base}/sitemap.xml": (200, indice),
        f"{base}/product-sitemap.xml": (200, mappa(prodotti)),
        f"{base}/product_cat-sitemap.xml": (200, mappa(categorie)),
        f"{base}/": (200, _pagina_html("Home", "Il negozio", schema="WebSite")),
        f"{base}/telefonia/": (200, _pagina_html("Telefonia", "Telefonia e accessori")),
    }
    for url in prodotti + categorie:
        sito[url] = (200, _pagina_html(url.rsplit("/", 2)[1], url.rsplit("/", 2)[1]))
    return sito


def test_indirizzo_di_una_sezione_limita_il_campione_a_quella_sezione(monkeypatch):
    richieste = _sito_finto(monkeypatch, _sito_con_sezioni())

    report = analizza_seo_sito("https://esempio.it/telefonia/")

    assert report["perimetro"] == "/telefonia"
    assert report["sitemap"]["url_trovati"] == {"categorie": 2, "prodotti": 8}
    pagine = [p["url"] for p in report["pagine"]]
    assert pagine[0] == "https://esempio.it/telefonia/"
    assert all("/telefonia/" in u for u in pagine)
    assert not any("/tv/" in r for r in richieste)  # nemmeno una richiesta fuori sezione
    assert not any(r.endswith("/prodotto/telefonia-1/") for r in richieste)
    assert report["campione"]["prodotti"] == 8 and report["campione"]["categorie"] == 2


def test_la_pagina_iniziale_di_una_sezione_non_e_una_home(monkeypatch):
    _sito_finto(monkeypatch, _sito_con_sezioni())

    report = analizza_seo_sito("https://esempio.it/telefonia/")

    assert report["pagine"][0]["tipo"] == "sezione"
    criteri = [c["criterio"] for c in report["valutazione"]["aree"]["dati_strutturati"]["criteri"]]
    assert not any("Organization" in c for c in criteri)  # il criterio vale per la home vera


def test_senza_sezione_l_analisi_resta_su_tutto_il_sito(monkeypatch):
    _sito_finto(monkeypatch, _sito_con_sezioni())

    report = analizza_seo_sito("https://esempio.it/")

    assert report["perimetro"] is None
    assert report["pagine"][0]["tipo"] == "home"
    assert report["sitemap"]["url_trovati"]["prodotti"] == 22


def test_in_una_sezione_senza_sitemap_si_usano_i_link_della_pagina_della_sezione(monkeypatch):
    base = "https://esempio.it"
    pagina_sezione = (
        "<html><head><title>Telefonia | Negozio</title></head><body><h1>Telefonia</h1>"
        f'<a href="{base}/telefonia/prodotto/uno/">Uno</a>'
        f'<a href="{base}/telefonia/categoria-prodotto/android/">Android</a>'
        f'<a href="{base}/tv/prodotto/estraneo/">Estraneo</a></body></html>'
    )
    richieste = _sito_finto(
        monkeypatch,
        {
            f"{base}/telefonia/": (200, pagina_sezione),
            f"{base}/telefonia/prodotto/uno/": (200, _pagina_html("Uno", "Uno")),
            f"{base}/telefonia/categoria-prodotto/android/": (200, _pagina_html("An", "An")),
        },
    )

    report = analizza_seo_sito(f"{base}/telefonia/")

    assert (report["campione"]["categorie"], report["campione"]["prodotti"]) == (1, 1)
    assert not any("/tv/" in r for r in richieste)


# --- sitemap grandi, composizione del campione, indirizzi 404 ---------------


def test_le_sitemap_hanno_un_tetto_molto_piu_alto_delle_pagine(monkeypatch):
    _pubblico(monkeypatch)
    enorme = b"a" * (competitor_seo.MAX_BYTE * 3)
    monkeypatch.setattr(requests, "get", lambda url, **kw: _RispostaHttpFinta(200, corpo=enorme))

    pagina = _scarica_grezzo("https://esempio.it/", "esempio.it")
    mappa = _scarica_grezzo("https://esempio.it/sitemap_0-product.xml", "esempio.it")
    robots_xml = _scarica_grezzo("https://esempio.it/prodotti.xml", "esempio.it")

    assert len(pagina.testo) == competitor_seo.MAX_BYTE
    assert len(mappa.testo) == len(enorme) < competitor_seo.MAX_BYTE_SITEMAP
    assert len(robots_xml.testo) == len(enorme)


def test_una_sitemap_grande_non_viene_letta_solo_all_inizio(monkeypatch):
    """Il difetto reale (Euronics): con il tetto delle pagine il campione veniva solo dai
    primi gruppi della sitemap. Qui i telefoni stanno in fondo a una sitemap da oltre 1,5 MB
    e il test passa dal vero trasporto, non da un finto sito."""
    _pubblico(monkeypatch)
    base = "https://esempio.it"
    accessori = [f"{base}/telefonia/accessori/cavo-{i}/1{i:06d}.html" for i in range(20000)]
    telefoni = [f"{base}/telefonia/smartphone/telefono-{i}/2{i:06d}.html" for i in range(60)]
    mappa = "<urlset>" + "".join(f"<url><loc>{u}</loc></url>" for u in accessori + telefoni)
    mappa = (mappa + "</urlset>").encode()
    assert len(mappa) > competitor_seo.MAX_BYTE  # piu' grande del tetto delle pagine
    pagina = _pagina_html("Telefono", "Telefono").encode()

    def get_finto(url, **kwargs):
        if url.endswith("/robots.txt"):
            return _RispostaHttpFinta(404, corpo=b"")
        if url.endswith("/sitemap.xml"):
            return _RispostaHttpFinta(200, corpo=mappa)
        return _RispostaHttpFinta(200, corpo=pagina)

    monkeypatch.setattr(requests, "get", get_finto)

    report = analizza_seo_sito(f"{base}/telefonia/smartphone/", max_prodotti=10)

    assert report["sitemap"]["url_trovati"]["prodotti"] == 60  # letta tutta, non solo l'inizio
    assert report["campione"]["prodotti"] == 10
    prodotti = [p["url"] for p in report["pagine"] if p["tipo"] == "prodotto"]
    assert len(prodotti) == 10 and all("/smartphone/" in u for u in prodotti)


def test_composizione_del_campione_per_sottogruppo():
    pagine = [
        {"tipo": "sezione", "url": "https://esempio.it/telefonia/"},
        {"tipo": "categoria", "url": "https://esempio.it/telefonia/accessori/"},
        {"tipo": "prodotto", "url": "https://esempio.it/telefonia/accessori/cavi/cavo-1.html"},
        {"tipo": "prodotto", "url": "https://esempio.it/telefonia/accessori/cavi/cavo-2.html"},
        {"tipo": "prodotto", "url": "https://esempio.it/telefonia/smartphone/uno.html"},
        {"tipo": "prodotto", "url": "https://esempio.it/telefonia/fisso.html"},
    ]
    assert competitor_seo._composizione(pagine, "/telefonia") == {
        "categoria": {"(radice)": 1},
        "prodotto": {"accessori": 2, "smartphone": 1, "(radice)": 1},
    }
    # senza perimetro il gruppo e' il primo tratto del percorso
    assert competitor_seo._composizione(pagine[2:3], "") == {"prodotto": {"telefonia": 1}}


def test_il_report_mostra_la_composizione_e_segnala_gli_indirizzi_404(monkeypatch):
    sito = _negozio_finto()
    sito["https://esempio.it/prodotto/telefono-7/"] = (404, "")
    _sito_finto(monkeypatch, sito)

    report = analizza_seo_sito("https://esempio.it")

    assert report["campione"]["composizione"]["prodotto"] == {"prodotto": 8}
    assert any("rispondono 404" in a and "sitemap non e' aggiornata" in a for a in report["avvisi"])
    assert any(s["motivo"] == "HTTP 404" for s in report["campione"]["pagine_saltate"])


# --- indirizzo di una pagina di categoria (categorie piatte, es. /it/category/x-1001.html) ---


def test_e_pagina_distingue_pagine_cartelle_e_radice():
    assert competitor_seo._e_pagina("https://esempio.it/it/category/telefoni-1001.html")
    assert competitor_seo._e_pagina("https://esempio.it/shop.php")
    assert not competitor_seo._e_pagina("https://esempio.it/telefonia/")
    assert not competitor_seo._e_pagina("https://esempio.it/telefonia")
    assert not competitor_seo._e_pagina("https://esempio.it/")
    assert not competitor_seo._e_pagina("https://esempio.it/dir.v2/sezione/")
    assert competitor_seo._perimetro("https://esempio.it/it/category/telefoni-1001.html") == ""


def _categoria_piatta():
    base = "https://esempio.it"
    prodotti = [f"{base}/it/product/_marca-modello-{i}-{9000 + i}.html" for i in range(12)]
    sottocategorie = [f"{base}/it/category/{c}-100{i}.html" for i, c in enumerate("abc", 2)]
    link = "".join(f'<a href="{u}">x</a>' for u in prodotti + sottocategorie)
    pagina_categoria = (
        "<html><head><title>Smartphone e cellulari al miglior prezzo | Negozio</title>"
        '<meta name="description" content="La migliore selezione di smartphone e cellulari delle '
        'migliori marche a ottimi prezzi, con consegna rapida e ritiro in negozio."></head>'
        f"<body><h1>Smartphone e cellulari</h1>{link}</body></html>"
    )
    sito = {f"{base}/it/category/telefoni-1001.html": (200, pagina_categoria)}
    for u in prodotti + sottocategorie:
        sito[u] = (200, _pagina_html(u.rsplit("/", 1)[1], u.rsplit("/", 1)[1]))
    # la sitemap esiste ma non deve servire: contiene prodotti di altri reparti
    altri = "".join(f"<url><loc>{base}/it/product/_tv-{i}.html</loc></url>" for i in range(50))
    sito[f"{base}/sitemap.xml"] = (200, f"<urlset>{altri}</urlset>")
    return sito, prodotti, sottocategorie


def test_indirizzo_di_una_pagina_di_categoria_campiona_dai_suoi_link(monkeypatch):
    sito, prodotti, sottocategorie = _categoria_piatta()
    richieste = _sito_finto(monkeypatch, sito)

    report = analizza_seo_sito(
        "https://esempio.it/it/category/telefoni-1001.html", max_categorie=10, max_prodotti=30
    )

    assert "errore" not in report
    assert report["perimetro"] == "pagina /it/category/telefoni-1001.html"
    assert report["pagine"][0]["tipo"] == "sezione"
    assert (report["campione"]["categorie"], report["campione"]["prodotti"]) == (3, 12)
    campionati = {p["url"] for p in report["pagine"][1:]}
    assert campionati == set(prodotti) | set(sottocategorie)
    assert not any("_tv-" in r for r in richieste)  # nessun prodotto dalla sitemap
    assert not any(r.endswith("sitemap.xml") for r in richieste)  # e nemmeno scaricata
    assert any("pagina di categoria" in a for a in report["avvisi"])
    assert "it" not in report["campione"]["composizione"]["prodotto"]  # il prefisso /it/ si salta


def test_la_valutazione_di_una_pagina_di_categoria_non_penalizza_la_sitemap(monkeypatch):
    sito, _, _ = _categoria_piatta()
    _sito_finto(monkeypatch, sito)

    report = analizza_seo_sito("https://esempio.it/it/category/telefoni-1001.html")

    criteri = [c["criterio"] for c in report["valutazione"]["aree"]["tecnico"]["criteri"]]
    assert "sitemap" not in criteri and "HTTPS" in criteri


def test_gli_h3_di_menu_e_footer_non_contano_per_la_gerarchia():
    html = (
        "<html><body><header><h3>Menu</h3></header><h1>Titolo</h1><h2>Sezione</h2><h3>Dettaglio</h3>"
        "<footer><h3>Contatti</h3><h3>Orari</h3></footer></body></html>"
    )
    pagina, _ = _estrai_pagina(html, "https://esempio.it/p/", "prodotto", "esempio.it")
    assert pagina["n_h3"] == 1  # solo quello del contenuto


def test_browser_visibile_implica_il_browser_e_si_avvia_con_la_finestra(monkeypatch):
    uso = _installa_browser(monkeypatch, _negozio_finto())
    _http_limitato(monkeypatch, _Risposta(403, "https://esempio.it/", ""))

    report = analizza_seo_sito("https://esempio.it", browser_visibile=True)  # senza usa_browser

    assert report["metodo"] == "browser"
    assert uso["visibile"] == [True]
    assert any("con la finestra visibile" in a for a in report["avvisi"])


def test_il_browser_normale_resta_senza_finestra(monkeypatch):
    uso = _installa_browser(monkeypatch, _negozio_finto())
    _http_limitato(monkeypatch, _Risposta(403, "https://esempio.it/", ""))

    report = analizza_seo_sito("https://esempio.it", usa_browser=True)

    assert uso["visibile"] == [False]
    assert not any("finestra visibile" in a for a in report["avvisi"])


def test_browser_visibile_anche_con_la_variabile_d_ambiente(monkeypatch):
    monkeypatch.setenv("SEO_ANALISI_BROWSER_VISIBILE", "1")
    uso = _installa_browser(monkeypatch, _negozio_finto())
    _http_limitato(monkeypatch, _Risposta(403, "https://esempio.it/", ""))

    analizza_seo_sito("https://esempio.it")

    assert uso["visibile"] == [True]


def test_il_trasporto_browser_chiede_la_finestra_solo_se_visibile(monkeypatch):
    richieste = []

    def avvio_finto(visibile=False):
        richieste.append(visibile)
        raise RuntimeError("non serve davvero avviare Chromium")

    monkeypatch.setattr(competitor_seo, "_avvia_playwright", avvio_finto)
    monkeypatch.setattr(competitor_seo, "_risolvi", lambda host: ["93.184.216.34"])
    for visibile in (False, True):
        with pytest.raises(ErroreAnalisi, match="Browser non disponibile"):
            competitor_seo._Browser(visibile).scarica("https://esempio.it/", "esempio.it")
    assert richieste == [False, True]


# --- elenchi senza estensione, con i prodotti in un altro percorso (/l/... e /p/...) ---


def test_riconosce_gli_indirizzi_di_elenco_e_di_prodotto_brevi():
    assert (
        competitor_seo._tipo_da_percorso("https://esempio.it/it-it/p/iphone-15/abc-123")
        == "prodotto"
    )
    assert (
        competitor_seo._tipo_da_percorso("https://esempio.it/it-it/l/smartphone/abc-123")
        == "categoria"
    )
    assert competitor_seo._tipo_da_percorso("https://esempio.it/it-it/chi-siamo") is None
    assert (
        competitor_seo._tipo_da_percorso("https://esempio.it/app/pagina") is None
    )  # "/app/" non e' "/p/"


def _elenco_con_prodotti_altrove():
    base = "https://esempio.it"
    prodotti = [f"{base}/it-it/p/telefono-{i}/id-{i:04d}" for i in range(14)]
    liste = [f"{base}/it-it/l/{c}/id-l{i}" for i, c in enumerate(("android", "ios", "tablet"))]
    elenco = f"{base}/it-it/l/smartphone/6c29-0010"
    link = "".join(f'<a href="{u}">x</a>' for u in prodotti + liste)
    pagina_elenco = (
        "<html><head><title>Smartphone ricondizionati | Negozio</title></head>"
        f"<body><h1>Smartphone ricondizionati</h1>{link}</body></html>"
    )
    sito = {elenco: (200, pagina_elenco)}
    for u in prodotti + liste:
        sito[u] = (200, _pagina_html("Pagina", "Pagina"))
    # sitemap senza niente sotto il percorso dell'elenco
    sito[f"{base}/sitemap.xml"] = (
        200,
        f"<urlset><url><loc>{base}/it-it/chi-siamo</loc></url></urlset>",
    )
    return sito, elenco, prodotti, liste


def test_se_sotto_il_percorso_non_c_e_niente_si_usano_i_link_della_pagina(monkeypatch):
    sito, elenco, prodotti, liste = _elenco_con_prodotti_altrove()
    # come su Back Market: la sitemap elenca anche la pagina da cui si parte (e' un'"elenco")
    sito["https://esempio.it/sitemap.xml"] = (
        200,
        f"<urlset><url><loc>{elenco}</loc></url><url><loc>https://esempio.it/it-it/chi-siamo</loc></url></urlset>",
    )
    _sito_finto(monkeypatch, sito)

    report = analizza_seo_sito(elenco, max_prodotti=30)

    assert report["perimetro"] == "pagina /it-it/l/smartphone/6c29-0010"
    assert (report["campione"]["categorie"], report["campione"]["prodotti"]) == (3, 14)
    assert {p["url"] for p in report["pagine"][1:]} == set(prodotti) | set(liste)
    assert any("collegati da quella pagina" in a for a in report["avvisi"])
    assert elenco not in [
        p["url"] for p in report["pagine"][1:]
    ]  # la pagina iniziale non si ripete
    # la sitemap e' stata letta, quindi il criterio resta valutabile
    criteri = [c["criterio"] for c in report["valutazione"]["aree"]["tecnico"]["criteri"]]
    assert "sitemap" in criteri


def test_con_prodotti_sotto_il_percorso_non_si_passa_ai_link(monkeypatch):
    """Il passaggio ai link scatta solo se il percorso non contiene nulla."""
    _sito_finto(monkeypatch, _sito_con_sezioni())

    report = analizza_seo_sito("https://esempio.it/telefonia/")

    assert report["perimetro"] == "/telefonia"
    assert not any("collegati da quella pagina" in a for a in report["avvisi"])


def test_composizione_salta_anche_il_prefisso_lingua_con_paese():
    pagine = [
        {"tipo": "prodotto", "url": "https://esempio.it/it-it/p/iphone-16"},
        {"tipo": "prodotto", "url": "https://esempio.it/it-it/p/iphone-15/abc"},
        {"tipo": "categoria", "url": "https://esempio.it/it/l/telefoni/id"},
    ]
    # saltato "it-it" / "it", il gruppo e' il tratto successivo: qui /p/ e /l/
    assert competitor_seo._composizione(pagine, "") == {
        "prodotto": {"p": 2},
        "categoria": {"l": 1},
    }


def test_nel_passaggio_ai_link_anche_le_categorie_vengono_dalla_pagina(monkeypatch):
    """Se la sitemap sotto il percorso offre meno categorie di quelle collegate dalla pagina."""
    sito, elenco, prodotti, liste = _elenco_con_prodotti_altrove()
    # la sitemap elenca una sola categoria sotto il percorso (diversa dalla pagina iniziale)
    sito["https://esempio.it/sitemap.xml"] = (
        200,
        f"<urlset><url><loc>{elenco}/sottolista</loc></url></urlset>",
    )
    _sito_finto(monkeypatch, sito)

    report = analizza_seo_sito(elenco, max_categorie=10, max_prodotti=30)

    assert report["campione"]["categorie"] == 3  # le liste collegate dalla pagina
    assert report["campione"]["prodotti"] == 14
