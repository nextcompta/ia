"""
Navigateur robuste pour le portail professionnel impots.gouv.fr.
Gère la détection de pages, onglets, menus et libellés proches.
S'adapte aux variantes d'interface et enrichit le journal d'expérience.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    ElementHandle,
    Page,
    TimeoutError as PwTimeout,
    async_playwright,
)

from . import experience_log as log


# ── Constantes ──────────────────────────────────────────────────────────────

BASE_URL = "https://cfspro.impots.gouv.fr/mire/accueil.do"

# Variantes connues de libellés pour chaque concept de navigation
LABEL_VARIANTS: dict[str, list[str]] = {
    "champ_login": [
        "Identifiant",
        "Login",
        "Numéro SIRET",
        "Identifiant fiscal",
        "Votre identifiant",
        "N° abonné",
    ],
    "champ_password": [
        "Mot de passe",
        "Password",
        "Code secret",
        "Votre mot de passe",
    ],
    "bouton_connexion": [
        "Valider",
        "Se connecter",
        "Connexion",
        "OK",
        "Accéder",
        "Confirmer",
    ],
    "menu_consulter": [
        "Consulter",
        "Mes services",
        "Accéder à mes services",
        "Services",
        "Tableau de bord",
    ],
    "menu_cfe": [
        "CFE",
        "Cotisation Foncière des Entreprises",
        "Avis CFE",
        "Avis de CFE",
        "Avis d'imposition CFE",
        "Cotisation foncière",
    ],
    "liste_avis": [
        "Consulter les avis",
        "Avis disponibles",
        "Mes avis",
        "Liste des avis",
        "Avis d'imposition",
        "Voir les avis",
        "Accéder aux avis",
    ],
    "telecharger": [
        "Télécharger",
        "Téléchargement",
        "PDF",
        "Imprimer",
        "Visualiser",
        "Accéder au document",
        "Consulter l'avis",
    ],
}

TIMEOUT_MS = 15_000
NAV_TIMEOUT_MS = 30_000

# Sélecteurs CSS connus pour le formulaire de connexion
LOGIN_FIELD_SELECTORS = [
    "#identifiant", "#login", "#username", "#siren",
    "input[name='identifiant']", "input[name='login']",
    "input[name='username']", "input[name='siren']",
    "input[type='text']",
]
PASSWORD_FIELD_SELECTORS = [
    "#motDePasse", "#password", "#passwd", "#mdp",
    "input[name='motDePasse']", "input[name='password']",
    "input[name='passwd']", "input[type='password']",
]
SUBMIT_SELECTORS = [
    "button[type='submit']", "input[type='submit']",
    "#btnValider", "#valider", "#submit",
    "button:has-text('Valider')", "button:has-text('Connexion')",
    "a:has-text('Valider')",
]


# ── Helpers texte ────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_ = nfkd.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", ascii_.lower()).strip()


def _fuzzy_match(candidate: str, references: list[str], threshold: float = 0.55) -> bool:
    c = _normalize(candidate)
    for ref in references:
        r = _normalize(ref)
        if r in c or c in r:
            return True
        c_words = set(c.split())
        r_words = set(r.split())
        if not r_words:
            continue
        if len(c_words & r_words) / len(r_words) >= threshold:
            return True
    return False


# ── Détecteur de page ────────────────────────────────────────────────────────

@dataclass
class PageState:
    url: str
    title: str
    is_login: bool = False
    is_home: bool = False
    is_cfe_list: bool = False
    is_error: bool = False
    raw_text: str = ""


async def detect_page_state(page: Page) -> PageState:
    url = page.url
    title = await page.title()
    text = await page.evaluate("() => document.body?.innerText || ''")

    state = PageState(url=url, title=title, raw_text=text[:500])

    state.is_login = (
        any(k in url for k in ("login", "connexion", "oauth", "authenticate", "mire/accueil"))
        or _fuzzy_match(title, ["connexion", "authentification", "espace professionnel", "identifiant"])
    )
    state.is_home = "cfspro.impots.gouv.fr" in url and not state.is_login
    state.is_cfe_list = (
        _fuzzy_match(title, LABEL_VARIANTS["liste_avis"])
        or _fuzzy_match(text[:300], ["avis cfe", "cotisation fonciere", "liste des avis"])
    )
    state.is_error = (
        any(k in title.lower() for k in ("erreur", "error", "indisponible", "503", "404"))
        or "service momentanément indisponible" in text.lower()
    )

    log.record_snapshot(url, title)
    return state


# ── Résolution de sélecteur adaptive ────────────────────────────────────────

async def _first_visible(page: Page, selectors: list[str], timeout: int = 1_500) -> Optional[ElementHandle]:
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
            if el:
                return el
        except PwTimeout:
            pass
    return None


async def find_element(page: Page, concept: str, extra_variants: list[str] | None = None) -> Optional[ElementHandle]:
    """
    Cherche un élément cliquable correspondant au concept.
    Priorité : sélecteurs déjà validés → libellés fuzzy → XPath de secours.
    """
    variants = LABEL_VARIANTS.get(concept, []) + (extra_variants or [])
    known_selectors = log.best_selectors(concept)

    for sel in known_selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=2_000, state="visible")
            if el:
                log.record_selector(concept, sel, worked=True)
                return el
        except PwTimeout:
            pass

    for tag in ("a", "button", "li", "span", "div[role='tab']", "div[role='menuitem']", "td"):
        try:
            for el in await page.query_selector_all(tag):
                txt = await el.inner_text()
                if _fuzzy_match(txt, variants):
                    sel = f"{tag}:has-text('{txt[:40].strip()}')"
                    log.record_selector(concept, sel, worked=True)
                    return el
        except Exception:
            continue

    for label in variants:
        xpath = f"//*[contains(normalize-space(text()),'{label}')]"
        try:
            el = await page.wait_for_selector(f"xpath={xpath}", timeout=1_500, state="visible")
            if el:
                log.record_selector(concept, f"xpath={xpath}", worked=True)
                return el
        except PwTimeout:
            pass

    log.record_error(concept, "element_not_found", f"variants essayées : {variants[:3]}")
    return None


# ── Navigateur principal ─────────────────────────────────────────────────────

class CFENavigator:
    """
    Skill de navigation robuste vers les avis CFE.
    Navigateur visible (non-headless) recommandé pour éviter les blocages du portail.
    """

    def __init__(self, download_dir: str = "./telechargements_cfe", headless: bool = False):
        self.download_dir = download_dir
        self.headless = headless
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    # ── Cycle de vie ────────────────────────────────────────────────────────

    async def start(self, slow_mo: int = 120) -> None:
        import pathlib
        pathlib.Path(self.download_dir).mkdir(parents=True, exist_ok=True)

        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(
            headless=self.headless,
            slow_mo=slow_mo,
            args=[] if self.headless else ["--start-maximized"],
        )
        self.context = await self.browser.new_context(
            viewport=None,
            accept_downloads=True,
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        self.page = await self.context.new_page()

    async def close(self) -> None:
        if self.browser:
            await self.browser.close()
        if hasattr(self, "_pw"):
            await self._pw.stop()

    # ── Connexion ────────────────────────────────────────────────────────────

    async def open_portal(self) -> PageState:
        await self.page.goto(BASE_URL, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        await self.page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)
        return await detect_page_state(self.page)

    async def login(self, identifiant: str, mot_de_passe: str) -> bool:
        """
        Remplit et soumet le formulaire de connexion.
        Détecte automatiquement les champs par sélecteur CSS puis par label fuzzy.
        Retourne True si la connexion semble réussie.
        """
        print("[CFE] Recherche du formulaire de connexion…")

        # Champ identifiant
        field_login = await _first_visible(self.page, LOGIN_FIELD_SELECTORS)
        if not field_login:
            field_login = await find_element(self.page, "champ_login")
        if not field_login:
            log.record_error("login", "champ_identifiant_introuvable", self.page.url)
            return False
        await field_login.click()
        await field_login.fill("")
        await field_login.type(identifiant, delay=60)
        log.record_selector("champ_login", await _get_selector_hint(field_login), worked=True)

        # Champ mot de passe
        field_pwd = await _first_visible(self.page, PASSWORD_FIELD_SELECTORS)
        if not field_pwd:
            field_pwd = await find_element(self.page, "champ_password")
        if not field_pwd:
            log.record_error("login", "champ_password_introuvable", self.page.url)
            return False
        await field_pwd.click()
        await field_pwd.fill("")
        await field_pwd.type(mot_de_passe, delay=70)
        log.record_selector("champ_password", await _get_selector_hint(field_pwd), worked=True)

        # Bouton de validation
        btn = await _first_visible(self.page, SUBMIT_SELECTORS)
        if not btn:
            btn = await find_element(self.page, "bouton_connexion")
        if not btn:
            log.record_error("login", "bouton_connexion_introuvable", self.page.url)
            return False

        await btn.click()
        await self.page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT_MS)

        state = await detect_page_state(self.page)
        if state.is_error:
            log.record_error("login", "echec_apres_connexion", state.title)
            return False

        # Vérifie si on est toujours sur la page de login (mauvais identifiants ?)
        if state.is_login:
            error_text = await self.page.evaluate("() => document.body?.innerText || ''")
            if any(k in error_text.lower() for k in ("incorrect", "invalide", "erroné", "erreur")):
                log.record_error("login", "identifiants_incorrects", error_text[:200])
                print("[CFE] Erreur : identifiants incorrects.")
                return False

        print("[CFE] Connexion réussie.")
        return True

    async def handle_2fa_if_needed(self, wait_s: int = 90) -> bool:
        """
        Si une étape 2FA est détectée (OTP, SMS…), attend que l'utilisateur
        la complète manuellement dans le navigateur ouvert.
        """
        state = await detect_page_state(self.page)
        text = state.raw_text.lower()
        if not any(k in text for k in ("code", "otp", "sms", "authentification", "vérification")):
            return True  # pas de 2FA
        print(f"[CFE] Double authentification détectée. Complétez-la dans le navigateur ({wait_s}s)…")
        deadline = asyncio.get_event_loop().time() + wait_s
        while asyncio.get_event_loop().time() < deadline:
            state = await detect_page_state(self.page)
            if state.is_home:
                return True
            await asyncio.sleep(3)
        log.record_error("handle_2fa", "timeout", "2FA non complétée dans le délai")
        return False

    # ── Navigation ──────────────────────────────────────────────────────────

    async def navigate_to_cfe(self) -> PageState:
        """
        Navigue depuis la page d'accueil jusqu'à la liste des avis CFE.
        Tente les chemins déjà validés, puis l'exploration adaptive.
        """
        known_paths = log._load().get("navigation_paths", [])
        for path_entry in known_paths:
            try:
                result = await self._follow_path(path_entry["steps"])
                if result and result.is_cfe_list:
                    return result
            except Exception as exc:
                log.record_error("navigate_to_cfe", str(exc), f"chemin échoué : {path_entry['steps']}")

        steps_taken: list[str] = []

        el = await find_element(self.page, "menu_consulter")
        if el:
            steps_taken.append("click:menu_consulter")
            await el.click()
            await self.page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

        el = await find_element(self.page, "menu_cfe")
        if el:
            steps_taken.append("click:menu_cfe")
            await el.click()
            await self.page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

        el = await find_element(self.page, "liste_avis")
        if el:
            steps_taken.append("click:liste_avis")
            await el.click()
            await self.page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

        state = await detect_page_state(self.page)
        if steps_taken:
            log.record_navigation_path(steps_taken, label="chemin_exploratoire_valide")
        return state

    async def _follow_path(self, steps: list[str]) -> PageState | None:
        for step in steps:
            if step.startswith("click:"):
                el = await find_element(self.page, step[len("click:"):])
                if not el:
                    return None
                await el.click()
                await self.page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
            elif step.startswith("goto:"):
                await self.page.goto(step[len("goto:"):], wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
        return await detect_page_state(self.page)

    # ── Collecte et téléchargement ───────────────────────────────────────────

    async def list_available_notices(self) -> list[dict]:
        notices = []
        rows = await self.page.query_selector_all(
            "table tr, .avis-item, .list-item, li.avis, tr.ligne-avis"
        )
        for row in rows:
            text = await row.inner_text()
            if not _fuzzy_match(text, ["cfe", "cotisation fonciere", "avis"]):
                continue
            year_m = re.search(r"\b(20[1-3]\d)\b", text)
            siret_m = re.search(r"\b(\d{9}|\d{14})\b", text)
            notices.append({
                "label": text[:120].strip(),
                "annee": year_m.group(1) if year_m else "",
                "siret": siret_m.group(1) if siret_m else "",
                "_element": row,
            })
        return notices

    async def download_notice(self, notice: dict) -> str | None:
        el: ElementHandle = notice["_element"]
        dl_el = None

        for tag in ("a", "button"):
            for c in await el.query_selector_all(tag):
                txt = await c.inner_text()
                if _fuzzy_match(txt, LABEL_VARIANTS["telecharger"]):
                    dl_el = c
                    break
            if dl_el:
                break

        if not dl_el:
            dl_el = await find_element(self.page, "telecharger")

        if not dl_el:
            log.record_error("download_notice", "bouton_telechargement_introuvable", notice["label"])
            return None

        async with self.page.expect_download(timeout=30_000) as dl_info:
            await dl_el.click()
        download = await dl_info.value

        filename = download.suggested_filename or f"cfe_{notice['annee']}_{notice['siret']}.pdf"
        dest = f"{self.download_dir}/{filename}"
        await download.save_as(dest)

        log.record_download(filename, self.page.url, siret=notice["siret"], annee=notice["annee"])
        print(f"[CFE] Téléchargé : {dest}")
        return dest

    # ── Point d'entrée haut niveau ───────────────────────────────────────────

    async def run(self, identifiant: str, mot_de_passe: str) -> list[str]:
        """
        Exécute le skill complet :
        1. Ouvre le portail
        2. Se connecte avec les identifiants fournis
        3. Gère le 2FA si nécessaire
        4. Navigue vers les avis CFE
        5. Télécharge tous les avis disponibles
        Retourne la liste des fichiers téléchargés.
        """
        try:
            await self.start()
            state = await self.open_portal()
            print(f"[CFE] Page initiale : {state.title}")

            if state.is_error:
                log.record_error("run", "portail_indisponible", state.url)
                return []

            ok = await self.login(identifiant, mot_de_passe)
            if not ok:
                return []

            ok = await self.handle_2fa_if_needed()
            if not ok:
                return []

            state = await self.navigate_to_cfe()
            if not state.is_cfe_list:
                print(f"[CFE] Avertissement : page CFE non confirmée ({state.title})")
                log.record_error("run", "cfe_list_non_detectee", state.url)

            notices = await self.list_available_notices()
            print(f"[CFE] {len(notices)} avis détectés.")

            downloaded = []
            for notice in notices:
                path = await self.download_notice(notice)
                if path:
                    downloaded.append(path)

            return downloaded

        finally:
            await self.close()


# ── Utilitaire interne ───────────────────────────────────────────────────────

async def _get_selector_hint(el: ElementHandle) -> str:
    """Génère une hint de sélecteur à partir d'un élément (id, name, type)."""
    try:
        attrs = await el.evaluate(
            "e => ({id: e.id, name: e.name, type: e.type, tag: e.tagName.toLowerCase()})"
        )
        if attrs.get("id"):
            return f"#{attrs['id']}"
        if attrs.get("name"):
            return f"{attrs['tag']}[name='{attrs['name']}']"
        if attrs.get("type"):
            return f"input[type='{attrs['type']}']"
    except Exception:
        pass
    return "unknown"
