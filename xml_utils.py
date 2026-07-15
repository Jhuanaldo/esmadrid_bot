import html
import xml.etree.ElementTree as ET
from datetime import datetime, date
from pathlib import Path
import re
import requests

XML_URL = "https://www.esmadrid.com/opendata/agenda_v1_es.xml"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_xml() -> bytes:
    resp = requests.get(XML_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.content


def parse_date_es(date_str: str) -> date | None:
    clean = re.sub(r"\s+", "", date_str.strip())
    try:
        return datetime.strptime(clean, "%d/%m/%Y").date()
    except ValueError:
        return None


def filter_and_save(xml_content: bytes, output_path: Path):
    root = ET.fromstring(xml_content)
    today = date.today()

    root_out = ET.Element("agenda")
    for service in root.findall(".//service"):
        fin = None
        for rango in service.findall(".//fechas/rango"):
            fin_elem = rango.find("fin")
            if fin_elem is not None and fin_elem.text:
                parsed = parse_date_es(fin_elem.text)
                if parsed and parsed >= today:
                    fin = parsed
                    break
        if fin is None:
            continue

        service_out = ET.SubElement(root_out, "service")
        for attr, val in service.attrib.items():
            service_out.set(attr, val)

        basic = service.find("basicData")
        if basic is not None:
            basic_out = ET.SubElement(service_out, "basicData")
            for tag in ("language", "name", "web"):
                el = basic.find(tag)
                if el is not None:
                    el_out = ET.SubElement(basic_out, tag)
                    el_out.text = decode(el.text)

        extra = service.find("extradata")
        if extra is not None:
            extra_out = ET.SubElement(service_out, "extradata")
            cats = extra.find("categorias")
            if cats is not None:
                cats_out = ET.SubElement(extra_out, "categorias")
                for cat in cats:
                    cats_out.append(cat)
            fechas = extra.find("fechas")
            if fechas is not None:
                fechas_out = ET.SubElement(extra_out, "fechas")
                for rango in fechas:
                    fechas_out.append(rango)

    tree = ET.ElementTree(root_out)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)


def load_filtered_data() -> list[dict]:
    path = Path(__file__).parent / "madrid_es_filtered.xml"
    if not path.exists():
        return []

    tree = ET.parse(path)
    root = tree.getroot()
    events = []

    for service in root.findall("service"):
        name = decode(service.findtext("basicData/name", ""))
        web = decode(service.findtext("basicData/web", ""))

        cats = []
        for cat in service.findall(".//categorias/categoria"):
            cat_name = decode(cat.findtext('item[@name="Categoria"]', ""))
            sub_names = []
            for sub in cat.findall(".//subcategoria"):
                sn = decode(sub.findtext('item[@name="SubCategoria"]', ""))
                if sn:
                    sub_names.append(sn)
            if cat_name:
                if sub_names:
                    for sn in sub_names:
                        cats.append((cat_name, sn))
                else:
                    cats.append((cat_name, ""))

        rango = service.find(".//fechas/rango")
        inicio = decode(rango.findtext("inicio", "")) if rango is not None else ""
        fin = decode(rango.findtext("fin", "")) if rango is not None else ""

        events.append({
            "name": name,
            "web": web,
            "categorias": cats,
            "inicio": inicio,
            "fin": fin,
        })

    return events


def format_events(events: list[dict]) -> str:
    lines = []
    for ev in events:
        for cat, subcat in ev["categorias"]:
            cat_str = f"{cat}, {subcat}" if subcat else cat
            lines.append(
                f"- {cat_str}: {ev['name']}, {ev['inicio']} - {ev['fin']} ({ev['web']})"
            )
    lines.sort(key=lambda l: l.lower().lstrip("- "))
    return "\n".join(lines)


def decode(val: str | None) -> str:
    return html.unescape(val) if val else ""


def get_categories() -> dict[str, list[str]]:
    raw = fetch_xml()
    root = ET.fromstring(raw)
    categories: dict[str, set[str]] = {}
    for service in root.findall(".//service"):
        for cat in service.findall(".//categorias/categoria"):
            cat_name = decode(cat.findtext('item[@name="Categoria"]', ""))
            if not cat_name:
                continue
            if cat_name not in categories:
                categories[cat_name] = set()
            for sub in cat.findall(".//subcategoria"):
                sub_name = decode(sub.findtext('item[@name="SubCategoria"]', ""))
                if sub_name:
                    categories[cat_name].add(sub_name)
    return {k: sorted(v) for k, v in sorted(categories.items())}
