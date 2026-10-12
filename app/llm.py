"""Optional Claude second-reviewer.

If the `anthropic` SDK is installed and credentials are available
(ANTHROPIC_API_KEY or `ant auth login`), each contract is sent to Claude
with the clause playbook. Claude's findings are merged with the rule
engine's:
  - both agree      -> confidence boosted, method "Rule + LLM"
  - LLM-only        -> added as a new finding, flagged "Needs review"
  - rule-only       -> kept, noted as not corroborated by LLM
Results are cached to app/cache/ so the demo replays offline.
Set DD_LLM=0 to switch the layer off.
"""
import json
import os

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
MODEL = os.environ.get("DD_MODEL", "claude-opus-5-5")

SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clause": {"type": "string", "description": "Clause number, e.g. 6.2"},
                    "clause_type": {"type": "string"},
                    "severity": {"type": "string", "enum": ["High", "Medium", "Low"]},
                    "confidence": {"type": "number"},
                    "issue": {"type": "string"},
                    "quote": {"type": "string", "description": "Verbatim quote from the clause"},
                },
                "required": ["clause", "clause_type", "severity", "confidence", "issue", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def _playbook_text():
    from engine import load_playbook
    return "\n".join(f"- {k}: look for {v['what_to_look_for']}. Rule: {v['standard_position_or_rule']}. "
                     f"Default severity: {v['default_severity']}" for k, v in load_playbook().items())


def review_contract(doc):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, doc["file"] + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    import anthropic  # imported lazily so the app runs without it
    client = anthropic.Anthropic()
    clauses = "\n".join(f"[{c['ref']}] (page {c['page']}) {c['text']}" for c in doc["clauses"])
    prompt = (
        "You are a legal due diligence analyst reviewing a target company's contract for a PE buyer. "
        "The target is Northgate Facilities Services (the Supplier/Company/Lessee).\n\n"
        f"Clause playbook:\n{_playbook_text()}\n\n"
        f"Contract: {doc['doc_title']} ({doc['kind']})\n{clauses}\n\n"
        "Return every clause that is non-standard under the playbook. One finding per issue; cite the single "
        "most relevant clause number. Quote verbatim. Do not flag standard or protective provisions. "
        "If nothing is non-standard, return an empty list."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM refused")
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    json.dump(data, open(path, "w"), indent=2)
    return data


def available():
    if os.environ.get("DD_LLM", "1") == "0":
        return False
    if os.path.isdir(CACHE) and os.listdir(CACHE):
        return True
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def merge(kb, findings):
    if not available():
        for f in findings:
            f["llm_note"] = "LLM layer off (rules only)"
        return findings
    # Call the API for every contract first, so a failure leaves the rule findings untouched
    reviews = {doc["file"]: review_contract(doc)["findings"] for doc in kb}
    for doc in kb:
        llm_fs = reviews[doc["file"]]
        mine = [f for f in findings if f["file"] == doc["file"]]
        used = set()
        for f in mine:
            match = next((i for i, l in enumerate(llm_fs) if i not in used and
                          (l["clause"] == f["clause"] or l["clause"] in f["related_clauses"])), None)
            if match is not None:
                used.add(match)
                f["method"] = "Rule + LLM"
                f["confidence"] = round(min(0.99, (f["confidence"] + llm_fs[match]["confidence"]) / 2 + 0.05), 2)
                f["llm_note"] = "Corroborated by LLM: " + llm_fs[match]["issue"]
            else:
                f["llm_note"] = "Not raised by LLM - analyst to confirm"
        clause_by_ref = {c["ref"]: c for c in doc["clauses"]}
        for i, l in enumerate(llm_fs):
            if i in used:
                continue
            c = clause_by_ref.get(l["clause"])
            findings.append({
                "id": None, "file": doc["file"], "counterparty": doc["counterparty"],
                "clause_type": l["clause_type"], "issue": l["issue"], "clause": l["clause"],
                "page": c["page"] if c else None, "related_clauses": [],
                "evidence": c["text"] if c else l["quote"], "severity": l["severity"],
                "confidence": round(min(l["confidence"], 0.7), 2), "method": "LLM only",
                "playbook_rule": "", "workstreams": ["Legal"], "data_check": "",
                "quant_gbp": None, "llm_note": "LLM-only finding - needs analyst review",
            })
    from engine import SEV_W
    findings.sort(key=lambda f: (-SEV_W.get(f["severity"], 1), -f["confidence"]))
    for i, f in enumerate(findings, 1):
        f["id"] = f"R{i:02d}"
    return findings
