"""
entity_rules.py — Resolve the legal source entity for each raw transaction.

Resolution order (most deterministic first):
  1. Account last-four -> config.ACCOUNT_LAST4_TO_ENTITY
  2. Explicit 'Entity' header text -> config.ENTITY_TEXT_MAP
  3. Card / account-holder / filename hints -> config.ENTITY_TEXT_MAP
  4. Fallback: Unassigned / Allocation Required
Also returns a confidence contribution for the entity decision.
"""
from . import config


def _match_text(text):
    t = (text or "").strip().lower()
    if not t:
        return None
    for key, entity in config.ENTITY_TEXT_MAP.items():
        if key in t:
            return entity
    return None


def resolve_entity(rec):
    """Return (source_entity, entity_confidence, entity_basis)."""
    last4 = (rec.get("meta_account_last4") or "").lstrip("0") or rec.get("meta_account_last4")
    raw_last4 = rec.get("meta_account_last4") or ""
    # 1. account last-four (most deterministic)
    for candidate in (raw_last4, raw_last4.lstrip("0")):
        if candidate and candidate in config.ACCOUNT_LAST4_TO_ENTITY:
            return config.ACCOUNT_LAST4_TO_ENTITY[candidate], 98, f"account …{candidate}"
    # 2. explicit Entity header text
    ent = _match_text(rec.get("meta_entity_text"))
    if ent:
        return ent, 95, f"entity header '{rec.get('meta_entity_text')}'"
    # 3. card name / account holder / filename hints
    for field in ("meta_card_name", "meta_account_holder", "source_file"):
        ent = _match_text(rec.get(field))
        if ent:
            return ent, 82, f"{field} hint"
    # 4. fallback
    return config.ENTITY_UNASSIGNED, 40, "no entity indicator"


def proposed_reporting_entity(source_entity, treatment):
    """
    The reporting entity may differ from the legal source entity when, e.g., a
    personal card carries a business charge. For now the proposed reporting
    entity equals the source entity unless a business-paid-personally / personal-
    paid-by-business condition reassigns it (handled in accounting_logic).
    """
    return source_entity
