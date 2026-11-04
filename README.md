# Holland Pharma feeds → Stock Sync

Snoep en thee van **Holland Pharma** (`klant.hollandpharma.nl`, de groothandel van de
winkel in Beverwijk) als **drempelvullers** in de webshop. Er staat alleen in wat
`witte_lijst.txt` noemt. Holland Pharma voert duizenden drogisterijartikelen.

**Witte lijst (02-11):** hele merken.
- Klepper&Klepper en Barkleys (snoep).
- Pukka, Yogi Tea en Piramide (thee).

Een `merk:`-regel wordt elke run uitgevouwen via het merkfilter van de zoekpagina: 25 per
pagina, `&page=N`, uitgelogd leesbaar. Een nieuw product van dat merk komt dus vanzelf mee.
Met `-artikelnr` sluit je een artikel uit.

**STOP-regel:** komt een merk niet uit op het aantal dat Holland Pharma zelf noemt
("N producten gevonden"), dan wordt er niets weggeschreven.

**In de add-feed komen alleen producten die:**
- een ingrediëntenlijst hebben (toonbank-displays vallen daardoor vanzelf weg);
- leverbaar zijn (voorraadbalk 3 of hoger).

**Tag `drempelvuller`:** alleen tot €15 adviesprijs. Cadeauverpakkingen komen wel in de winkel, niet in de winkelwagen-vuller.

| Feed | Script | Output | Doel | Schema |
|---|---|---|---|---|
| **Update-feed** | `scraper.py` | `hollandpharma_feed.xml` | Prijs + voorraad bijwerken | 2× per dag (09:41 + 19:41 UTC) |
| **Add-feed** | `add_scraper.py` | `hollandpharma_add_feed.xml` | Nieuwe producten met etiketinformatie | ma 04:17 UTC + bij nieuwe witte lijst |

```
Update:  https://raw.githubusercontent.com/Maximillian-creator/hollandpharma-feed/main/hollandpharma_feed.xml
Add:     https://raw.githubusercontent.com/Maximillian-creator/hollandpharma-feed/main/hollandpharma_add_feed.xml
```

## Geen inlog, geen secrets

De productpagina's tonen ook uitgelogd:
- merk, omschrijving, inhoud en EAN;
- adviesprijs incl. btw en btw-code;
- voorraadbalk en foto;
- het etiket: ingrediënten, voedingswaarde, gebruik, bewaren en wie het in de handel brengt.

Alleen de **inkoopprijs** zit achter de inlog. Die hoort niet in dit openbare repo, en de
tests controleren dat hij er niet in staat.

## Velden

- **SKU** `HP-<artikelnr>`, **barcode** = EAN.
- **Prijs** = adviesprijs (AVP) incl. btw, 1-op-1. Daar komt geen btw meer bij in Stock Sync.
- **Voorraad**: Holland Pharma geeft een balk, geen aantallen. Het aantal hieronder is dus een schatting.

  | Balk | Tekst | Aantal in de feed |
  |---|---|---|
  | 6 | ruim voldoende | 20 |
  | 5 | voldoende | 10 |
  | 4 | — | 5 |
  | 3 | beperkte voorraad | 2 |
  | 1–2 | — | 0 (niet leverbaar) |

- **Handle** = merk + titel (`klepper-klepper-de-beste-drop-ooit-honing-200-gram`).
- **Tags**: `drempelvuller` (voor de winkelwagen-collectie), `hollandpharma`, artikelgroep en btw-tag.
- **Published** = `false`: Max zet ze live na Nova en Themis.

## Etiket = wettelijke plicht

Snoep is een levensmiddel. Bij online verkoop moet de verplichte informatie vóór de
aankoop zichtbaar zijn (EU 1169/2011 art. 14). De add-feed zet daarom deze onderdelen
letterlijk van het etiket in de beschrijving:
- ingrediënten;
- voedingswaarde;
- gebruik en waarschuwing, bijvoorbeeld zoethout of zoetstoffen;
- bewaren;
- wie het in de handel brengt.

Een product **zonder ingrediëntenlijst komt niet in de add-feed**.

**Nog na te lopen:**
- Zeven kleine verpakkingen hebben geen voedingswaarde op de pagina: de liquorice pellets en de suikervrije mints van 15 g. Is de grootste zijde kleiner dan 25 cm², dan is dat toegestaan (bijlage V, punt 18).
- Allergenen staan niet vet in de ingrediëntenlijst van de bron. Nova let daarop.

## De rem

- Is meer dan 20% van de witte lijst niet te lezen, dan wordt er niets weggeschreven.
- Een product dat één run niet te lezen is, houdt zijn regel uit de vorige feed. Zo archiveert Stock Sync het niet.
- `prijsrem.py` houdt een prijsverschil van meer dan 3% zonder btw-patroon tegen. `FORCE_PRIJZEN=1` laat het door.

## Stock Sync

- **Update**: koppel op SKU (of barcode) en map `price`, `available` en `quantity`.
- **Add**: kies "Add products", parent node `products.product[*]`, **variant-node leeg** (de feed is plat, één regel per product). Product-identificeerder `sku`, variantgroep `handle`, optie 1 `option1`. Map geen voorraad, zoals bij Deltastar.
  Optienaam 1 = **Title** (anders toont de winkelwagen "Inhoud: Default Title"). Metafield `custom.soort` ← `soort` (Thee/Snoep, filter op Kleine extra's).

## Lokaal

```bash
pip install requests pytest
python -m pytest -q test_feed.py   # zonder netwerk, op testdata/
python scraper.py && python add_scraper.py
```

Op Max' laptop onderschept Norton het https-verkeer. Python vertrouwt dat niet. Gebruik
daarom de Windows-certificaatopslag (`pip install truststore`):

```bash
python -c "import truststore; truststore.inject_into_ssl(); import scraper; scraper.main()"
```
