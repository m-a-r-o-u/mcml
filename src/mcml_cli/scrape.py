from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

import requests
from bs4 import BeautifulSoup

from .db import Person

BASE = "https://mcml.ai"
TEAM_ROOT = f"{BASE}/team/"

SEED_PAGES = [
    TEAM_ROOT,
    f"{BASE}/team/directors/",
    f"{BASE}/team/management/",
    f"{BASE}/team/researchgroups/",
    f"{BASE}/team/jrgs/",
    f"{BASE}/team/juniors/",
    f"{BASE}/team/tbfs/",
    f"{BASE}/team/strategyboard/",
    f"{BASE}/team/advisoryboard/",
    f"{BASE}/team/former/",
]

# Common academic titles and honorifics that appear as separate lines.
TITLE_TOKENS = {
    "Prof.",
    "Prof",
    "Dr.",
    "Dr",
    "Junior",
    "Representative",
}


def _clean_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _abs_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return BASE + url
    return BASE + "/" + url


def _dedupe_preserve(urls: Iterable[str]) -> list[str]:
    seen = set()
    out: list[str] = []
    for u in urls:
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _discover_team_pages() -> list[str]:
    """Find team subpages from the main navigation."""
    try:
        html = fetch_html(TEAM_ROOT)
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith("mailto:"):
            continue
        abs_url = _abs_url(href)
        if not abs_url.startswith(TEAM_ROOT):
            continue
        abs_url = abs_url.split("#", 1)[0].split("?", 1)[0].rstrip("/") + "/"
        urls.append(abs_url)

    # Always include the canonical list of expected team pages.
    urls.extend(SEED_PAGES)

    return _dedupe_preserve(urls)


def _looks_like_name(s: str) -> bool:
    s = _clean_ws(s)
    if not s or len(s) < 3:
        return False
    # Avoid section headings.
    lowered = s.lower()
    bad = {
        "home",
        "team",
        "back to top",
        "board of directors",
        "management team",
        "research groups",
        "junior research groups",
        "junior members",
        "postdocs",
        "phd students",
        "students",
    }
    if lowered in bad:
        return False
    # Require at least two name-like tokens.
    tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'.-]*", s)
    if len(tokens) < 2:
        return False
    if len(tokens) > 8:
        return False
    return True


def _split_name(full_name: str) -> tuple[str, str]:
    full_name = _clean_ws(full_name)
    parts = full_name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _person_score(p: Person) -> int:
    score = 0
    if p.mcml_url:
        score += 1
        if p.mcml_url.startswith(BASE):
            score += 1
    if p.note:
        score += 1
    if p.role and p.role.lower() != "member":
        score += 1
    return score


@dataclass
class _Candidate:
    full_name: str
    role: str
    note: str
    mcml_url: str


def fetch_html(url: str, timeout_s: int = 30) -> str:
    headers = {
        "User-Agent": "mcml-cli/0.1 (+https://mcml.ai/team/)"
    }
    try:
        r = requests.get(url, headers=headers, timeout=timeout_s)
        r.raise_for_status()
        return r.text
    except requests.RequestException:
        # Retry with http if https failed (some proxies block HTTPS tunneling).
        if url.startswith("https://"):
            alt_url = "http://" + url[len("https://") :]
            r = requests.get(alt_url, headers=headers, timeout=timeout_s)
            r.raise_for_status()
            return r.text
        raise


def _extract_candidates_from_page(html: str, page_url: str) -> list[_Candidate]:
    soup = BeautifulSoup(html, "html.parser")

    # Track current section (eg, "PostDocs", "PhD Students").
    current_section = ""

    candidates: list[_Candidate] = []

    # We iterate over elements in DOM order.
    for el in soup.find_all(["h1", "h2", "h3", "h4", "h5", "p", "a", "strong", "li", "span", "div", "td"]):
        tag = el.name or ""
        text = _clean_ws(el.get_text(" ", strip=True))

        if tag == "h2" and text:
            current_section = text
            continue

        # Names can appear in various heading or inline tags across pages.
        if tag in {"h1", "h2", "h3", "h4", "h5", "strong", "li", "span", "div", "td", "a", "p"} and _looks_like_name(text):
            full_name = text

            # Collect nearby text in the same container to infer role/note.
            container = el.parent
            block_texts: list[str] = []
            block_links: list[str] = []

            if container:
                # Include text from following siblings inside the same container.
                for sib in el.find_all_next(["p", "a", "h3", "h4", "h5", "li", "span", "div"], limit=30):
                    if sib is el:
                        continue
                    if sib.name in {"h1", "h2", "h3", "h4", "h5", "strong"} and sib.get_text(strip=True) != "":
                        # Stop when the next person starts.
                        sib_text = _clean_ws(sib.get_text(" ", strip=True))
                        if _looks_like_name(sib_text):
                            break
                    if sib.name in {"p", "li", "span", "div"}:
                        t = _clean_ws(sib.get_text(" ", strip=True))
                        if t:
                            block_texts.append(t)
                    if sib.name == "a":
                        href = sib.get("href") or ""
                        if href:
                            block_links.append(_abs_url(href))

            # Decide role.
            role = ""
            note = ""

            # Pull role-like lines: shortish phrases, not biographies.
            for t in block_texts:
                if len(t) > 180:
                    continue
                if t in TITLE_TOKENS:
                    continue
                # Common pattern: role on its own line.
                if role == "" and ("manager" in t.lower() or "director" in t.lower() or "leader" in t.lower() or "fellow" in t.lower() or "coordinator" in t.lower() or "official" in t.lower()):
                    role = t
                    continue
                if role == "" and len(t.split()) <= 6:
                    # In juniors pages, explicit roles exist (Transfer Coordinator).
                    if any(k in t.lower() for k in ["coordinator", "fellow", "representative"]):
                        role = t
                        continue

            if not role:
                # Fall back to section name, if it looks meaningful.
                if current_section and len(current_section) <= 30:
                    role = current_section
                else:
                    role = "Member"

            # Find an MCML link: prefer internal mcml.ai links.
            mcml_url = ""
            internal = [u for u in block_links if u.startswith(BASE)]
            external = [u for u in block_links if not u.startswith(BASE)]
            if internal:
                mcml_url = internal[0]
            elif external:
                # As a fallback, store external personal homepages.
                mcml_url = external[0]

            # A short note: group affiliation is often in link text "→ Group ...".
            group_link = None
            for a in el.find_all_next("a", limit=25):
                txt = _clean_ws(a.get_text(" ", strip=True))
                href = a.get("href") or ""
                if "→" in txt or txt.startswith("Group"):
                    group_link = txt.replace("→", "").strip()
                    if href:
                        # Prefer group page as the MCML url.
                        mcml_url = _abs_url(href)
                    break

            if group_link:
                note = group_link

            candidates.append(_Candidate(full_name=full_name, role=role, note=note, mcml_url=mcml_url))

    # De-duplicate by (name, mcml_url, role)
    seen = set()
    out: list[_Candidate] = []
    for c in candidates:
        key = (c.full_name.lower(), (c.mcml_url or "").lower(), c.role.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def scrape_all(seed_pages: Optional[Iterable[str]] = None) -> list[Person]:
    base_pages = list(seed_pages) if seed_pages is not None else SEED_PAGES
    discovered = _discover_team_pages()
    pages = _dedupe_preserve(list(base_pages) + discovered)
    if not pages:
        pages = SEED_PAGES
    all_people: list[Person] = []

    for page in pages:
        html = fetch_html(page)
        cands = _extract_candidates_from_page(html, page_url=page)
        for c in cands:
            first, last = _split_name(c.full_name)
            all_people.append(
                Person(
                    full_name=c.full_name,
                    first_name=first,
                    last_name=last,
                    role=c.role,
                    note=c.note,
                    mcml_url=c.mcml_url,
                    source_page=page,
                )
            )

    # Further de-duplication across pages.
    by_exact = {}
    for p in all_people:
        key = (p.full_name.lower(), (p.mcml_url or "").lower(), p.role.lower())
        by_exact[key] = p

    # Merge entries that refer to the same person (same normalized full name).
    by_name: dict[str, Person] = {}
    for p in by_exact.values():
        name_key = _norm(p.full_name)
        existing = by_name.get(name_key)
        if existing is None:
            by_name[name_key] = p
            continue
        # Prefer richer records (MCML link, note, role info).
        if _person_score(p) > _person_score(existing):
            by_name[name_key] = p

    return list(by_name.values())
