# Answer Key - Planted Issues (for accuracy testing)

Use this to score your tool: **14 planted issues** across 6 contracts. Bridgeway (contract 04) is a clean control, so any High flag on it is a false positive.

| ID | Contract | Clause | Page | Issue | Severity | Detail |
|---|---|---|---|---|---|---|
| P1 | 01_Customer_Harlow_Health_Trust_MSA.pdf | 6.2 | 2 | Change of Control termination right | High | Trust can terminate on 30 days' notice within 12 months of an un-consented CoC; no termination payment |
| P2 | 01_Customer_Harlow_Health_Trust_MSA.pdf | 4.4 | 1 | Persistent Failure termination right | High | 3+ KPI failures in rolling 6 months allows termination on 30 days' notice. Threshold already met per SLA data (4 failures Apr-Sep 2026) |
| P3 | 01_Customer_Harlow_Health_Trust_MSA.pdf | 1.1 | 1 | Data contradiction | Medium | Contract states c.GBP 28.0m annual charges; ledger shows GBP 32.4m FY2025 (variance GBP 4.4m, possibly ad hoc works - needs explanation) |
| P4 | 02_Customer_Meridian_Retail_Services_Agreement.pdf | 2.2 | 1 | Auto-renewal, short notice window | Medium | 12-month auto-renewal; 30 days' notice. Initial term ends 31 Dec 2026, so notice deadline is c.1 Dec 2026 (about 7 weeks from today) |
| P5 | 02_Customer_Meridian_Retail_Services_Agreement.pdf | 6.2 | 1 | Uncapped liability | High | Unlimited liability for all service-failure losses incl. loss of profit, stock and trading revenue |
| P6 | 02_Customer_Meridian_Retail_Services_Agreement.pdf | 4.1 | 1 | Most-favoured-customer pricing | High | Warranty to match the best price offered to any other customer, with refund |
| P7 | 02_Customer_Meridian_Retail_Services_Agreement.pdf | 2.3 | 1 | Fixed price, no indexation | Medium | Fee fixed through initial and renewal terms; supports low 8.2% margin vs 13.4% group |
| P8 | 03_Customer_Castlebrook_Council_Grounds_Waste.pdf | 5.2 | 1 | Termination for convenience | Medium | Council can exit on 3 months' notice, paying unamortised capital only |
| P9 | 05_Supplier_Apex_Fleet_Leasing_Agreement.pdf | 3.1 | 1 | Exclusivity | Medium | Exclusive leasing for all light commercial vehicles for 7 years, plus bar on third-party fleet arrangements (3.2) |
| P10 | 05_Supplier_Apex_Fleet_Leasing_Agreement.pdf | 4.1 | 1 | Take-or-pay minimum commitment | High | 400 vehicles paid for regardless of use. Q3 2026 usage 341 -> 59 idle, c.GBP 0.66m per year |
| P11 | 05_Supplier_Apex_Fleet_Leasing_Agreement.pdf | 4.2 | 1 | Uncapped price escalation | Medium | RPI + 2.0%, no cap |
| P12 | 05_Supplier_Apex_Fleet_Leasing_Agreement.pdf | 5.1 | 1 | Punitive early termination fee | High | 100% of remaining rentals for Minimum Fleet to Aug 2029 |
| P13 | 06_Employment_Operations_Director_Service_Agreement.pdf | 4.2 | 1 | Single-trigger CoC payment | High | 18 months' salary (GBP 315k) plus max pro-rated bonus, payable on completion regardless of continued employment. Deal cost to quantify as a price chip |
| P14 | 06_Employment_Operations_Director_Service_Agreement.pdf | 3.1 | 1 | Long notice period | Low | 12 months' notice (retention and cost implications; PILON c.GBP 210k) |

## Expected cross-workstream risk register (ranked)

| Rank | Customer / item | Why it ranks here | Streams linked |
|---|---|---|---|
| 1 | **Harlow Health NHS Trust** | 18.0% of revenue (GBP 32.4m) + CoC termination right (6.2) + Persistent Failure threshold already breached (4 KPI failures Apr-Sep 2026) + GBP 270k service credits in 12 months (5 failures) + contract/ledger value gap | Legal, commercial, operational, financial |
| 2 | **Meridian Retail Group** | 12.0% of revenue + uncapped liability + MFN clause + fixed price (8.2% margin) + renewal notice deadline c.1 Dec 2026 + one KPI failure (Aug 2026) | Legal, commercial, financial |
| 3 | **Apex Fleet Leasing** | Take-or-pay on 400 vehicles with utilisation falling to 85% + uncapped RPI+2% + 100% exit fee + exclusivity | Legal, operational, financial |
| 4 | **Operations Director CoC payment** | GBP 315k + max bonus on completion, single trigger; direct price-chip/SPA item | Legal, HR, financial |
| 5 | Castlebrook Council | 8.0% of revenue, termination for convenience on 3 months; otherwise clean, zero KPI failures | Legal, commercial |
| - | Bridgeway Logistics | Clean control. No flags expected (one minor KPI miss Feb 2026, no contractual consequence) | - |

## Key numbers to quote in the demo

- Harlow: 18.0% of FY2025 revenue (GBP 32.4m of GBP 180.0m)
- Harlow SLA: KPI failures in May, Jun, Aug, Sep 2026 (4 of last 6 months) vs. persistent-failure threshold of 3
- Harlow service credits over 12 months: GBP 270k (5 failures x GBP 54k; failures in Mar, May, Jun, Aug, Sep 2026)
- Top 2 customers: 30.0% of revenue
- Apex idle vehicles Q3 2026: 59 of 400, GBP 166k per quarter
- Exec CoC payment: 18 months x GBP 210k/12 = GBP 315k

## Scoring suggestion

Recall = issues found / 14. Precision = true flags / total flags. Report both, plus examples of any miss or false positive and what you would change. Showing this honestly is a governance point in itself.
