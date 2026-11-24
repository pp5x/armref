"""Build a static Arm reference from the Arm XML release bundles."""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import SplitResult, urlsplit, urlunsplit

import click
from lxml import etree, html

XSL = "{http://www.w3.org/1999/XSL/Transform}"
XHTML = "{http://www.w3.org/1999/xhtml}"
ROOT = Path(__file__).resolve().parent
RELEASE = "2026-09"
# Pagefind indexes Unicode connector punctuation by default.
PAGEFIND_CHARACTERS = "_\u203f\u2040\u2054\ufe33\ufe34\ufe4d\ufe4e\ufe4f\uff3f"
WEIGHTED_TITLE = {
    "data-pagefind-body": "1",
    "data-pagefind-weight": "10",
    "data-pagefind-sort": "title",
}
PAGEFIND_BODY = {"data-pagefind-body": "1"}
BROWSE = {
    "latest_aarch64": {
        "index.html": "Base",
        "fpsimdindex.html": "SIMD and FP",
        "sveindex.html": "SVE",
        "mortlachindex.html": "SME",
    },
    "latest_sysreg": {
        "AArch64-regindex.html": "AArch64 registers",
        "AArch32-regindex.html": "AArch32 registers",
    },
}
MARKER = ".armref-build"


@dataclass(frozen=True)
class Corpus:
    source: Path
    route: str
    fallback: tuple[str, ...]


def corpora(source: Path, release: str) -> tuple[Corpus, Corpus]:
    return (
        Corpus(
            source / "isa_a64" / f"ISA_A64_xml_A_profile-{release}",
            "latest_aarch64",
            ("encodingindex.xml",),
        ),
        Corpus(
            source / "sysreg" / f"SysReg_xml_A_profile-{release}",
            "latest_sysreg",
            ("enc_index.xml", "ext_enc_index.xml", "func_index.xml"),
        ),
    )


def xml_parser() -> etree.XMLParser:
    return etree.XMLParser(no_network=True, load_dtd=False, resolve_entities=False)


def prepare_register_stylesheet(sheet: etree._ElementTree) -> None:
    """Add search markup where the vendor stylesheet knows the field boundaries."""
    template = sheet.find(f"{XSL}template[@match='register|register_block']")
    heading = template.find(f"{XHTML}h1")
    heading.attrib.update(WEIGHTED_TITLE)
    long_name = heading.find(f"{XSL}if[@test='reg_long_name']")
    heading.remove(long_name)
    subtitle = etree.SubElement(long_name, f"{XHTML}p", attrib=PAGEFIND_BODY)
    subtitle.set("class", "insn_subtitle")
    subtitle.text = long_name.text.removeprefix(", ")
    long_name.text = None
    subtitle.append(long_name.find(f"{XSL}value-of"))
    heading.addnext(long_name)

    purpose = sheet.find(f"{XSL}template[@match='reg_purpose']")
    purpose.remove(purpose.find(f"{XHTML}h2"))
    text = purpose.find(f"{XSL}for-each")
    wrapper = etree.SubElement(purpose, f"{XHTML}div", attrib=PAGEFIND_BODY)
    wrapper.append(text)


def mark_instruction_prose(sheet: etree._ElementTree) -> None:
    paragraphs = sheet.xpath(
        "//h:p[@class='aml'][not(ancestor::xsl:template"
        "[@match='operationalnote/operationalnote_titles'])]",
        namespaces={"h": XHTML[1:-1], "xsl": XSL[1:-1]},
    )
    for paragraph in paragraphs:
        paragraph.attrib.update(PAGEFIND_BODY)


def compile_stylesheet(path: Path) -> etree.XSLT:
    sheet = etree.parse(path, xml_parser())
    if path.name == "one_register.xsl":
        prepare_register_stylesheet(sheet)
    if path.name == "iform.xsl":
        mark_instruction_prose(sheet)
    return etree.XSLT(
        sheet,
        access_control=etree.XSLTAccessControl(
            read_network=False, write_network=False, write_file=False, create_dir=False
        ),
    )


def stylesheet_name(doc: etree._ElementTree) -> str | None:
    instructions = doc.xpath('/processing-instruction("xml-stylesheet")')
    return instructions[0].get("href") if instructions else None


def transform(
    path: Path, stylesheets: dict[str, etree.XSLT]
) -> tuple[html.HtmlElement, etree._ElementTree] | None:
    doc = etree.parse(path, xml_parser())
    name = stylesheet_name(doc)
    if name is None:
        return None
    if Path(name).name != name or not name.endswith(".xsl"):
        msg = f"{path}: invalid stylesheet name {name!r}"
        raise ValueError(msg)
    if name not in stylesheets:
        stylesheets[name] = compile_stylesheet(path.parent / name)
    result = stylesheets[name](doc)
    return html.document_fromstring(bytes(result)), doc


def add(
    parent: html.HtmlElement, tag: str, text: str = "", **attributes: str
) -> html.HtmlElement:
    element = html.Element(tag, attrib=attributes)
    element.text = text or None
    parent.append(element)
    return element


def nav_links(parent: html.HtmlElement, links: dict[str, str], prefix: str) -> None:
    for path, label in links.items():
        add(parent, "a", label, href=prefix + path)


def shell(page: html.HtmlElement, title: str, prefix: str) -> html.HtmlElement:
    head = page.find("head")
    body = page.find("body")
    head.clear()
    add(head, "meta", charset="utf-8")
    add(head, "meta", name="viewport", content="width=device-width, initial-scale=1")
    add(head, "title", title)
    for stylesheet in ("pagefind/pagefind-component-ui.css", "static/reference.css"):
        add(head, "link", rel="stylesheet", href=prefix + stylesheet)
    add(head, "script", type="module", src=prefix + "pagefind/pagefind-component-ui.js")
    return body


def page_header(
    body: html.HtmlElement, prefix: str, *, autofocus: bool = False
) -> None:
    header = html.Element("header", attrib={"class": "site-header"})
    body.insert(0, header)
    add(header, "a", "Arm Reference", href=prefix + "index.html")
    search = add(header, "pagefind-searchbox", shortcut="mod+k")
    if autofocus:
        search.set("autofocus", "")


def landing(prefix: str) -> html.HtmlElement:
    page = html.document_fromstring("<html><head></head><body></body></html>")
    body = shell(page, "Arm Reference", prefix)
    page_header(body, prefix, autofocus=True)
    main = add(body, "main")
    add(main, "h1", "Arm Reference")
    for route, label in (
        ("latest_aarch64", "AArch64 instructions"),
        ("latest_sysreg", "System registers"),
    ):
        add(main, "h2", label)
        nav = add(main, "nav", **{"aria-label": label})
        nav_links(nav, BROWSE[route], f"{prefix}{route}/")
    return page


def normalize_instruction(body: html.HtmlElement, doc: etree._ElementTree) -> None:
    headings = body.find_class("instruction-section")
    if not headings:
        return
    heading = headings[0]
    heading.tag = "h1"
    heading.attrib.update(WEIGHTED_TITLE)
    if doc.getroot().get("type") == "pseudocode":
        return
    brief = doc.xpath("normalize-space(desc/brief)")
    following = heading.getnext()
    if brief and following is not None and following.tag == "p":
        following.set("class", "insn_subtitle")
        following.attrib.update(PAGEFIND_BODY)


def wrap_diagrams(body: html.HtmlElement) -> None:
    for diagram in body.find_class("regdiagram"):
        if diagram.tag != "table":
            continue
        wrapper = html.Element("div", attrib={"class": "diagram-scroll"})
        diagram.addprevious(wrapper)
        wrapper.append(diagram)


def remove_upstream_navigation(body: html.HtmlElement) -> None:
    for topbar in body.xpath("./table[.//div[@class='topbar']]"):
        body.remove(topbar)
    for spacer in body.xpath("./hr[1][not(@class) and not(preceding-sibling::*)]"):
        body.remove(spacer)


def local_document(link: str) -> SplitResult | None:
    parts = urlsplit(link)
    if parts.scheme or parts.netloc or "/" in parts.path:
        return None
    if Path(parts.path).suffix not in {".xml", ".html"}:
        return None
    return parts


def rewrite_links(body: html.HtmlElement) -> set[str]:
    targets = set()
    for link in body.xpath(".//a[@href]"):
        href = link.get("href")
        parts = local_document(href)
        if parts is None:
            continue
        target = Path(parts.path).with_suffix(".html").name
        link.set("href", urlunsplit(parts._replace(path=target)))
        targets.add(target)
    return targets


def render_document(
    page: html.HtmlElement, doc: etree._ElementTree, route: str, filename: str
) -> set[str]:
    original_title = page.findtext("head/title", "").removesuffix(" -- A64")
    body = shell(page, f"{original_title} | Arm Reference", "../")
    remove_upstream_navigation(body)
    targets = rewrite_links(body)
    for label in body.find_class("note-header"):
        label.drop_tree()
    if route == "latest_aarch64":
        normalize_instruction(body, doc)
    wrap_diagrams(body)
    page_header(body, "../")
    if filename in BROWSE[route]:
        nav = html.Element("nav", attrib={"aria-label": "Browse reference"})
        body.insert(1, nav)
        nav_links(nav, BROWSE[route], "")
    return targets


def write_page(path: Path, page: html.HtmlElement) -> None:
    path.write_bytes(html.tostring(page, encoding="utf-8", doctype="<!doctype html>"))


def render_pages(corpus: Corpus, output: Path) -> set[str]:
    stylesheets: dict[str, etree.XSLT] = {}
    targets = {Path(name).with_suffix(".html").name for name in corpus.fallback}
    for source in sorted(corpus.source.glob("*.xml")):
        if source.name in corpus.fallback:
            continue
        transformed = transform(source, stylesheets)
        if transformed is None:
            continue
        page, doc = transformed
        name = source.with_suffix(".html").name
        targets.update(render_document(page, doc, corpus.route, name))
        write_page(output / name, page)

    return targets


def render_corpus(corpus: Corpus, destination: Path) -> None:
    output = destination / corpus.route
    output.mkdir()
    targets = render_pages(corpus, output)
    for name in sorted(targets):
        if not (output / name).exists():
            write_page(output / name, landing("../"))
    for asset in sorted(corpus.source.glob("*.svg")):
        shutil.copyfile(asset, output / asset.name)


def index_site(path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "pagefind",
        "--site",
        str(path),
    ]
    subprocess.run(command, check=True)


def validate_output(output: Path) -> None:
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        msg = f"Output must be a directory: {output}"
        raise ValueError(msg)
    if output.exists() and any(output.iterdir()) and not (output / MARKER).is_file():
        msg = f"Output contains files from outside this generator: {output}"
        raise ValueError(msg)


def publish(site: Path, output: Path) -> None:
    validate_output(output)
    if not output.exists():
        site.rename(output)
        return
    previous = site.parent / "previous"
    output.rename(previous)
    try:
        site.rename(output)
    except OSError:
        previous.rename(output)
        raise


def verify_sources(sources: tuple[Corpus, Corpus]) -> None:
    for corpus in sources:
        if not corpus.source.is_dir():
            msg = f"Missing XML release {corpus.source}. Run ./download.sh."
            raise ValueError(msg)
        for name in BROWSE[corpus.route]:
            if not (corpus.source / Path(name).with_suffix(".xml")).is_file():
                msg = f"Missing browse index {name} in {corpus.source}"
                raise ValueError(msg)


def build(source: Path, release: str, output: Path) -> None:
    sources = corpora(source.resolve(), release)
    verify_sources(sources)
    validate_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".armref-", dir=output.parent) as temporary:
        site = Path(temporary) / "site"
        site.mkdir()
        (site / "static").mkdir()
        shutil.copyfile(ROOT / "static/reference.css", site / "static/reference.css")
        write_page(site / "index.html", landing(""))
        for corpus in sources:
            render_corpus(corpus, site)
        index_site(site)
        (site / MARKER).touch()
        publish(site, output)


@click.command()
@click.option(
    "--source", type=click.Path(path_type=Path), default=ROOT / "ref", show_default=True
)
@click.option("--release", default=RELEASE, show_default=True)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=ROOT / "dist",
    show_default=True,
)
def main(source: Path, release: str, output: Path) -> None:
    """Generate the Arm reference website and build its Pagefind index."""
    if not re.fullmatch(r"\d{4}-\d{2}", release):
        msg = "Use YYYY-MM."
        raise click.BadParameter(msg, param_hint="--release")
    try:
        build(source, release, output.absolute())
    except (ValueError, OSError, etree.Error, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Built {output}")


if __name__ == "__main__":
    main()
