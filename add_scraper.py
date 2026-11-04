"""
Holland Pharma — add-feed (nieuwe producten aanmaken) voor Stock Sync
=====================================================================
Zelfde witte lijst en leeslaag als scraper.py, maar met alles wat een nieuw product
nodig heeft: titel, merk, type, tags, foto en een beschrijving met de etiketinformatie.

Snoep is een levensmiddel: wie het online verkoopt, moet de verplichte informatie vóór
de aankoop tonen (EU 1169/2011 art. 14): ingrediënten, voedingswaarde, bewaaradvies en
wie het in de handel brengt. Die komen hier letterlijk van het etiket (Holland Pharma),
zodat het product ook zonder Nova-tekst klopt. Een product zonder ingrediëntenlijst
komt NIET in de add-feed (wel in de update-feed): eerst het etiket, dan de winkel.

- tags: `drempelvuller` (tot DREMPEL_MAX, voor de winkelwagen-collectie), `hollandpharma`, btw-tag
- niet leverbaar (voorraadbalk 1-2) → nog niet aanmaken; komt mee zodra het leverbaar is
- published=false: Max zet ze zelf live na Nova en Themis
- price = adviesprijs incl. btw; voorraad loopt via de update-feed
"""
from __future__ import annotations

import html
import xml.etree.ElementTree as ET

import hp
from scraper import save_xml

OUTPUT_FILE = "hollandpharma_add_feed.xml"

# Tot dit bedrag (adviesprijs incl. btw) krijgt een product de tag `drempelvuller` en komt het
# in de winkelwagen-vuller. Duurdere artikelen (cadeauverpakkingen) komen wel in de winkel.
DREMPEL_MAX = 15.00


def beschrijving(p: dict) -> str:
    e = html.escape
    delen = [f"<p>{e(p['merk'])} {e(p['omschrijving'])}, {e(p['inhoud'].lower())}.</p>"]
    delen.append(f"<p><strong>Ingrediënten:</strong> {e(p['ingredienten'])}</p>")
    if p.get("allergenen"):
        delen.append(f"<p><strong>Allergenen:</strong> {e(p['allergenen'])}</p>")
    waarden = p.get("voedingswaarde") or []
    if waarden:
        kop = next((w for n, w in waarden if not n), "Voedingswaarde")
        regels = "".join(f"<li>{e(n)}: {e(w)}</li>" for n, w in waarden if n)
        delen.append(f"<p><strong>{e(kop)}</strong></p><ul>{regels}</ul>")
    if p.get("gebruik"):
        delen.append(f"<p><strong>Gebruik:</strong> {e(p['gebruik'])}</p>")
    if p.get("bewaren"):
        delen.append(f"<p><strong>Bewaren:</strong> {e(p['bewaren'])}</p>")
    if p.get("verantwoordelijk"):
        delen.append(f"<p><strong>In de handel gebracht door:</strong> {e(p['verantwoordelijk'])}</p>")
    return "\n".join(delen)


soort = hp.soort  # 04-11: in hp.py, want de bijwerk-feed geeft hem ook mee


def bouw(artikelen: list[str], gelezen: dict[str, dict]) -> tuple[ET.Element, list[str], list[str]]:
    root = ET.Element("products")
    zonder_etiket, niet_leverbaar = [], []
    for artikel in artikelen:
        p = gelezen.get(artikel) or {}
        if not p or not p.get("avp"):
            continue
        if not p.get("ingredienten"):
            zonder_etiket.append(f"{artikel} {p['merk']} {p['omschrijving']}")
            continue
        leverbaar, _ = hp.beschikbaar(p)
        if not leverbaar:
            niet_leverbaar.append(f"{artikel} {p['merk']} {p['omschrijving']}")
            continue
        vuller = "drempelvuller" if p["avp"] <= DREMPEL_MAX else ""
        tags = ", ".join(t for t in (vuller, "hollandpharma", p["artikelgroep"].lower(), hp.btw_tag(p)) if t)
        # Plat: één <product>-regel, geen geneste <variants>. Stock Sync leest een
        # <variants> met precies één <variant> als los object en slaat die rij
        # dan zonder melding over (Kala, 24-09-2026: 6 van 81 producten weg).
        # Instellingen in Stock Sync zoals bij de andere feeds: variant-node leeg,
        # variantgroep = handle, optie 1 = option1.
        item = ET.SubElement(root, "product")
        for tag, waarde in (("handle", hp.handle(p)), ("title", hp.titel(p)), ("vendor", p["merk"]),
                            ("brand", p["merk"]), ("product_type", p["artikelgroep"]), ("tags", tags),
                            ("published", "false"), ("btw", p["btw"]), ("description", beschrijving(p)),
                            ("ingredienten", p["ingredienten"]), ("bewaren", p.get("bewaren", "")),
                            ("waarschuwingen", p.get("gebruik", "")),
                            ("soort", soort(p)),
                            ("sku", hp.sku(p)), ("barcode", p["ean"]), ("price", f"{p['avp']:.2f}"),
                            ("compare_at_price", ""), ("available", "true" if leverbaar else "false"),
                            ("variant_title", "Default Title"), ("option1", "Default Title"),
                            ("image", p["foto"])):
            ET.SubElement(item, tag).text = waarde
    return root, zonder_etiket, niet_leverbaar


def main() -> None:
    s = hp.sessie()
    print("Holland Pharma add-feed: witte lijst uitvouwen")
    artikelen, _ = hp.artikelen(s)
    print(f"   {len(artikelen)} artikelen in totaal")
    gelezen = hp.haal_alles(artikelen, s)
    hp.rem(gelezen)
    root, zonder_etiket, niet_leverbaar = bouw(artikelen, gelezen)
    for regel in zonder_etiket:
        print(f"   NIET in de add-feed (geen ingrediëntenlijst op de pagina): {regel}")
    for regel in niet_leverbaar:
        print(f"   (nog) niet in de add-feed, niet leverbaar bij Holland Pharma: {regel}")
    print(f"{len(root.findall('product'))} producten in de add-feed")
    save_xml(root, OUTPUT_FILE)
    print(f"https://raw.githubusercontent.com/Maximillian-creator/hollandpharma-feed/main/{OUTPUT_FILE}")


if __name__ == "__main__":
    main()
