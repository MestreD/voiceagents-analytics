"""
Generate the synthetic raw data for the VoiceAgents analytics project.

Writes three CSV files to data/raw/ that stand in for what would arrive from
the application database and the billing system:

    gestorias.csv   one row per customer (a Spanish tax/accounting firm)
    pricing.csv     one row per plan per validity window (a slowly-changing source)
    calls.csv       one row per call handled by the voice agent

Deterministic: the seed is fixed, so everyone who clones this repo and runs
the script gets byte-identical data. That is what makes the dbt tests in CI
meaningful.

Usage:
    python scripts/generate_data.py
"""

import csv
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 20261010
random.seed(SEED)

OUT = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

PERIOD_START = date(2025, 1, 1)
PERIOD_END = date(2026, 6, 30)
N_GESTORIAS = 50

# ---------------------------------------------------------------- gestorias

CITIES = [
    ("Madrid", "Madrid"), ("Barcelona", "Catalunya"), ("Valencia", "C. Valenciana"),
    ("Sevilla", "Andalucia"), ("Zaragoza", "Aragon"), ("Malaga", "Andalucia"),
    ("Bilbao", "Pais Vasco"), ("Murcia", "Murcia"), ("Palma", "Baleares"),
    ("Las Palmas", "Canarias"), ("Valladolid", "Castilla y Leon"),
    ("Vigo", "Galicia"), ("Alicante", "C. Valenciana"), ("Cordoba", "Andalucia"),
    ("Terrassa", "Catalunya"), ("Pamplona", "Navarra"),
]

FIRM_PREFIX = [
    "Asesoria", "Gestoria", "Despacho", "Consultoria", "Grupo",
    "Asesores", "Gabinete",
]
FIRM_NAME = [
    "Iberica", "Mediterraneo", "Delta", "Central", "Atlantic", "Norte",
    "Progreso", "Castellana", "Prisma", "Lumen", "Vertex", "Aurora",
    "Camino", "Solera", "Meridiano", "Nexo", "Arco", "Faro", "Cima",
    "Ribera", "Alameda", "Cruz", "Vega", "Puerto", "Sierra",
]
FIRM_SUFFIX = ["SL", "SLU", "SC", "y Asociados", "Consulting SL"]

PLANS = ["basico", "pro", "premium"]
PLAN_WEIGHTS = [0.45, 0.40, 0.15]

# Seats drive call volume. A bigger firm fields more inbound calls.
PLAN_SEATS = {"basico": (1, 3), "pro": (3, 9), "premium": (8, 25)}


def make_firm_names(n):
    """Draw n distinct firm names."""
    names = set()
    while len(names) < n:
        name = "{} {} {}".format(
            random.choice(FIRM_PREFIX),
            random.choice(FIRM_NAME),
            random.choice(FIRM_SUFFIX),
        )
        names.add(name)
    return sorted(names)


def build_gestorias():
    names = make_firm_names(N_GESTORIAS)
    rows = []
    # Signups cluster in the first half of the period, as a growing product would.
    signup_span = (date(2026, 3, 31) - PERIOD_START).days

    for i, name in enumerate(names, start=1):
        city, region = random.choice(CITIES)
        plan = random.choices(PLANS, weights=PLAN_WEIGHTS, k=1)[0]
        low, high = PLAN_SEATS[plan]

        # Skew signups early: squaring a uniform draw pulls the mass left, so
        # most firms are already live at the start and a tail joins later.
        signed_up = PERIOD_START + timedelta(
            days=int(signup_span * random.random() ** 2)
        )

        # About 16% churn, never sooner than 45 days after signing up.
        churned = ""
        if random.random() < 0.16:
            earliest = signed_up + timedelta(days=45)
            if earliest < PERIOD_END:
                churned = (
                    earliest
                    + timedelta(days=random.randint(0, (PERIOD_END - earliest).days))
                ).isoformat()

        rows.append({
            "gestoria_id": i,
            "gestoria_name": name,
            "city": city,
            "region": region,
            "plan_code": plan,
            "seats": random.randint(low, high),
            "signed_up_on": signed_up.isoformat(),
            "churned_on": churned,
        })
    return rows


# ------------------------------------------------------------------ pricing
# Each plan is repriced once or twice during the period. Every row is valid
# from valid_from up to but NOT including valid_to; the open row has an empty
# valid_to. Billing a given month therefore means picking the row that was in
# force on that month's last day, which is the as-of join this project exists
# to demonstrate.

PRICING_PLAN = {
    "basico":  {"base": 49.00,  "minutes": 300,  "overage": 0.11},
    "pro":     {"base": 149.00, "minutes": 1200, "overage": 0.09},
    "premium": {"base": 399.00, "minutes": 4000, "overage": 0.07},
}

REPRICE_DATES = {
    "basico":  [date(2025, 9, 1)],
    "pro":     [date(2025, 7, 1), date(2026, 2, 1)],
    "premium": [date(2026, 1, 1)],
}


def build_pricing():
    rows = []
    for plan in PLANS:
        spec = PRICING_PLAN[plan]
        boundaries = [PERIOD_START] + REPRICE_DATES[plan]
        base, minutes, overage = spec["base"], spec["minutes"], spec["overage"]

        for idx, start in enumerate(boundaries):
            if idx > 0:
                # Price rises, included minutes rise a little, overage eases.
                base = round(base * random.uniform(1.06, 1.14), 2)
                minutes = int(minutes * random.choice([1.0, 1.0, 1.15]))
                overage = round(overage * random.uniform(0.92, 1.0), 3)

            end = boundaries[idx + 1] if idx + 1 < len(boundaries) else None
            rows.append({
                "plan_code": plan,
                "monthly_fee_eur": f"{base:.2f}",
                "included_minutes": minutes,
                "overage_eur_per_minute": f"{overage:.3f}",
                "valid_from": start.isoformat(),
                "valid_to": end.isoformat() if end else "",
            })
    return rows


# -------------------------------------------------------------------- calls

INTENTS = [
    ("cita_previa",        0.26, 0.93),
    ("estado_tramite",     0.21, 0.88),
    ("documentacion",      0.16, 0.74),
    ("factura_pago",       0.12, 0.69),
    ("consulta_fiscal",    0.11, 0.31),
    ("alta_cliente",       0.07, 0.58),
    ("reclamacion",        0.04, 0.22),
    ("otros",              0.03, 0.40),
]
INTENT_NAMES = [i[0] for i in INTENTS]
INTENT_W = [i[1] for i in INTENTS]
RESOLVE_RATE = {i[0]: i[2] for i in INTENTS}

LANGS = ["es", "ca", "en"]
LANG_W = [0.82, 0.14, 0.04]


def active_on(g, day):
    if date.fromisoformat(g["signed_up_on"]) > day:
        return False
    if g["churned_on"] and date.fromisoformat(g["churned_on"]) <= day:
        return False
    return True


def daily_call_count(g, day):
    """Expected calls for one firm on one day."""
    if day.weekday() >= 5:              # weekends are near-silent
        return random.choices([0, 1], weights=[0.88, 0.12], k=1)[0]

    base = g["seats"] * 1.45

    # Spanish filing calendar: quarterly VAT months and the June income-tax
    # deadline bring a surge.
    if day.month in (1, 4, 7, 10):
        base *= 1.45
    if day.month == 6:
        base *= 1.30
    if day.month == 8:                  # August is dead
        base *= 0.45

    # The agent takes on more traffic as the firm settles in.
    weeks_live = (day - date.fromisoformat(g["signed_up_on"])).days / 7.0
    base *= min(1.0, 0.35 + 0.05 * weeks_live)

    return max(0, int(random.gauss(base, base * 0.42)))


def call_duration(intent, resolved):
    """Seconds. Unresolved calls run long before they give up."""
    mu = {
        "cita_previa": 62, "estado_tramite": 78, "documentacion": 112,
        "factura_pago": 95, "consulta_fiscal": 150, "alta_cliente": 185,
        "reclamacion": 165, "otros": 88,
    }[intent]
    if not resolved:
        mu *= 1.5
    secs = int(random.lognormvariate(math.log(mu), 0.45))
    return max(8, min(secs, 1800))


def build_calls(gestorias):
    rows = []
    call_id = 0
    day = PERIOD_START

    while day <= PERIOD_END:
        for g in gestorias:
            if not active_on(g, day):
                continue
            for _ in range(daily_call_count(g, day)):
                call_id += 1
                intent = random.choices(INTENT_NAMES, weights=INTENT_W, k=1)[0]
                resolved = random.random() < RESOLVE_RATE[intent]
                duration = call_duration(intent, resolved)

                # Business hours, two humps: a morning peak and an afternoon one.
                hour = random.choices(
                    [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
                    weights=[3, 9, 13, 14, 11, 7, 4, 6, 10, 11, 8, 4],
                    k=1,
                )[0]
                started = datetime(
                    day.year, day.month, day.day,
                    hour, random.randint(0, 59), random.randint(0, 59),
                )

                # An unresolved call is usually handed to a person.
                transferred = (not resolved) and random.random() < 0.78

                rows.append({
                    "call_id": call_id,
                    "gestoria_id": g["gestoria_id"],
                    "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
                    "duration_seconds": duration,
                    "detected_intent": intent,
                    "language": random.choices(LANGS, weights=LANG_W, k=1)[0],
                    "was_resolved": int(resolved),
                    "transferred_to_human": int(transferred),
                    "caller_hash": f"c{random.randint(10**9, 10**10 - 1)}",
                })
        day += timedelta(days=1)
    return rows


# ------------------------------------------------------------------- output

def write_csv(filename, rows):
    path = OUT / filename
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    size_kb = path.stat().st_size / 1024
    print(f"  {filename:<16} {len(rows):>7,} rows  {size_kb:>8,.0f} KB")


def main():
    print(f"Generating synthetic data (seed {SEED})")
    print(f"Period {PERIOD_START} to {PERIOD_END}\n")

    gestorias = build_gestorias()
    pricing = build_pricing()
    calls = build_calls(gestorias)

    write_csv("gestorias.csv", gestorias)
    write_csv("pricing.csv", pricing)
    write_csv("calls.csv", calls)

    churned = sum(1 for g in gestorias if g["churned_on"])
    print(f"\n  {churned} of {len(gestorias)} gestorias churned in the period")
    print(f"  written to {OUT}")


if __name__ == "__main__":
    main()
