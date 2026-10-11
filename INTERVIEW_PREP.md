# Interview Prep - AI Due Diligence Accelerator

## 30-second pitch
"Deal teams lose time on two things: reading contracts by hand to find non-standard terms, and
spotting late that a legal clause and an operational or financial fact add up to one big risk. I built
those two things. First, a risk register: every flag cites the clause, page and verbatim quote, and an
analyst accepts or rejects it. Second, a cross-workstream layer that joins those flags to revenue, SLA
and fleet data and ranks counterparties. On the synthetic pack it found all 14 planted issues with no
false positives, matched the expected risk ranking, and passed the clean control contract. It runs
locally with zero installs, because a live deal gives you weeks, not months, and the data can't leave
the deal room."

---

## A. Scope and prioritisation

**Q1. The brief lists six capabilities. Why build these two?**
- They map directly to two of the four "Expected Outputs" (Risk & Exception Register, Cross-Workstream Insight Layer), and they are where the value is: finding risks *earlier* and *not missing* them.
- Together they still touch all six steps: ingest, extract, flag, cross-reference, a first-draft memo, and audit. I built the other four thinly, enough to support these two.
- The knowledge base on its own (search or chat) is a convenience. It doesn't find risks. A partner cares about "what can hurt the deal," not "can I search the VDR faster."
- The cross-workstream layer is the differentiator. Harlow's CoC clause looks like a routine legal point until you join it to 18% of revenue and SLA data showing the termination threshold is *already* breached. No single workstream catches that.

**Q2. Why not build a chatbot over the data room? That's what most people demo.**
- A chatbot is *pull*: it only answers the questions the analyst thinks to ask. Missed findings come from questions nobody asked. The register is *push*: it checks every clause against every playbook rule.
- Chat answers are hard to audit, hard to compare across documents, and change with phrasing. A register is structured, so you can sort, filter, export and reconcile it.
- I did include clause search as a supporting feature. In production I'd add Q&A with citations, as a layer on top of the register rather than instead of it.

---

## B. Technical approach - why this and not that

**Q3. Why a hybrid of deterministic rules plus an LLM, and not just an LLM?**
- **Repeatability and audit:** the same documents always give the same register. In a live deal, partners need to know why something was flagged, and that it won't vanish on a re-run.
- **Precision on mechanical checks:** "notice under 90 days," "exit fee above 50%," "indexation with no cap" are thresholds. Code is exact and free. An LLM can misread "thirty (30) days."
- **Numbers must be computed, not generated:** the £315k CoC payment, 59 idle vehicles, the £4.4m variance. LLMs shouldn't do arithmetic you then put in front of a client.
- **The LLM adds coverage:** rules only find what they were written for. The LLM is an independent second reviewer that catches new clause wording. Where both agree, confidence goes up. Where only one flags, it goes to an analyst.
- It mirrors how deal teams already work, with a junior reviewer plus a second check.

**Q4. Then why not rules only? You got 100% without the LLM.**
- Because I wrote the rules against this pack, the 100% is partly overfitting, and I'd say that openly. On a new deal, contracts word things differently ("change in shareholding," "assignment by operation of law"). Rules will miss those; an LLM generalises.
- The rule engine is the reliable baseline. The LLM gives recall on unseen wording. Analyst review handles what's left.

**Q5. Why not fine-tune a model, or train a clause classifier?**
- The brief rules it out: "no time for lengthy platform builds or bespoke model training."
- Practically: no labelled data at the start of a deal, weeks of work, and a model that's stale by the next deal. A playbook plus a frontier model with structured output is deployable on day one, and the playbook is something lawyers can read and edit.

**Q6. Why not buy a tool like Kira, Luminance or Harvey?**
- Firms often should, for contract extraction at scale. I'd position this as complementary, not competing.
- What those tools don't do out of the box is the cross-workstream join: tying a clause to the client's revenue ledger, SLA history and fleet data, with £ impact. That join is deal-specific, which is exactly the forward-deployed work.
- Procurement and onboarding a new vendor onto a live deal under NDA rarely fits in a 4-8 week window. This runs on day one inside existing controls.

**Q7. Why no vector database or RAG?**
- Six documents, about 46 clauses: the whole contract fits in one model call. Retrieval would add a failure mode (missing the relevant chunk) and buy nothing.
- I segment by **clause**, not by token chunks, because a clause is the unit lawyers cite and the unit of traceability.
- At a few thousand documents I'd add a retrieval index (hybrid keyword plus embeddings) for search and Q&A. But the playbook check would still run on every clause of every contract, because completeness is the point.

**Q8. Why plain Python, no frameworks, a local web app?**
- Partly forced: package installs were blocked in my environment. That turned out to be a realistic deal constraint, since VDR and client environments are locked down. Zero dependencies means it runs on any analyst laptop or approved VM with no security review of third-party packages.
- Local means the data never leaves the environment, which matters under NDA and information barriers.
- In production I'd use proper components: a robust PDF/OCR service, a database, SSO, and a hosted UI inside the firm's tenancy. The architecture stays the same; the parts get swapped.

**Q9. How does the PDF ingestion handle messy documents?**
- Honestly, the prototype handles text-based PDFs only. That's what the pack contains.
- For production: OCR for scans, layout-aware parsing for tables and schedules, Word/Excel ingestion, de-duplication of versions, and a "document quality" flag so unreadable files show up as a data gap instead of failing silently.
- The brief says the system must tolerate messy data. My answer is to **make gaps visible**. The contract-vs-ledger contradiction (Harlow £28.0m vs £32.4m) is a finding, and it generates an information request.

---

## C. Accuracy, risk and governance

**Q10. How do you stop the LLM from hallucinating findings?**
- Structured JSON output against a fixed schema, so it must cite a clause number and quote the clause.
- Each LLM finding is tied back to a real clause in the index. LLM-only findings are capped at 70% confidence and labelled "needs analyst review."
- Nothing reaches the memo without the review workflow, and rejected findings are excluded and logged.
- Next step I'd add: automatically check that the quote really appears in the clause text, and drop it if not. Cheap and deterministic.

**Q11. How are confidence scores calculated? Are they calibrated?**
- Rule specificity sets the base (an explicit "take-or-pay" scores higher than inferred wording). Corroborating client data raises it (e.g. SLA data confirms the breach). Rule and LLM agreement raises it again.
- They are *not* statistically calibrated yet, and I wouldn't claim they are. To calibrate, log analyst accept/reject decisions across deals and measure: of the findings at 90%, what share were accepted? Until then, they're for ranking and triage, not probabilities.

**Q12. Precision or recall - which matters more?**
- Recall, within reason. A missed CoC clause can cost millions. A false positive costs an analyst 30 seconds to reject.
- But precision matters for trust: if partners see too much noise, they stop reading. So I report both, use Bridgeway as a clean control (any High flag there is a false positive), and require a note when rejecting so we learn from it.

**Q13. Why make analysts give a reason when they reject a finding?**
- Governance: the audit trail shows who overruled the tool and why.
- Improvement: rejection notes are labelled data for tuning rules and prompts.
- The brief requires human-in-the-loop by design: AI supports judgement and doesn't replace sign-off.

**Q14. What about confidentiality and information barriers?**
- The prototype runs locally. The only external call is the optional LLM, which would go through an enterprise API agreement with zero data retention, ideally in a UK/EU region or the firm's cloud tenancy (Bedrock or Vertex).
- In production: one isolated workspace per deal, access mirroring the VDR permissions, no cross-deal data mixing, and LLM caching scoped per deal. The playbook is the one asset shared across deals.

---

## D. The cross-workstream layer

**Q15. How is the risk score built, and isn't it arbitrary?**
- Score = legal severity points + revenue exposed to exit rights + operational evidence (KPI failures, a breached threshold, utilisation decline) + quantified £ cost + breadth (how many workstreams are linked).
- The weights are judgement calls that I set by hand, and they're transparent: every component shows in the stacked bar and heatmap. It's a triage ranking, not a valuation. In a real deal I'd agree the weights with the deal lead in the first week.
- Design choice: revenue share only counts when there's an exit right. Bridgeway is 6% of revenue but has no exit trigger, so it isn't scored as risk. Concentration alone isn't a contract risk.

**Q16. Give me one example the system finds that a siloed team would miss.**
- Harlow: the legal team sees a standard-looking CoC clause and a persistent-failure clause. Ops sees some KPI misses. Finance sees revenue above the contract value. Joined up: the deal itself triggers a termination right on 18% of revenue, *and* the customer already has a separate termination right today because the SLA threshold is breached. That changes the SPA: a consent condition precedent, price protection, or a specific indemnity.
- Apex: legal sees take-or-pay; ops sees utilisation falling from 93% to 85%. Together: c.£0.67m a year paid for idle vehicles, with a c.£12.8m exit fee locking it in.

---

## E. Deployment and the forward-deployed angle

**Q17. How would you roll this out on a live deal?**
- **Week 0-1:** connect to a VDR export. Agree the playbook with the legal lead (start from the firm's standard positions). Run on the first batch and review the outputs alongside the analysts.
- **Week 1-2:** tune rules and prompts on analyst rejections. Add the client data joins (revenue, KPIs, HR). Start daily runs as new documents land.
- **Week 2+:** the register becomes the team's working tracker. The memo and information-request list feed into workstream reports. Report recall and precision weekly.
- Success metrics: time from document upload to first flag, analyst hours per contract, findings raised before vs after the SPA draft, and the share of final-report findings first surfaced by the tool.

**Q18. How do you win over a sceptical partner or lawyer?**
- Show traceability first: every flag goes to the exact clause and page in one click.
- Show the accuracy scorecard *including* misses. Being honest about limits builds more trust than claiming perfection.
- Position it as removing the first-pass reading, not their judgement. They still sign off.
- Start with one workstream and one deal, and let results make the case.

**Q19. What would you do differently, or next?**
- Run and evaluate the LLM layer on unseen contracts, and add automatic checking of quotes.
- OCR and broader formats; versioning when documents are replaced in the VDR.
- Calibrate confidence from analyst decisions; let lawyers edit the playbook in the UI.
- Track information requests (sent, answered, overdue), which is the "coordination friction" bottleneck in the brief.
- Scale: batch LLM calls and prompt caching of the playbook for thousands of documents.

**Q20. What was the hardest trade-off you made under time pressure?**
- Choosing depth on two features over breadth on six. A shallow demo of all six would look impressive and prove nothing. Two features with measured accuracy against an answer key prove the approach works and show how it would be governed.
- Second: environment constraints (no package installs) forced a zero-dependency build. I treated that as a feature, since locked-down deal environments are the norm, rather than spending the time fighting it.

---

## Honest caveats to state yourself (they earn credibility)
1. 100% recall/precision is on the pack the rules were built against, so expect lower on a new deal.
2. Confidence scores are heuristic, not calibrated probabilities.
3. Risk-score weights are judgement calls, transparent and adjustable.
4. The LLM layer is built but wasn't exercised in my environment (no API access). The demo runs on rules alone.
