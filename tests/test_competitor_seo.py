import pytest
import requests

from push_contempt_mcp import competitor_seo
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
def _senza_pause_e_rete_privata(monkeypatch):
    monkeypatch.setattr(competitor_seo, "PAUSA_SECONDI", 0)
    monkeypatch.delenv("SEO_ANALISI_CONSENTI_RETE_PRIVATA", raising=False)


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


def test_estrai_pagina_conta_solo_le_parole_del_contenuto_e_non_le_restituisce():
    pagina, _ = _estrai_pagina(PAGINA, "https://esempio.it/p/", "prodotto", "esempio.it")

    # h1 (3) + h2 x2 (4) + h3 (1) + paragrafo (11) + testi dei link in main (7) = 26: niente
    # menu, script, footer, titolo
    assert pagina["n_parole"] == 26
    assert not any("batteria" in str(valore) for valore in pagina.values())


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


def _pagina_html(titolo, h1, h2=("Caratteristiche", "Spedizione"), schema="Product"):
    return f"""<html lang="it"><head><title>{titolo} | Negozio Esempio</title>
<meta name="description" content="Descrizione di {titolo} con tutte le informazioni utili.">
<script type="application/ld+json">{{"@type": "{schema}"}}</script></head>
<body><h1>{h1}</h1>{"".join(f"<h2>{t}</h2>" for t in h2)}<p>Testo segreto del concorrente.</p>
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
        sito[url] = (200, _pagina_html(f"Telefono {i}", f"Telefono {i}"))
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
    assert {"testo": "caratteristiche", "pagine": 9} in prodotti["h2_ricorrenti"]
    assert report["riepilogo_per_tipo"]["categoria"]["dati_strutturati"] == {"CollectionPage": 3}
    assert {"termine": "negozio", "pagine": 13} in report["parole_ricorrenti"]
    assert "non copiare" in report["nota_uso"]


def test_il_report_non_contiene_il_testo_delle_pagine(monkeypatch):
    _sito_finto(monkeypatch, _negozio_finto())
    assert "segreto" not in str(analizza_seo_sito("https://esempio.it"))


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
