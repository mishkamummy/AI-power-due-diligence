# AI Due Diligence Accelerator - Architecture

This covers two things:
1. **What the prototype does today** (this repo), and
2. **The proposed production architecture**: how the same design scales to a real deal with thousands of documents, several workstreams and many analysts.

The **logic stays the same** between the two (ingest → extract → flag → cross-reference → report → govern). Only the components get swapped for enterprise-grade versions.

> Diagrams use Mermaid and render automatically on GitHub.

---

## 1. End-to-end workflow (the six capabilities from the brief)

```mermaid
flowchart LR
    subgraph IN["Inputs"]
        VDR["Virtual Data Room<br/>contracts, financials,<br/>HR, ops reports"]
        CD["Client data<br/>revenue ledger, SLA/KPI,<br/>fleet, payroll"]
        PB["Clause playbook<br/>owned by legal team"]
    end

    subgraph AI["AI Diligence Pipeline"]
        S1["01 Ingest<br/>parse, OCR, clause<br/>segmentation, index"]
        S2["02 Extract<br/>normalised key terms<br/>value, term, caps, notice"]
        S3["03 Flag and Prioritise<br/>playbook rules +<br/>LLM second reviewer"]
        S4["04 Cross-Reference<br/>join clauses to client data,<br/>quantify GBP impact"]
        S5["05 Accelerate Reporting<br/>draft memo, info request<br/>list, register export"]
    end

    subgraph HUMAN["Human-in-the-loop"]
        REV["Analyst review<br/>accept / escalate / reject"]
        PART["Partner sign-off"]
    end

    S6["06 Audit and Govern<br/>traceability, confidence,<br/>review log, accuracy KPIs"]

    VDR --> S1 --> S2 --> S3 --> S4 --> S5
    CD --> S4
    PB --> S3
    S3 --> REV
    S4 --> REV
    REV --> S5 --> PART
    REV -. "rejection notes = training signal" .-> PB
    S1 & S3 & S4 & REV --> S6
```

**Key design choices**
- **Push, not pull:** every clause is checked against every playbook rule, so findings don't depend on someone thinking to ask.
- **Lawyers own the playbook; the system applies it.** Analyst rejections feed back into improving it.
- **Nothing reaches a client-facing output without human review.**

---

## 2. Prototype architecture (this repo, as built)

```mermaid
flowchart TB
    subgraph LOCAL["Runs locally - Python standard library only, zero installs"]
        PDF["synthetic_pack/contracts/*.pdf"] --> PT["pdftext.py<br/>PDF text extraction"]
        PT --> KB["Clause index<br/>ref, page, text"]
        CSV["synthetic_pack/data/*.csv<br/>revenue, SLA, fleet, playbook"] --> ENG
        KB --> ENG["engine.py<br/>12 playbook rules<br/>data cross-checks<br/>cross-workstream scoring<br/>memo + info requests<br/>evaluation vs answer key"]
        ENG <--> LLM["llm.py - optional<br/>Claude second reviewer<br/>JSON schema output"]
        LLM <--> CACHE[("app/cache/<br/>saved LLM responses")]
        ENG --> SRV["server.py<br/>JSON API + exports"]
        SRV --> UI["index.html dashboard<br/>Register | Insights | KB<br/>Draft outputs | Governance"]
        UI -- "accept / reject" --> LOG[("review_log.json<br/>audit trail")]
    end
    LLM <-. "HTTPS, only if API key set" .-> API["Claude API"]
```

| Prototype component | Purpose | Limitation |
|---|---|---|
| `pdftext.py` | Text from text-based PDFs | No OCR, tables or Word/Excel |
| Keyword rules | Repeatable, exact on thresholds | Tuned to this pack, so it overfits |
| Claude reviewer | Covers unseen wording | Not yet tested on new contracts |
| JSON files | Review log and LLM cache | Single user, no concurrency |
| Local web server | Zero-install demo | No auth, single machine |

---

## 3. Production architecture (proposed, scalable)

```mermaid
flowchart TB
    subgraph SRC["Sources"]
        VDR["VDR<br/>Intralinks / Datasite"]
        CLI["Client data<br/>ERP, ledger, KPI exports"]
        EXT["Benchmarks and<br/>precedent deals"]
    end

    subgraph TENANT["Firm cloud tenancy - one isolated workspace per deal"]
        direction TB
        CONN["Connectors<br/>VDR sync, SFTP, API<br/>change detection"]
        Q[["Job queue<br/>one task per document"]]

        subgraph ING["Ingestion workers - scale horizontally"]
            OCR["Parse + OCR<br/>layout, tables, schedules"]
            SEG["Clause segmentation<br/>versioning, de-duplication"]
            DQ["Data quality checks<br/>unreadable, missing, duplicate"]
        end

        subgraph ANALYSIS["Analysis workers"]
            RULES["Rule engine<br/>thresholds and maths"]
            LLMW["LLM reviewer<br/>batched calls,<br/>prompt-cached playbook"]
            VERIFY["Quote verification<br/>citation must match source"]
            XREF["Cross-workstream joins<br/>legal x commercial x<br/>ops x financial"]
        end

        subgraph STORE["Data layer"]
            OBJ[("Object store<br/>raw documents")]
            DB[("Relational DB<br/>clauses, findings,<br/>reviews, audit")]
            IDX[("Search index<br/>keyword + vector")]
        end

        APP["Web app + API<br/>SSO, role-based access<br/>mirrors VDR permissions"]
        RPT["Report generator<br/>memo, IRL, Word/Excel export"]
        MON["Monitoring<br/>accuracy KPIs, LLM cost,<br/>latency, drift"]
    end

    LLMAPI["Claude via enterprise endpoint<br/>zero data retention, UK/EU region<br/>e.g. Bedrock / Vertex / Claude API"]

    subgraph USERS["Users"]
        AN["Analysts by workstream"]
        PT2["Partners / deal lead"]
        LEG["Legal - playbook owners"]
    end

    VDR & CLI & EXT --> CONN --> Q --> ING
    OCR --> SEG --> DQ
    ING --> OBJ & DB & IDX
    DB --> ANALYSIS
    RULES & LLMW --> VERIFY --> XREF --> DB
    LLMW <--> LLMAPI
    DB & IDX --> APP --> AN & PT2
    LEG -- "edit playbook" --> APP
    APP --> RPT
    ANALYSIS & APP --> MON
```

### What changes from prototype to production

| Concern | Prototype | Production |
|---|---|---|
| **Volume** | 6 PDFs | 1,000s of documents; queue + parallel workers |
| **Formats** | Text PDFs | OCR, Word, Excel, scanned, email |
| **Detection** | Keyword rules + optional LLM | Rules for thresholds/maths; LLM is primary for clause meaning; quote verification |
| **Incremental updates** | Re-run everything | Process only new or changed documents (change detection) |
| **Search** | Keyword over clauses | Hybrid keyword + vector index; Q&A with citations |
| **Storage** | JSON files | Relational DB + object store; full version history |
| **Users** | Single local user | SSO, role-based access per workstream, concurrency |
| **Confidentiality** | Runs on laptop | Isolated workspace per deal, no cross-deal data, zero-retention LLM |
| **Governance** | Review log + answer key | Audit DB, calibrated confidence, accuracy dashboard, escalation paths |
| **Cost control** | ~6 calls/run | Batch API, prompt caching, only re-review changed clauses |

---

## 4. How a new document flows through the system

```mermaid
sequenceDiagram
    autonumber
    participant V as VDR
    participant C as Connector
    participant W as Ingestion worker
    participant A as Analysis worker
    participant L as Claude (enterprise)
    participant D as Findings DB
    participant U as Analyst

    V->>C: New / updated document
    C->>W: Queue job (doc id, version)
    W->>W: Parse, OCR, split into clauses with page refs
    W->>D: Store clauses + data quality flags
    D->>A: Trigger analysis for changed clauses only
    A->>A: Run playbook rules (thresholds, maths)
    A->>L: Clauses + playbook (structured JSON output)
    L-->>A: Candidate findings with quotes
    A->>A: Verify quotes against source, merge with rules, score confidence
    A->>A: Join to client data (revenue, SLA, fleet) and quantify GBP impact
    A->>D: Save findings + evidence + confidence
    D-->>U: Notify: new High finding on key customer
    U->>D: Accept / escalate / reject with note
    D->>D: Audit log entry, memo + IRL refreshed
```

**Effect on timelines:** a document uploaded in the morning has first-pass flags in minutes, not after it reaches the front of an analyst's reading queue. Risks show up while there's still negotiating leverage.

---

## 5. Human-in-the-loop and governance

```mermaid
flowchart LR
    F["New finding"] --> C{"Confidence<br/>and agreement"}
    C -- "Rule + LLM agree,<br/>high confidence" --> Q1["Analyst queue<br/>standard review"]
    C -- "Only one method flags,<br/>or low confidence" --> Q2["Analyst queue<br/>needs closer review"]
    C -- "High severity +<br/>material GBP impact" --> Q3["Escalate to<br/>deal lead / partner"]
    Q1 & Q2 & Q3 --> D{"Analyst decision"}
    D -- "Accept" --> R["Register + draft memo"]
    D -- "Escalate" --> P["Partner review"] --> R
    D -- "Reject + reason" --> X["Excluded from outputs"]
    X --> FB["Feedback loop<br/>tune rules and prompts,<br/>calibrate confidence"]
    R --> S["Partner sign-off<br/>before client use"]
```

**Controls**
- **Traceability:** every finding cites document, clause, page and a verbatim quote that has been checked against the source.
- **Confidence:** comes from rule strength, data corroboration and LLM agreement. It is calibrated over time from analyst decisions.
- **Accuracy KPIs:** recall and precision against seeded test issues and a clean control document, measured on every deal.
- **Confidentiality:** one workspace per deal, access mirrors VDR permissions, zero-retention LLM endpoint, no training on client data.

---

## 6. Scaling strategy

```mermaid
flowchart LR
    A["Pilot<br/>1 deal, 1 workstream<br/>legal contracts"] --> B["Expand<br/>all workstreams<br/>+ client data joins"]
    B --> C["Repeatable<br/>playbook library<br/>per sector"]
    C --> D["Firm-wide<br/>multiple concurrent deals,<br/>precedent learning"]
```

| Scale lever | How |
|---|---|
| **Throughput** | Stateless workers on a queue; add workers as document volume grows |
| **Latency** | Incremental processing: only new or changed clauses are re-analysed |
| **LLM cost** | Prompt caching of playbook and instructions; Batch API for overnight bulk runs; rules handle the mechanical checks for free |
| **Reuse across deals** | Sector playbooks (FM, healthcare, software...) maintained by legal; connectors reused |
| **Quality at scale** | Seed known test issues into every deal; track recall/precision; sample-audit accepted findings |
| **Multi-deal isolation** | Separate workspace per deal (storage, index, keys), so no data crosses information barriers |

---

## 7. Deployment plan within a live deal (4-8 weeks)

```mermaid
gantt
    dateFormat  YYYY-MM-DD
    title Deployment inside an active transaction
    axisFormat  Wk %W
    section Setup
    VDR connector + secure workspace     :a1, 2026-10-12, 5d
    Agree playbook with legal lead       :a2, 2026-10-12, 4d
    section First pass
    Ingest + rules + LLM on first batch  :b1, after a1, 4d
    Analyst parallel review and tuning   :b2, after b1, 5d
    section Scale out
    Client data joins - revenue SLA HR   :c1, after b1, 7d
    Daily runs on new VDR uploads        :c2, after b2, 21d
    section Reporting
    Draft memo + IRL into workstreams    :d1, after c1, 14d
    Accuracy KPIs reported weekly        :d2, after b2, 21d
```

**Success metrics:** time from upload to first flag · analyst hours per contract · share of material risks found before SPA drafting · recall/precision on seeded issues · analyst rejection rate over time.
