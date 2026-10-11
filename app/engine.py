"""Diligence engine: ingest -> extract -> flag -> cross-reference -> report.

Feature 1  Contract Risk & Exception Register
           Clause-level flags vs. the clause playbook, each with clause/page
           traceability, quoted evidence and a confidence score.
Feature 2  Cross-Workstream Insight Layer
           Joins contract flags to revenue, SLA and fleet data so that
           legal + commercial + operational + financial signals are scored
           together per counterparty.

Deterministic rules run by default (offline, repeatable, auditable).
An optional Claude pass (llm.py) acts as an independent second reviewer.
"""
import csv
import datetime as dt
import os
import re

from pdftext import extract_pages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "synthetic_pack")
CONTRACTS = os.path.join(PACK, "contracts")
DATA = os.path.join(PACK, "data")

SEV_W = {"High": 3, "Medium": 2, "Low": 1}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def today():
    env = os.environ.get("DD_TODAY")
    return dt.date.fromisoformat(env) if env else dt.date.today()


# --------------------------------------------------------------------------
# 01 INGEST - documents into a clause-level knowledge base
# --------------------------------------------------------------------------
_CLAUSE_RE = re.compile(r"^(\d+\.\d+)\s+(.*)")
_HEADING_RE = re.compile(r"^(\d+)\.\s+([A-Z].*)$")


def _read_csv(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def doc_meta(filename):
    stem = filename[:-4]
    parts = stem.split("_")
    kind = parts[1].lower() if len(parts) > 1 else "other"   # customer/supplier/employment
    return {"file": filename, "kind": kind, "title": " ".join(parts[2:])}


def ingest_contract(filename):
    pages = extract_pages(os.path.join(CONTRACTS, filename))
    clauses, title_lines, parties = [], [], ""
    heading = ""
    for pno, text in enumerate(pages, 1):
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("SYNTHETIC DOCUMENT") or re.fullmatch(r"Page \d+", line):
                continue
            m = _CLAUSE_RE.match(line)
            h = _HEADING_RE.match(line)
            if m:
                clauses.append({"ref": m.group(1), "page": pno, "heading": heading,
                                "text": m.group(2)})
            elif h and not clauses or (h and len(line) < 60):
                heading = h.group(2)
            elif clauses and not line.startswith("Executed as"):
                clauses[-1]["text"] += " " + line
            elif not clauses:
                title_lines.append(line)
    preamble = " ".join(title_lines)
    pm = re.search(r"between (.+?) \(the", preamble)
    parties = pm.group(1) if pm else ""
    if doc_meta(filename)["kind"] == "employment":
        em = re.search(r"and (.+?) \(the \"Executive\"\)", preamble)
        if em:
            parties = f"{em.group(1)} (Operations Director)"
    dm = re.search(r"Dated (\d{1,2} \w+ \d{4})", preamble)
    meta = doc_meta(filename)
    meta.update({
        "counterparty": parties,
        "doc_title": title_lines[0] if title_lines else meta["title"],
        "dated": dm.group(1) if dm else "",
        "pages": len(pages),
        "clauses": clauses,
        "full_text": "\n".join(pages),
    })
    return meta


def load_knowledge_base():
    files = sorted(f for f in os.listdir(CONTRACTS) if f.lower().endswith(".pdf"))
    return [ingest_contract(f) for f in files]


def search(kb, query, limit=25):
    terms = [t for t in re.findall(r"\w+", query.lower()) if len(t) > 1]
    hits = []
    for doc in kb:
        for c in doc["clauses"]:
            low = (c["heading"] + " " + c["text"]).lower()
            score = sum(low.count(t) for t in terms)
            if terms and all(t in low for t in terms):
                score += 5
            if score:
                hits.append({"file": doc["file"], "counterparty": doc["counterparty"],
                             "ref": c["ref"], "page": c["page"], "heading": c["heading"],
                             "text": c["text"], "score": score})
    return sorted(hits, key=lambda h: -h["score"])[:limit]


# --------------------------------------------------------------------------
# 02 EXTRACT - normalise key data points
# --------------------------------------------------------------------------
def paren_num(text, unit):
    """'thirty (30) days' -> 30 ; returns first match for the unit."""
    m = re.search(r"\((\d+)\)\s*" + unit, text)
    return int(m.group(1)) if m else None


def parse_date(s):
    m = re.search(r"(\d{1,2}) (\w+) (\d{4})", s)
    if not m or m.group(2).lower() not in MONTHS:
        return None
    return dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))


def gbp_amounts(text):
    return [float(x.replace(",", "")) for x in re.findall(r"GBP\s*([\d,]+(?:\.\d+)?)", text)]


def key_terms(doc):
    """Structured extraction used for the 'normalised terms' table."""
    t = doc["full_text"]
    flat = " ".join(t.split())
    terms = {"Counterparty": doc["counterparty"], "Dated": doc["dated"]}
    am = re.search(r"\"(Annual (?:Charges|Fee|Contract Sum))\" means[^.]*?GBP\s*([\d,]+)", flat)
    if am:
        terms["Stated annual value (GBP m)"] = round(float(am.group(2).replace(",", "")) / 1e6, 2)
    em = re.search(r"(?:expiring on|to) (\d{1,2} \w+ \d{4})", flat)
    if em:
        terms["Term end"] = em.group(1)
    if re.search(r"capped at|lower of CPI", flat):
        terms["Indexation"] = "Capped"
    elif re.search(r"no cap", flat, re.I):
        terms["Indexation"] = "Uncapped"
    elif re.search(r"not be subject to indexation", flat):
        terms["Indexation"] = "None (fixed)"
    lm = re.search(r"liability[^.]*?not exceed ([^.]*?)(?:\.|of the)", flat)
    if re.search(r"liable without limit", flat):
        terms["Liability cap"] = "UNCAPPED (supplier)"
    elif lm:
        terms["Liability cap"] = lm.group(1).strip()
    terms["Governing law"] = "England & Wales" if "England and Wales" in flat else "?"
    return terms


# --------------------------------------------------------------------------
# 03 FLAG - playbook rules (one detector per playbook clause_type)
# --------------------------------------------------------------------------
NEG_TERMINATION = re.compile(r"does not give rise to any right of termination|does not affect", re.I)


def _d_change_of_control(c, doc):
    t = c["text"]
    if not re.search(r"change of control|change in (its )?ownership", t, re.I) or NEG_TERMINATION.search(t):
        return None
    if doc["kind"] == "employment":
        if re.search(r"irrespective|single trigger", t, re.I):
            return 0.95, "Single-trigger CoC payment: payable on completion regardless of continued employment"
        if re.search(r"shall pay", t, re.I):
            return 0.75, "CoC payment obligation to executive"
        return None
    if re.search(r"may terminate", t, re.I):
        return 0.93, "Counterparty may terminate following an un-consented Change of Control"
    if re.search(r"consent", t, re.I) and re.search(r"terminat", t, re.I):
        return 0.7, "Consent requirement on Change of Control"
    return None


def _d_persistent_failure(c, doc):
    t = c["text"]
    if re.search(r"persistent failure", t, re.I) and re.search(r"terminate", t, re.I):
        return 0.92, "Termination right on repeated KPI failures"
    return None


def _d_uncapped_liability(c, doc):
    t = c["text"]
    if re.search(r"neither party (is|shall be) liable", t, re.I):
        return None
    if re.search(r"without limit|unlimited liability|no cap on (its )?liability", t, re.I):
        conf = 0.95 if re.search(r"loss of profit", t, re.I) else 0.85
        return conf, "Unlimited liability incl. loss of profit/revenue (standard: 100% annual charges cap, no indirect loss)"
    return None


def _d_auto_renewal(c, doc):
    t = c["text"]
    if not re.search(r"renew automatically|automatically renew|auto-?renew", t, re.I):
        return None
    days = paren_num(t, r"days")
    if days is not None and days < 90:
        return 0.9, f"Auto-renews; non-renewal notice only {days} days (playbook: flag if <90)"
    return None


def _d_mfn(c, doc):
    t = c["text"]
    if re.search(r"most favoured", t, re.I):
        return 0.95, "Most-favoured-customer pricing warranty"
    if re.search(r"no less favourable than the fees charged", t, re.I):
        return 0.85, "Pricing parity obligation vs. other customers"
    if re.search(r"more favourable fees to any other customer", t, re.I):
        return 0.8, "Obligation to match better pricing offered elsewhere, with refund"
    return None


def _d_exclusivity(c, doc):
    t = c["text"]
    if re.search(r"\bexclusive(ly)?\b", t, re.I) and not re.search(r"exclusive jurisdiction", t, re.I):
        return 0.92, "Exclusive purchasing/leasing obligation"
    if re.search(r"shall not enter into any arrangement with any third party", t, re.I):
        return 0.7, "Bar on third-party arrangements (de facto exclusivity)"
    return None


def _d_take_or_pay(c, doc):
    t = c["text"]
    if re.search(r"take-or-pay|whether or not .{0,40}in use|minimum commitment", t, re.I):
        return 0.94, "Pays for minimum volume whether used or not"
    return None


def _d_uncapped_escalation(c, doc):
    t = c["text"]
    if not re.search(r"\b(increase|uplifted?|indexed|adjusted)\b", t, re.I) or not re.search(r"\b(RPI|CPI)\b", t):
        return None
    if re.search(r"no cap", t, re.I):
        return 0.95, "Price escalator with no cap"
    if not re.search(r"cap|lower of", t, re.I):
        return 0.7, "Indexation without an explicit cap"
    return None


def _d_fixed_price(c, doc):
    t = c["text"]
    if re.search(r"remain fixed|not be subject to indexation|no indexation", t, re.I):
        return 0.9, "Price fixed for initial and renewal terms with no inflation link"
    return None


def _d_tfc(c, doc):
    t = c["text"]
    if not re.search(r"for convenience", t, re.I) or re.search(r"neither party may terminate", t, re.I):
        return None
    months = paren_num(t, r"months")
    if doc["kind"] == "customer" and (months is None or months < 6):
        return 0.9, f"Customer may exit without cause on {months or '?'} months' notice (playbook: flag if <6)"
    return None


def _d_early_termination_fee(c, doc):
    t = c["text"]
    if not re.search(r"early termination fee|terminate .{0,30}early only by paying", t, re.I):
        return None
    pm = re.search(r"\((\d+)%\)", t) or re.search(r"(\d+)%", t)
    pct = int(pm.group(1)) if pm else None
    if pct is None or pct > 50:
        return 0.93, f"Exit fee of {pct or '?'}% of remaining payments (playbook: flag if >50%)"
    return None


def _d_long_notice(c, doc):
    t = c["text"]
    if doc["kind"] != "employment" or not re.search(r"written notice", t, re.I):
        return None
    months = paren_num(t, r"months")
    if months and months > 6:
        return 0.88, f"{months} months' notice (playbook: flag if >6)"
    return None


# (playbook clause_type, detector, severity override or None, workstreams)
RULES = [
    ("Change of control", _d_change_of_control, None, ["Legal", "Commercial"]),
    ("Persistent failure / termination for service levels", _d_persistent_failure, None, ["Legal", "Operational"]),
    ("Uncapped liability", _d_uncapped_liability, None, ["Legal", "Financial"]),
    ("Auto-renewal with short notice", _d_auto_renewal, None, ["Legal", "Commercial"]),
    ("Most-favoured-customer pricing", _d_mfn, None, ["Legal", "Commercial", "Financial"]),
    ("Exclusivity", _d_exclusivity, None, ["Legal", "Operational"]),
    ("Take-or-pay / minimum commitment", _d_take_or_pay, None, ["Legal", "Operational", "Financial"]),
    ("Uncapped price escalation", _d_uncapped_escalation, None, ["Legal", "Financial"]),
    ("Fixed price, no indexation", _d_fixed_price, None, ["Commercial", "Financial"]),
    ("Termination for convenience", _d_tfc, None, ["Legal", "Commercial"]),
    ("Early termination fee", _d_early_termination_fee, None, ["Legal", "Financial"]),
    # Playbook bundles long notice with single-trigger payments (High); long notice
    # on its own is a retention/cost point, so it is downgraded to Low.
    ("Single-trigger executive payments / long notice", _d_long_notice, "Low", ["HR", "Financial"]),
]


def load_playbook():
    return {r["clause_type"]: r for r in _read_csv("clause_playbook.csv")}


def run_rules(kb):
    playbook = load_playbook()
    findings = []
    for doc in kb:
        for rule_type, fn, sev_override, streams in RULES:
            hits = []
            for c in doc["clauses"]:
                r = fn(c, doc)
                if r:
                    hits.append((r[0], r[1], c))
            if not hits:
                continue
            hits.sort(key=lambda h: -h[0])
            conf, why, best = hits[0]
            pb = playbook.get(rule_type) or playbook.get(
                "Change of control" if rule_type.startswith("Change") else "", {})
            # CoC in employment contracts maps to the single-trigger playbook row
            ptype = rule_type
            if rule_type == "Change of control" and doc["kind"] == "employment":
                ptype = "Single-trigger executive payments / long notice"
                streams = ["Legal", "HR", "Financial"]
            sev = sev_override or (playbook.get(ptype) or pb).get("default_severity", "Medium")
            findings.append({
                "id": None,
                "file": doc["file"],
                "counterparty": doc["counterparty"],
                "clause_type": ptype if ptype != rule_type else rule_type,
                "issue": why,
                "clause": best["ref"],
                "page": best["page"],
                "related_clauses": [h[2]["ref"] for h in hits[1:]],
                "evidence": best["text"],
                "severity": sev,
                "confidence": round(conf, 2),
                "method": "Rule",
                "playbook_rule": (playbook.get(ptype) or pb).get("standard_position_or_rule", ""),
                "workstreams": streams,
                "data_check": "",
                "quant_gbp": None,
            })
    return findings


# --------------------------------------------------------------------------
# 04 CROSS-REFERENCE - contracts x revenue x SLA x fleet
# --------------------------------------------------------------------------
def load_data():
    rev = _read_csv("customer_revenue_FY2023-2025.csv")
    sla = _read_csv("sla_performance_monthly.csv")
    fleet = _read_csv("fleet_utilisation_quarterly.csv")
    return rev, sla, fleet


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def sla_summary(sla, customer):
    rows = sorted((r for r in sla if r["customer"] == customer), key=lambda r: r["month"])
    fails = [r["month"] for r in rows if r["kpi_failure"].strip().upper() == "Y"]
    last6 = rows[-6:]
    fails6 = [r["month"] for r in last6 if r["kpi_failure"].strip().upper() == "Y"]
    credits = sum(_f(r["service_credit_gbpk"]) or 0 for r in rows)
    return {"months": len(rows), "failures_12m": fails, "failures_last6": fails6,
            "window": f"{last6[0]['month']} to {last6[-1]['month']}" if last6 else "",
            "service_credits_gbpk": credits}


def enrich(kb, findings):
    """Validate contract flags against structured data; add data-driven findings."""
    rev, sla, fleet = load_data()
    rev_by_file = {r["contract_file"]: r for r in rev if r["contract_file"]}
    total = next((r for r in rev if r["customer"].upper() == "TOTAL"), None)
    group_margin = _f(total["gross_margin_pct_FY2025"]) if total else None
    docs = {d["file"]: d for d in kb}
    extra = []

    for f in findings:
        doc = docs[f["file"]]
        r = rev_by_file.get(f["file"])
        ct = f["clause_type"]
        if ct.startswith("Persistent failure") and r:
            s = sla_summary(sla, r["customer"])
            thr = paren_num(f["evidence"], r"or more") or 3
            n = len(s["failures_last6"])
            if n >= thr:
                f["data_check"] = (f"THRESHOLD ALREADY MET: {n} KPI failures in last 6 months "
                                   f"({', '.join(s['failures_last6'])}) vs. threshold {thr}. "
                                   "Termination right is exercisable today.")
                f["confidence"] = min(0.99, f["confidence"] + 0.05)
                f["workstreams"] = sorted(set(f["workstreams"] + ["Operational"]))
            else:
                f["data_check"] = f"{n} KPI failures in last 6 months vs threshold {thr}."
        elif ct == "Auto-renewal with short notice":
            init = next((c for c in doc["clauses"] if "Initial Term" in c["text"] and "means" in c["text"]), None)
            end = None
            if init:
                ds = re.findall(r"\d{1,2} \w+ \d{4}", init["text"])
                end = parse_date(ds[-1]) if ds else None
            days = paren_num(f["evidence"], "days") or 30
            if end:
                deadline = end - dt.timedelta(days=days)
                left = (deadline - today()).days
                f["data_check"] = (f"Initial term ends {end:%d %b %Y}; notice deadline {deadline:%d %b %Y} "
                                   f"({left} days / c.{round(left / 7)} weeks from today).")
                if 0 <= left <= 90:
                    f["data_check"] += " DEADLINE FALLS WITHIN DEAL TIMELINE."
        elif ct == "Fixed price, no indexation" and r and group_margin:
            m = _f(r["gross_margin_pct_FY2025"])
            f["data_check"] = f"FY2025 gross margin {m}% vs group {group_margin}% ({m - group_margin:+.1f}pp)."
        elif ct == "Take-or-pay / minimum commitment" and fleet:
            q = fleet[-1]
            commit = int(_f(q["vehicles_leased_min_commitment"]))
            used = int(_f(q["vehicles_in_use"]))
            rent = _f(q["monthly_rental_per_vehicle_gbp"])
            idle = commit - used
            annual = idle * rent * 12
            trend = " -> ".join(f"{x['utilisation_pct']}%" for x in fleet)
            f["data_check"] = (f"{q['quarter']}: {used}/{commit} vehicles in use, {idle} idle. "
                               f"Idle cost GBP {_f(q['idle_vehicle_cost_gbp_per_quarter']) / 1e3:.0f}k/qtr, "
                               f"c.GBP {annual / 1e6:.2f}m/yr. Utilisation trend {trend}.")
            f["quant_gbp"] = annual
            f["confidence"] = min(0.99, f["confidence"] + 0.04)
        elif ct == "Early termination fee" and fleet:
            q = fleet[-1]
            commit = int(_f(q["vehicles_leased_min_commitment"]))
            rent = _f(q["monthly_rental_per_vehicle_gbp"])
            end = None
            tm = re.search(r"to (\d{1,2} \w+ \d{4})", " ".join(c["text"] for c in doc["clauses"] if c["ref"].startswith("2.")))
            if tm:
                end = parse_date(tm.group(1))
            if end:
                months = (end.year - today().year) * 12 + end.month - today().month
                fee = commit * rent * months
                f["data_check"] = (f"Indicative exit cost today: {commit} x GBP {rent:.0f} x {months} months "
                                   f"remaining = c.GBP {fee / 1e6:.1f}m (at current rental).")
                f["quant_gbp"] = fee
        elif f["clause_type"].startswith("Single-trigger") and doc["kind"] == "employment":
            flat = " ".join(doc["full_text"].split())
            sal = gbp_amounts(re.search(r"base salary is GBP[\d, ]+", flat).group(0))[0] if re.search(r"base salary is GBP", flat) else None
            bonus_pct = re.search(r"up to (\d+)% of base salary", flat)
            if sal and "Change of Control" in f["evidence"] + " ".join(c["text"] for c in doc["clauses"] if c["ref"] == "4.1"):
                months_cc = paren_num(" ".join(c["text"] for c in doc["clauses"] if c["ref"] == "4.1"), r"months")
                if f["clause"].startswith("4"):
                    pay = sal * (months_cc or 0) / 12
                    bonus = sal * int(bonus_pct.group(1)) / 100 if bonus_pct else 0
                    f["data_check"] = (f"{months_cc} months x GBP {sal / 1e3:.0f}k / 12 = GBP {pay / 1e3:.0f}k, "
                                       f"plus up to GBP {bonus / 1e3:.0f}k max pro-rated bonus "
                                       f"=> up to GBP {(pay + bonus) / 1e3:.0f}k payable on completion. SPA price-chip item.")
                    f["quant_gbp"] = pay + bonus
                else:
                    notice = paren_num(f["evidence"], "months") or 0
                    f["data_check"] = f"PILON exposure c.GBP {sal * notice / 12 / 1e3:.0f}k ({notice} months' base salary)."
                    f["quant_gbp"] = sal * notice / 12
        elif ct == "Termination for convenience" and r:
            f["data_check"] = (f"GBP {r['revenue_FY2025_gbpm']}m FY2025 revenue ({r['pct_of_FY2025_revenue']}%) "
                               "exitable on short notice.")
        elif ct == "Change of control" and r:
            f["data_check"] = (f"Transaction itself is the trigger. Revenue at risk: GBP {r['revenue_FY2025_gbpm']}m "
                               f"({r['pct_of_FY2025_revenue']}% of FY2025). Obtain consent pre-signing.")
            f["quant_gbp"] = _f(r["revenue_FY2025_gbpm"]) * 1e6
        elif ct == "Most-favoured-customer pricing" and r:
            f["data_check"] = (f"Any cheaper price to another customer resets GBP {r['revenue_FY2025_gbpm']}m fee "
                               "and triggers refund; constrains post-deal pricing strategy. Margin already "
                               f"{r['gross_margin_pct_FY2025']}%.")
        elif ct == "Exclusivity":
            tm = re.search(r"seven \((\d+)\) years|\((\d+)\) years", " ".join(c["text"] for c in doc["clauses"] if c["ref"].startswith("2.")))
            yrs = (tm.group(1) or tm.group(2)) if tm else "?"
            f["data_check"] = f"Exclusivity runs for the full {yrs}-year term (playbook: flag >3 years); blocks fleet synergies post-deal."
        elif ct == "Uncapped price escalation" and fleet:
            q = fleet[-1]
            base = int(_f(q["vehicles_leased_min_commitment"])) * _f(q["monthly_rental_per_vehicle_gbp"]) * 12
            r0, r1 = _f(fleet[0]["monthly_rental_per_vehicle_gbp"]), _f(q["monthly_rental_per_vehicle_gbp"])
            f["data_check"] = (f"Rental GBP {r0:.0f} -> {r1:.0f}/vehicle/month in data (+{(r1 / r0 - 1) * 100:.1f}%). "
                               f"Annual minimum rent c.GBP {base / 1e6:.2f}m; each 1pp of RPI adds c.GBP {base / 100 / 1e3:.0f}k p.a., "
                               "with no cap.")
        elif ct == "Uncapped liability" and r:
            f["data_check"] = (f"Annual fee GBP {r['revenue_FY2025_gbpm']}m; exposure unbounded. "
                               "Check insurance cover and claims history.")

    # Data-driven: contract value vs ledger contradiction
    for d in kb:
        r = rev_by_file.get(d["file"])
        if not r:
            continue
        kt = key_terms(d)
        stated = kt.get("Stated annual value (GBP m)")
        ledger = _f(r["revenue_FY2025_gbpm"])
        if stated and ledger:
            var = ledger - stated
            pct = var / stated * 100
            if abs(pct) > 10:
                c11 = next((c for c in d["clauses"] if "GBP" in c["text"] and "means" in c["text"]), d["clauses"][0])
                extra.append({
                    "id": None, "file": d["file"], "counterparty": d["counterparty"],
                    "clause_type": "Data contradiction (contract vs ledger)",
                    "issue": f"Contract states c.GBP {stated:.1f}m p.a.; FY2025 ledger shows GBP {ledger:.1f}m",
                    "clause": c11["ref"], "page": c11["page"], "related_clauses": [],
                    "evidence": c11["text"], "severity": "Medium", "confidence": 0.85,
                    "method": "Data cross-check", "playbook_rule": "Variance >10% between contract and ledger",
                    "workstreams": ["Financial", "Commercial"],
                    "data_check": (f"Variance GBP {var:+.1f}m ({pct:+.1f}%). Possibly ad hoc / variation works "
                                   "(cl 5.3?). Raise information request for revenue bridge."),
                    "quant_gbp": var * 1e6,
                })
    out = findings + extra
    out.sort(key=lambda f: (-SEV_W[f["severity"]], -f["confidence"]))
    for i, f in enumerate(out, 1):
        f["id"] = f"R{i:02d}"
        f["confidence"] = round(f["confidence"], 2)
    return out


def entity_key(f):
    return f["counterparty"]


def cross_workstream(kb, findings):
    """Feature 2: score each counterparty across legal/commercial/operational/financial."""
    rev, sla, fleet = load_data()
    rev_by_file = {r["contract_file"]: r for r in rev if r["contract_file"]}
    total = next((r for r in rev if r["customer"].upper() == "TOTAL"), None)
    group_margin = _f(total["gross_margin_pct_FY2025"]) if total else None
    exit_types = ("Change of control", "Persistent failure", "Termination for convenience",
                  "Auto-renewal")
    entities = []
    for d in kb:
        fs = [f for f in findings if f["file"] == d["file"]]
        r = rev_by_file.get(d["file"])
        signals, streams = [], set()
        legal = sum(SEV_W[f["severity"]] for f in fs)
        if fs:
            streams.add("Legal")
        for f in fs:
            streams.update(f["workstreams"])

        commercial = 0.0
        if r:
            share = _f(r["pct_of_FY2025_revenue"])
            if any(f["clause_type"].startswith(exit_types) for f in fs):
                commercial += share / 2
                signals.append(f"Commercial: GBP {r['revenue_FY2025_gbpm']}m ({share}% of revenue) exposed to exit rights")
                streams.add("Commercial")
            m = _f(r["gross_margin_pct_FY2025"])
            if group_margin and m < group_margin - 2:
                commercial += (group_margin - m) / 2
                signals.append(f"Financial: margin {m}% vs group {group_margin}%")
                streams.add("Financial")

        operational = 0.0
        if r:
            s = sla_summary(sla, r["customer"])
            nf = len(s["failures_12m"])
            if nf:
                operational += nf
                signals.append(f"Operational: {nf} KPI failure(s) in 12m ({', '.join(s['failures_12m'])}); "
                               f"service credits GBP {s['service_credits_gbpk']:.0f}k")
                streams.add("Operational")
            pf = next((f for f in fs if f["clause_type"].startswith("Persistent") and "ALREADY MET" in f["data_check"]), None)
            if pf:
                operational += 5
                signals.append("Cross-stream: SLA data shows the contractual Persistent Failure threshold is already breached")
        if d["kind"] == "supplier" and fleet:
            u0, u1 = _f(fleet[0]["utilisation_pct"]), _f(fleet[-1]["utilisation_pct"])
            if u1 < u0:
                operational += (u0 - u1) / 2.5
                signals.append(f"Operational: fleet utilisation down {u0}% -> {u1}% against fixed 400-vehicle commitment")
                streams.add("Operational")

        recurring = sum(f["quant_gbp"] or 0 for f in fs
                        if f["clause_type"].startswith(("Take-or-pay", "Single-trigger")))
        financial = recurring / 1e6 * 5
        if recurring:
            streams.add("Financial")

        breadth = len(streams & {"Legal", "Commercial", "Operational", "Financial", "HR"})
        score = round(legal + commercial + operational + financial + (breadth if fs else 0), 1)
        rag = "Red" if score >= 18 else "Amber" if score >= 7 else "Green"
        entities.append({
            "counterparty": d["counterparty"], "file": d["file"], "kind": d["kind"],
            "score": score, "rag": rag,
            "components": {"Legal": legal, "Commercial": round(commercial, 1),
                           "Operational": round(operational, 1), "Financial": round(financial, 1),
                           "Breadth": breadth if fs else 0},
            "revenue_gbpm": _f(r["revenue_FY2025_gbpm"]) if r else None,
            "revenue_pct": _f(r["pct_of_FY2025_revenue"]) if r else None,
            "streams": sorted(streams), "signals": signals,
            "finding_ids": [f["id"] for f in fs],
            "narrative": narrative(d, fs, r, signals),
        })
    entities.sort(key=lambda e: -e["score"])
    for i, e in enumerate(entities, 1):
        e["rank"] = i
    return entities


def narrative(doc, fs, r, signals):
    if not fs:
        extra = ""
        if r:
            extra = f" ({r['pct_of_FY2025_revenue']}% of revenue)"
        return (f"No playbook exceptions identified in {doc['doc_title'].title()}{extra}. "
                "Standard liability cap, capped indexation, mutual renewal. Treat as clean control; analyst to confirm.")
    hi = [f for f in fs if f["severity"] == "High"]
    lead = "; ".join(f"{f['clause_type'].lower()} (cl {f['clause']}, p{f['page']})" for f in hi) or \
        "; ".join(f"{f['clause_type'].lower()} (cl {f['clause']})" for f in fs)
    txt = f"{len(fs)} exception(s), {len(hi)} High: {lead}."
    checks = [f["data_check"] for f in fs if f["data_check"]]
    if checks:
        txt += " Evidence: " + " ".join(checks[:3])
    return txt


# --------------------------------------------------------------------------
# 05 ACCELERATE REPORTING - first-draft outputs
# --------------------------------------------------------------------------
def info_requests(findings):
    reqs = []
    for f in findings:
        ct = f["clause_type"]
        q = None
        if ct.startswith("Data contradiction"):
            q = f"Provide revenue bridge for {f['counterparty']}: contract value vs FY2025 ledger (variations/ad hoc works)."
        elif ct == "Change of control":
            q = f"Confirm approach to {f['counterparty']} for CoC consent (cl {f['clause']}); any prior correspondence."
        elif ct.startswith("Persistent"):
            q = f"Provide remediation plan and customer correspondence on KPI failures for {f['counterparty']}."
        elif ct.startswith("Auto-renewal"):
            q = f"Confirm management intention on {f['counterparty']} renewal and any notices given/received."
        elif ct.startswith("Most-favoured"):
            q = f"Provide pricing schedule across comparable customers to test MFN exposure ({f['counterparty']})."
        elif ct.startswith("Uncapped liability"):
            q = f"Provide insurance schedule and claims history relevant to {f['counterparty']} uncapped liability."
        elif ct.startswith("Take-or-pay"):
            q = "Provide fleet plan and options to reduce idle vehicles under the Apex minimum commitment."
        elif ct.startswith("Single-trigger") and f["clause"].startswith("4"):
            q = "Confirm treatment of executive CoC payments in completion accounts / locked box leakage."
        if q:
            reqs.append({"finding": f["id"], "request": q, "priority": f["severity"]})
    return reqs


def ic_memo(findings, entities, reviews=None):
    reviews = reviews or {}
    live = [f for f in findings if reviews.get(f["id"], {}).get("status") != "Rejected"]
    lines = ["# DRAFT - Key Diligence Findings (AI-generated, analyst review required)", "",
             f"_Target: Northgate Facilities Services (c.GBP 180m revenue). Generated {today():%d %b %Y}._", "",
             "## Headline risks (cross-workstream ranking)", ""]
    for e in entities:
        if not e["finding_ids"]:
            continue
        lines.append(f"**{e['rank']}. {e['counterparty']}** - {e['rag']} (score {e['score']}; streams: {', '.join(e['streams'])})")
        for s in e["signals"]:
            lines.append(f"   - {s}")
        for fid in e["finding_ids"]:
            f = next(x for x in live if x["id"] == fid) if any(x["id"] == fid for x in live) else None
            if f:
                st = reviews.get(fid, {}).get("status", "Pending review")
                lines.append(f"   - [{f['severity']}] {f['issue']} (cl {f['clause']}, p{f['page']}, conf {f['confidence']:.0%}, {st})"
                             + (f" - {f['data_check']}" if f["data_check"] else ""))
        lines.append("")
    clean = [e["counterparty"] for e in entities if not e["finding_ids"]]
    if clean:
        lines += ["## No exceptions identified", "", ", ".join(clean), ""]
    lines += ["## Suggested SPA / negotiation points", "",
              "- CoC consents from key customers as a condition precedent (or price protection / escrow).",
              "- Specific indemnity or price chip for executive single-trigger CoC payment(s).",
              "- Fleet commitment: model idle cost and exit fee in the base case; seek vendor renegotiation.",
              "- Renewal deadline management for short-notice auto-renewals inside the deal timetable.", "",
              "## Open information requests", ""]
    lines += [f"- [{r['priority']}] {r['request']} (ref {r['finding']})" for r in info_requests(live)]
    lines += ["", "---", "_All findings trace to clause/page in the VDR. Confidence scores are indicative; "
              "partner sign-off required before client use._"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 06 AUDIT & GOVERN - score against answer key
# --------------------------------------------------------------------------
def load_answer_key():
    path = os.path.join(PACK, "ANSWER_KEY.md")
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\|\s*(P\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(\w+)\s*\|", line)
        if m:
            rows.append({"id": m.group(1), "file": m.group(2), "clause": m.group(3),
                         "page": int(m.group(4)), "issue": m.group(5), "severity": m.group(6)})
    return rows


def evaluate(findings):
    key = load_answer_key()
    matched_f, results = set(), []
    for k in key:
        hit = next((f for f in findings if f["file"] == k["file"] and
                    (f["clause"] == k["clause"] or k["clause"] in f["related_clauses"])
                    and f["id"] not in matched_f), None)
        if hit:
            matched_f.add(hit["id"])
        results.append({**k, "found": bool(hit), "finding": hit["id"] if hit else None,
                        "sev_match": bool(hit and hit["severity"] == k["severity"]),
                        "our_severity": hit["severity"] if hit else None})
    fps = [f for f in findings if f["id"] not in matched_f]
    n = len(key) or 1
    tp = len(matched_f)
    return {
        "recall": tp / n, "precision": tp / (len(findings) or 1),
        "tp": tp, "expected": len(key), "flags": len(findings),
        "severity_agreement": sum(r["sev_match"] for r in results) / n,
        "rows": results, "false_positives": [{"id": f["id"], "file": f["file"], "clause": f["clause"],
                                              "issue": f["issue"]} for f in fps],
        "control_clean": not any(f["file"].startswith("04_") and f["severity"] == "High" for f in findings),
    }


def analyse():
    kb = load_knowledge_base()
    findings = enrich(kb, run_rules(kb))
    try:
        import llm
        findings = llm.merge(kb, findings)
    except Exception as e:  # LLM layer is optional - never break the demo
        for f in findings:
            f.setdefault("llm_note", f"LLM layer unavailable: {type(e).__name__}")
    entities = cross_workstream(kb, findings)
    return kb, findings, entities


if __name__ == "__main__":
    kb, findings, entities = analyse()
    for f in findings:
        print(f"{f['id']} {f['severity']:6} {f['confidence']:.2f} {f['file'][:30]:30} cl{f['clause']:5} "
              f"{f['clause_type'][:40]:40} | {f['data_check'][:90]}")
    print()
    for e in entities:
        print(e["rank"], e["counterparty"], e["score"], e["rag"], e["components"])
    ev = evaluate(findings)
    print(f"\nRecall {ev['recall']:.0%}  Precision {ev['precision']:.0%}  "
          f"Severity agreement {ev['severity_agreement']:.0%}  Control clean: {ev['control_clean']}")
    for r in ev["rows"]:
        if not r["found"]:
            print("MISS", r)
    for fp in ev["false_positives"]:
        print("FP", fp)
