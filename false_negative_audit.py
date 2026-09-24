"""
false_negative_audit.py - VALIDATION-ONLY, READ-ONLY script for the false-negative review
requested after the section-membership fixes. Does NOT modify section_rank.py,
homepage_rank.py, the database, export_static.py, or any other source file - it only
imports and calls the existing, unmodified classify_* functions.

Builds candidate lists using BROAD "entity mention" regexes that are deliberately
INDEPENDENT of (and broader than) section_rank.py's own tier regexes, so the candidate
list isn't just re-deriving the same answer - then reports whether section_rank.py's
current classification actually admits each candidate, for manual substantive-vs-
incidental review.

Run:  py false_negative_audit.py
"""
import re
from datetime import datetime, timezone

import database
import section_rank as sr
from database import get_all_events, get_connection

POOL_N = 1500

DEFENCE_ENTITY = re.compile(
    r"\bdrdo\b|\barmy\b|\bnavy\b|\bair force\b|\biaf\b|coast guard|defence ministry|"
    r"defense ministry|\bmilitary\b|\bweapon|\bmissile|\bsoldier|\bjawan\b|\btroops?\b|"
    r"\bborder\b|\bloc\b|\blac\b|rajnath|\bdefence\b|\bdefense\b|security forces?|"
    r"submarine|fighter jet|warship|tejas|rafale|brahmos|agni missile|"
    r"सेना|वायुसेना|नौसेना|रक्षा|जवान|सैनिक", re.I)

AI_ENTITY = re.compile(
    r"\bai\b|artificial intelligence|generative ai|chatgpt|\bllm\b|machine learning|"
    r"large language model", re.I)

INDIA_FOREIGN_ENTITY = re.compile(
    r"india.{0,60}\b(us|u\.s\.|china|pakistan|russia|uk|u\.k\.|europe|japan|australia|"
    r"canada|bangladesh|nepal|sri lanka|middle east|gulf|israel|iran|germany|france)\b|"
    r"\b(us|u\.s\.|china|pakistan|russia|uk|u\.k\.|japan|germany|france)\b.{0,60}india|"
    r"h-1b|h1b|tariff|trade deal|\bvisa\b|immigration|\bimports?\b|\bexports?\b|energy", re.I)

INDIA_POLITICS_ENTITY = re.compile(
    r"\bbjp\b|congress|\btmc\b|\baap\b|shiv sena|parliament|lok sabha|rajya sabha|"
    r"\bmla\b|\bmp\b|chief minister|\bcm\b|\bgovernor\b|election commission|supreme court|"
    r"high court|\bcabinet\b|ordinance|\bbill\b|amendment|\bminister\b|\bgovernment\b|"
    r"संसद|चुनाव|विधायक|सांसद|सरकार|मंत्री", re.I)

ECONOMY_ENTITY = re.compile(
    r"\bgdp\b|inflation|unemployment|employment|industrial production|manufacturing|"
    r"\bexports?\b|\bimports?\b|trade deficit|fiscal deficit|infrastructure|investment|"
    r"consumption|\bsector\b|commodit|\bcrore\b|\binvest|expansion|budget|economic|"
    r"\bfactory\b|\bplant\b|\bfdi\b|production", re.I)


def _text(e):
    return " ".join([e.get("title") or "", e.get("title_hi") or ""])


def main():
    print(f"Resolved database: {database.DB_PATH}")
    events = get_all_events()
    pool = events[:POOL_N]
    print(f"Candidate pool: {len(pool)} of {len(events)} total publishable events\n")

    categories = [
        ("DEFENCE & SECURITY entity candidates", DEFENCE_ENTITY, sr.classify_defence_security),
        ("AI/TECHNOLOGY entity candidates", AI_ENTITY, sr.classify_technology),
        ("INDIA-FOREIGN relationship candidates", INDIA_FOREIGN_ENTITY, sr.classify_india_world),
        ("INDIA POLITICS entity candidates", INDIA_POLITICS_ENTITY, sr.classify_politics_policy),
        ("ECONOMY-ADJACENT entity candidates", ECONOMY_ENTITY, sr.classify_economy),
    ]

    for label, rx, classify_fn in categories:
        matches = [e for e in pool if rx.search(_text(e))]
        print(f"{'=' * 110}\n{label}  ({len(matches)} matches in pool)\n{'=' * 110}")
        for e in matches:
            cls = classify_fn(e)
            member = "YES" if cls is not None else "NO"
            tier = cls[1] if cls is not None else "-"
            print(f"  [{member:>3}] tier={tier:<28} #{e['id']:<6} region={e.get('region'):<5} "
                  f"topic={e.get('topic'):<14} | {e.get('title','')[:80]}")
        print()


if __name__ == "__main__":
    main()
