"""Regole AEO e GEO per scrivere gli articoli del blog.

AEO (Answer Engine Optimization): scrivere in modo che motori di risposta e assistenti
vocali possano estrarre la risposta. GEO (Generative Engine Optimization): scrivere in modo
che le AI generative (ChatGPT, Perplexity, Gemini) capiscano e citino il negozio e i suoi
prodotti. Qui ci sono solo le regole che si applicano al TESTO di un articolo; quelle sul
sito (llms.txt, dati strutturati, recensioni, velocita') non c'entrano con l'articolo.

Il testo e' dentro il pacchetto e non legge nessun file: vale su qualunque installazione.
Lo restituiscono `leggi_brief_blog` e `contesto_blog` quando nel brief e' attiva l'opzione
`ottimizza_aeo_geo`.
"""

REGOLE_AEO_GEO = """\
Regole AEO e GEO per questo articolo (si aggiungono alle altre; se una regola spingesse a \
scrivere qualcosa di non verificato, vince sempre la regola di non inventare).

AEO - rendere il testo "estraibile" da motori di risposta e assistenti vocali:
1. Almeno meta dei sottotitoli H2/H3 sono domande vere che l'utente si fa, con Cosa, Come, \
Quale, Perche', Quanto, Dove (es. "Quanto dura la batteria di ...?").
2. Subito sotto ogni domanda scrivi la risposta in UN solo paragrafo <p> di 40-60 parole, che \
si regge da solo (mai "come detto sopra") e comincia con una definizione o una risposta \
diretta. I dettagli vengono dopo.
3. Per procedure, passaggi e liste di elementi usa elenchi veri (<ol> numerati per i passaggi, \
<ul> per gli elenchi). Per i confronti usa una tabella HTML vera (<table>, <thead> per le \
intestazioni, <tbody> per i dati), mai un'immagine.
4. Chiudi con una sezione di domande frequenti: 3-5 coppie domanda (H3) e risposta breve (<p>). \
Non scrivere JSON-LD o script: i dati strutturati li gestisce il plugin SEO.
5. Il primo paragrafo riassume in due frasi di cosa parla l'articolo e a chi serve.

GEO - farsi capire e citare dalle AI generative:
6. Contenuto non banale: oltre ai dati tecnici (che stanno gia' nella scheda e che chiunque \
ripete) aggiungi una sezione "Per chi e' pensato" e casi d'uso concreti, con i limiti detti \
onestamente. Un punto di vista originale vale piu' di una scheda riscritta.
7. Statistiche, numeri e citazioni di esperti aumentano le probabilita' di essere citati, ma \
SOLO se sono reali, verificabili e con la fonte linkata. Mai inventarli o arrotondarli a occhio.
8. Scrivi il nome del negozio, del marchio e del prodotto per esteso e sempre allo stesso modo \
(modello, versione, capacita'), senza pronomi vaghi al posto del nome: cosi' l'AI capisce di \
quale entita' si parla.
9. Cita e linka fonti autorevoli esterne (produttore, enti, testate): le AI si fidano dei testi \
che si appoggiano a fonti.

Fuori dall'articolo (non inserirli nel testo): llms.txt, dati strutturati JSON-LD, recensioni, \
velocita' del sito, menzioni su siti esterni.
"""
