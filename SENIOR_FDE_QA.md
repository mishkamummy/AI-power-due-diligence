# Senior FDE Interview Q&A - based on the Due Diligence POC

Format for each question: **Answer** → **Trade-off** → *line to say in the interview*.
Senior-level signal: reasoning about trade-offs, the customer's constraints, and what you'd do *differently* at scale. Not just what you built.

---

## Section 1 - Scoping and problem framing

### Q1. You had very little time. How did you decide what to build?
**Answer:** I ranked the brief's six capabilities by *value to the deal* and *how well they can be shown*. Missing a material risk is the costliest failure, so the risk register and the cross-workstream layer came first. I built the other four thinly to support them.
**Trade-off:** depth over breadth. It looks less complete, but every claim can be measured (14/14 against the answer key).
*"A shallow demo of six features proves nothing. Two features with measured accuracy prove the approach works."*

### Q2. What would you ask the client in the first meeting?
**Answer:** What decision is this diligence feeding (a price chip, walk-away, SPA protections)? Which risks have hurt them on past deals? Who owns the playbook? What data-room platform and security approvals apply? What does "done" look like by week 2?
**Trade-off:** time spent on discovery vs starting to build. On a live deal I'd cap discovery at 1-2 days and build alongside it.
*"I'd start from the decision the deal team needs to make, not from the technology."*

### Q3. The client says "just give us a ChatGPT for our data room." How do you respond?
**Answer:** Acknowledge the need (faster answers), then reframe: a chatbot only answers questions someone thinks to ask, and diligence fails on the questions nobody asked. Offer both: the systematic register as the core, plus Q&A with citations on top.
**Trade-off:** giving the client what they asked for vs what they need. Don't refuse; layer it.
*"I'd give them the chat, but put it on top of something that guarantees coverage."*

---

## Section 2 - Architecture decisions

### Q4. Why a workflow pipeline and not a multi-agent system?
**Answer:** The diligence steps are known in advance (ingest, extract, flag, cross-reference, report). A fixed workflow is predictable, complete, cheap and auditable. Agents earn their place when the path can't be scripted in advance.
**Trade-off:** less flexible on novel tasks, but far easier to debug, explain to partners, and certify.
*"Use the simplest architecture that's reliable, and add autonomy only where it pays for itself."*

### Q5. Where would you introduce agents, then?
**Answer:** For open-ended work: chasing information requests (draft, send, track, re-check on response) and investigating contradictions across documents (e.g. Harlow £28m contract vs £32.4m ledger).
**Trade-off:** agents add cost, latency variance and audit complexity. So I'd constrain them: limited tools, a step budget, human approval before anything goes to the target.

### Q6. Why rules plus LLM, not LLM only?
**Answer:** Rules are exact and free for thresholds ("notice under 90 days") and maths (£315k CoC payment). The LLM handles meaning and new wording. Agreement between the two raises confidence; disagreement goes to an analyst.
**Trade-off:** two systems to maintain. But each covers the other's weakness, and the disagreements are themselves useful signals.
*"Code calculates, the model interprets. I never let an LLM produce a number that goes in front of a client."*

### Q7. Why no vector database or RAG in the POC?
**Answer:** About 46 clauses fit in a single model call, so retrieval would only add a failure mode (missing a chunk). I segment by clause, not by token chunks, because a clause is the unit lawyers cite.
**Trade-off:** doesn't scale to analyst Q&A over thousands of documents. That's where I'd add hybrid keyword plus vector search. But the playbook check still runs on every clause, because completeness is the point.

### Q8. Why zero dependencies and a local app?
**Answer:** Partly forced: package installs were blocked. But it matches deal reality: locked-down machines, data that can't leave the deal room, and no security review needed for third-party packages.
**Trade-off:** no OCR, no database, single user. Fine for a POC; production swaps in enterprise components while keeping the same logic.
*"I turned a constraint into a design point, and I'm clear about what has to change for production."*

### Q9. Walk me through the production architecture.
**Answer:** Data-room connectors with change detection → job queue → parallel ingestion workers (OCR, clause segmentation, data quality) → analysis workers (rules, LLM, quote verification, cross-reference) → database + object store + search index → web app with SSO and permissions that mirror the data room. One isolated workspace per deal. Claude through a zero-retention enterprise endpoint in a UK/EU region. (See ARCHITECTURE.md, diagram 3.)
**Trade-off:** more infrastructure to run. But the workers are stateless and scale horizontally, and incremental processing keeps cost proportional to change.

### Q10. How do you handle documents being updated in the data room mid-deal?
**Answer:** Version every document, detect changes on sync, re-analyse only the changed clauses, and diff the findings ("clause 6.2 changed; CoC risk removed"). Analyst decisions stay attached to the clause version they were made on.
**Trade-off:** versioning adds complexity, but without it you can't trust the register on day 20 of a deal.

---

## Section 3 - LLM-specific trade-offs

### Q11. Which model would you use and why?
**Answer:** Claude Opus 5.5 for judgement-heavy steps (clause interpretation, cross-workstream reasoning). A cheaper model such as Claude Haiku 4.5 for high-volume, simple steps (document classification, simple extraction). The rules handle everything mechanical for free.
**Trade-off:** routing between models adds complexity. I'd first measure whether one strong model at lower effort is good enough, because one model is simpler to run and caches better.

### Q12. What does it cost at deal scale?
**Answer (back-of-envelope):** 5,000 documents × about 5k tokens = 25M input tokens. At Opus 5.5's $4 per million input that's about $100, plus about $50 of output, so **roughly $150 per deal**. The Batch API halves that for overnight runs, and prompt caching of the playbook reduces input cost further.
**Trade-off:** negligible next to analyst time (one analyst-day costs more), so I'd optimise for accuracy first and cost second.
*"LLM cost isn't the constraint here. Trust and accuracy are."*

### Q13. LLMs are non-deterministic. How do you keep the register stable?
**Answer:** Structured JSON output against a fixed schema; cache responses per document version, so a re-run doesn't re-generate; rules give a deterministic baseline; findings only change when the source changes.
**Trade-off:** caching can hide a model improvement. So re-runs are deliberate and versioned, not accidental.

### Q14. How do you prevent hallucinated findings?
**Answer:** The LLM must cite a clause number and quote the clause. Each finding is matched to a real clause in the index. LLM-only findings are capped at 70% confidence and marked "needs review". Next step: automatically check that the quote really appears in the source.
**Trade-off:** strict verification can drop some valid paraphrased findings. That's acceptable, because a dropped finding still exists as a rule flag or goes to review.

### Q15. What about prompt injection? Documents come from the counterparty.
**Answer:** Good point, and it's a real risk: the seller controls the data room content. Treat document text strictly as data: keep it separate from instructions, use structured outputs, give the analysis step no tools, verify quotes against the source, and run the rules independently so one manipulated LLM output can't suppress a finding.
**Trade-off:** sandboxing limits what agents can do with documents. That's the right default for adversarial input.
*"In M&A the data room is written by the other side. I treat it as untrusted input."*

---

## Section 4 - Evaluation and quality

### Q16. How do you evaluate the system?
**Answer:** POC: recall, precision and severity agreement against a planted-issue answer key, plus a clean control contract (14/14, no false positives). Production: held-out contracts labelled by lawyers, seeded issues in every live deal, analyst rejection rate as live precision, confidence calibration, and business metrics (time to first flag, analyst hours per contract).
**Trade-off:** building eval sets costs lawyer time, but without them you can't defend the output to a partner.

### Q17. Your 100% score: should I trust it?
**Answer:** No, not as a generalisation claim. The rules were written against this pack, so it's an upper bound. It proves the pipeline works end to end and is traceable; it doesn't prove accuracy on unseen contracts. A held-out test would.
*"I'd rather tell you that than have you find it."*

### Q18. Precision vs recall: where do you set the threshold?
**Answer:** Lean towards recall. A missed CoC clause can cost millions; a false flag costs 30 seconds. But watch the rejection rate: if partners see noise, they stop reading. Route by confidence: high confidence to standard review, low confidence to closer review.
**Trade-off:** more analyst review load in exchange for fewer misses, tuned over the first weeks from real rejection data.

### Q19. How are the confidence scores calculated, and are they meaningful?
**Answer:** Rule specificity + data corroboration + rule/LLM agreement. They're heuristic and not calibrated yet; they're useful for ranking, not as probabilities. I'd calibrate them from analyst decisions: findings marked 90% should be accepted about 90% of the time.

---

## Section 5 - Deployment, customer and delivery

### Q20. How do you deploy into a live deal in 4-8 weeks?
**Answer:** Week 1: secure workspace, data-room connector, agree the playbook with the legal lead. Week 2: run alongside analysts and tune on their rejections. Week 3 onwards: daily runs on new uploads; memo and information requests feed the workstreams; report accuracy weekly.
**Trade-off:** running alongside analysts doubles the effort for a week, but it's what earns trust.

### Q21. A senior lawyer says "I don't trust AI, I'll re-read everything anyway." What do you do?
**Answer:** Don't argue. Show traceability (one click to the clause), show the accuracy scorecard including misses, and propose a side-by-side on one batch. Position the tool as removing the first-pass read, not their judgement. Let the results persuade them.
*"Adoption is earned by evidence, not by argument."*

### Q22. Legal and finance disagree on how severe a finding is. Who wins?
**Answer:** Neither the tool nor me. The playbook owner sets the default, the finding shows both perspectives (legal severity + £ impact), and the deal lead decides. The system's job is to make the disagreement visible early, which is exactly what the cross-workstream layer does.

### Q23. How would you make this reusable across clients and deals?
**Answer:** Keep the engine generic and put the specifics into configuration: sector playbooks (FM, healthcare, software), reusable connectors, and per-deal data mappings. The cross-workstream joins are the deal-specific part that the FDE configures.
**Trade-off:** generic versus deal-specific. Over-generalising early slows delivery, so I'd extract reusable parts after two or three deals, not before.

### Q24. What technical debt does this POC carry?
**Answer:** Keyword rules tuned to one pack; text-only PDF parsing; JSON files instead of a database; no auth; uncalibrated confidence; hand-set risk weights; untested LLM layer; ranking not covered by automated tests.
**Trade-off:** all deliberate for speed. I'd pay off parsing, the database, auth and the eval set first, because those block production.
*"I can tell you exactly where the shortcuts are, and which order I'd fix them in."*

### Q25. What would you do differently with another week?
**Answer:** 1) Run and evaluate the Claude layer on held-out contracts. 2) Automatic quote verification. 3) Q&A with citations on top of search. 4) An information-request tracker (the "coordination friction" bottleneck in the brief). 5) An automated test for the risk ranking.

---

## Section 6 - Behavioural, FDE-flavoured

### Q26. Tell me about a constraint that changed your design.
**Answer:** Package installs were blocked, so I wrote a small PDF extractor and a web app using only standard Python. It turned out to be a better fit for locked-down deal environments: zero installs, runs anywhere, no data leaves the machine.

### Q27. Tell me about a mistake you caught.
**Answer:** The exclusivity rule flagged "exclusive jurisdiction" in a governing-law clause, a false positive. I found it by scoring against the answer key, fixed the rule, and kept it as an example of why evaluation has to be built in from day one.

### Q28. How do you balance speed for the customer with engineering quality?
**Answer:** Move fast on what's reversible (UI, weights, prompts) and be careful about what's hard to undo (data handling, confidentiality, anything client-facing). Hence the mandatory human review before outputs, and the per-deal isolation in the design.

---

## Five lines to remember
1. *"Code calculates, the model interprets."*
2. *"Workflow first; add autonomy only where it pays for itself."*
3. *"A chatbot answers the questions you ask; diligence fails on the ones you didn't."*
4. *"The data room is written by the other side, so treat it as untrusted input."*
5. *"100% on the data I built against is an upper bound, not a claim."*
