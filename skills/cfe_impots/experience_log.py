"""
Journal d'expérience persistant pour le skill CFE impots.gouv.fr.
Stocke les variantes d'interface rencontrées, les sélecteurs qui ont fonctionné
et les chemins de navigation validés.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


LOG_PATH = Path(__file__).parent / "experience.json"

_EMPTY = {
    "version": 1,
    "updated_at": None,
    "navigation_paths": [],       # chemins validés vers la CFE
    "selector_variants": {},      # libellé → liste de sélecteurs CSS/texte essayés
    "interface_snapshots": [],    # captures d'état marquantes (URL + titre + date)
    "download_history": [],       # fichiers téléchargés avec succès
    "errors": [],                 # erreurs rencontrées et comment elles ont été contournées
}


def _load() -> dict:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_EMPTY)


def _save(data: dict) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    LOG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── API publique ────────────────────────────────────────────────────────────

def record_navigation_path(steps: list[str], label: str = "") -> None:
    """Enregistre un chemin de navigation qui a abouti aux avis CFE."""
    data = _load()
    entry = {"steps": steps, "label": label, "recorded_at": datetime.now(timezone.utc).isoformat()}
    # déduplique sur la séquence de steps
    if not any(e["steps"] == steps for e in data["navigation_paths"]):
        data["navigation_paths"].append(entry)
        _save(data)


def record_selector(concept: str, selector: str, worked: bool) -> None:
    """Mémorise qu'un sélecteur a fonctionné (ou non) pour un concept donné."""
    data = _load()
    variants = data["selector_variants"].setdefault(concept, [])
    for v in variants:
        if v["selector"] == selector:
            v["worked"] = worked
            v["last_seen"] = datetime.now(timezone.utc).isoformat()
            _save(data)
            return
    variants.append({
        "selector": selector,
        "worked": worked,
        "last_seen": datetime.now(timezone.utc).isoformat(),
    })
    _save(data)


def best_selectors(concept: str) -> list[str]:
    """Retourne les sélecteurs qui ont déjà fonctionné pour ce concept, en premier."""
    data = _load()
    variants = data["selector_variants"].get(concept, [])
    worked = [v["selector"] for v in variants if v.get("worked")]
    others = [v["selector"] for v in variants if not v.get("worked")]
    return worked + others


def record_snapshot(url: str, title: str, note: str = "") -> None:
    data = _load()
    data["interface_snapshots"].append({
        "url": url,
        "title": title,
        "note": note,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    # garde les 100 derniers
    data["interface_snapshots"] = data["interface_snapshots"][-100:]
    _save(data)


def record_download(filename: str, url: str, siret: str = "", annee: str = "") -> None:
    data = _load()
    data["download_history"].append({
        "filename": filename,
        "source_url": url,
        "siret": siret,
        "annee": annee,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    _save(data)


def record_error(context: str, error: str, workaround: str = "") -> None:
    data = _load()
    data["errors"].append({
        "context": context,
        "error": error,
        "workaround": workaround,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    data["errors"] = data["errors"][-200:]
    _save(data)


def summary() -> dict:
    """Résumé lisible du journal d'expérience."""
    data = _load()
    return {
        "derniere_maj": data.get("updated_at"),
        "chemins_valides": len(data["navigation_paths"]),
        "concepts_connus": list(data["selector_variants"].keys()),
        "telechargements": len(data["download_history"]),
        "erreurs_enregistrees": len(data["errors"]),
    }
