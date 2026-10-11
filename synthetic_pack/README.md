# Synthetic Data Pack - Northgate Facilities Services (fictional target, c.GBP 180m revenue)

All names, figures and documents are invented for prototype demonstration. Not real agreements.

## Contents
- contracts/ - 6 text-based PDFs (4 customer, 1 supplier, 1 employment); Bridgeway is a clean control
- data/customer_revenue_FY2023-2025.csv - revenue, % share and margin by customer (joins to contracts via contract_file)
- data/sla_performance_monthly.csv - 12 months of KPI performance and service credits for the 4 customers
- data/fleet_utilisation_quarterly.csv - Apex vehicle usage vs. 400-vehicle take-or-pay commitment
- data/clause_playbook.csv - 12 clause rules your tool checks against (what counts as non-standard)
- ANSWER_KEY.md - 14 planted issues with clause and page, expected risk-register ranking, and key numbers

## Join keys
customer name <-> contract party; contract_file column links revenue rows to PDFs.
