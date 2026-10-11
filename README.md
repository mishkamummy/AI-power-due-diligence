# AI Due Diligence Accelerator - Demo

Prototype for the *AI-enabled Due Diligence Acceleration* case study, run on the synthetic
Northgate Facilities Services data pack (`synthetic_pack/`).

The two main features:

| # | Feature | Case-study output it delivers |
|---|---|---|
| 1 | **Risk & Exception Register**: clause-level flags vs. the playbook, with clause/page traceability, verbatim evidence, confidence, analyst Accept/Escalate/Reject | *Risk & Exception Register* (+ Ingest, Extract, Flag, Audit) |
| 2 | **Cross-Workstream Insight Layer**: joins contract flags to revenue, SLA and fleet data, quantifies GBP impact, ranks counterparties | *Cross-Workstream Insight Layer* (+ Cross-Reference, Accelerate Reporting) |

Supporting tabs: Deal Knowledge Base (clause search), Draft Outputs (findings memo + info
request list), Governance (accuracy vs `ANSWER_KEY.md` + review audit trail).

## Run it

Needs Python 3.9+ only. No packages to install.

```bash
cd AI-power-due-diligence
python3 app/server.py
```

Open http://localhost:8501 . Use a different port if needed: `PORT=8600 python3 app/server.py`.

Command-line view of the same analysis: `python3 app/engine.py`

Pin the "today" date so deadline maths matches the answer key: `DD_TODAY=2026-10-12 python3 app/server.py`

### Optional: Claude as second reviewer

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
python3 app/server.py
```

Each contract goes to Claude (`claude-opus-5-5`, structured JSON output) together with the
playbook. Findings the rules and Claude agree on get a confidence boost (method "Rule + LLM").
Findings Claude raises alone are added as "LLM only - needs review". Responses are cached in
`app/cache/`, so the demo can replay offline. Turn it off with `DD_LLM=0`.

## Architecture

```
synthetic_pack/contracts/*.pdf ─► pdftext.py (stdlib PDF text) ─► clause index (ref, page, text)
synthetic_pack/data/*.csv ───────────────────────────────┐
clause_playbook.csv ─► engine.run_rules (12 detectors) ──┼─► engine.enrich (data cross-checks, GBP)
                       llm.py (optional Claude review) ──┘          │
                                                     engine.cross_workstream (score/rank)
                                                     engine.ic_memo / info_requests
                                                     engine.evaluate (vs ANSWER_KEY.md)
server.py (http.server JSON API) ─► index.html (dashboard)  ;  review_log.json (audit trail)
```

## Results on the pack

- 6 documents, 14 flags. **Recall 14/14, precision 14/14, severity agreement 100%.** The clean control (Bridgeway) gets no flags.
- Ranking matches the expected register: Harlow > Meridian > Apex > Ops Director CoC > Castlebrook > Bridgeway.
- Key numbers: Harlow 18% of revenue plus a CoC exit right plus 4 KPI failures in 6 months (threshold 3), GBP 270k service credits, GBP 4.4m contract-vs-ledger gap. Apex: 59 idle vehicles, c.GBP 0.67m/yr. Exec CoC: GBP 315k plus up to GBP 84k bonus. Meridian renewal notice deadline: 1 Dec 2026.
