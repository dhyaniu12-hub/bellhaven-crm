# Bellhaven Senior Living CRM Reconciliation

An end-to-end reconciliation system that compares Bellhaven Senior Living's authoritative website community data against a CRM sandbox, identifies discrepancies and duplicates, routes ambiguous changes through human review, and safely writes approved corrections back to the CRM.

## Overview

The Bellhaven website is treated as the authoritative source for current communities and care offerings.

The pipeline:

1. Scrapes all Bellhaven community locations from the website.
2. Retrieves CRM accounts through the REST API.
3. Normalizes and matches website communities to CRM accounts.
4. Generates explainable reconciliation proposals.
5. Detects potential duplicate CRM records.
6. Presents proposed changes for human review in Streamlit.
7. Applies only approved changes through a separate write-back process.
8. Supports safe reruns through idempotency checks.
9. Can run the reconciliation pipeline daily through GitHub Actions.

## Architecture

```text
Bellhaven Website
       |
       v
   scraper.py
       |
       v
website_communities.csv
       |
       +----------------+
       |                |
       v                v
 proposals.py      duplicates.py
       |                |
       +-------+--------+
               |
               v
            app.py
       Human Review UI
               |
               v
      review_decisions.json
               |
               v
       apply_changes.py
               |
               v
          CRM REST API
```

## Matching Strategy

Matching does not rely on facility name alone.

Candidate accounts are evaluated using normalized:

- Facility name
- Street address
- City
- State
- ZIP code
- Parent relationship
- Care offering

Address normalization handles common formatting differences such as `Street` vs `St`, `Northwest` vs `NW`, and `Pike` vs `Pk`.

Ambiguous matches are sent to human review rather than being automatically changed.

## Care-Type Mapping

Website terminology is mapped to the CRM taxonomy:

| Website | CRM |
|---|---|
| Short-Term Rehabilitation & Nursing | Skilled Nursing |
| Memory Support | Memory Care |
| Assisted Living | Assisted Living |

The website can contain multiple care offerings while the CRM exposes a singular `care_type`. For new records requiring a singular value, the first authoritative website offering is treated as the primary CRM care type.

## Change of Ownership (CHOW)

Parent changes require special handling because historical financial records must be preserved.

When a facility is associated with the wrong parent:

- If both `lifetime_revenue > 0` and `outstanding_ar > 0`, the historical account is not re-parented.
- A new current facility account is created under Bellhaven.
- The historical account is linked to the new account using `chow_current_account`.
- Otherwise, the existing account can be updated directly when appropriate.

This preserves historical revenue and receivable relationships while establishing the correct current ownership record.

## Duplicate Handling

Potential duplicates are identified using normalized facility identity and physical location.

Duplicates are not automatically deleted. They are presented for human review, where a canonical account is selected. Approved duplicate records are linked using `duplicate_of_account`.

This preserves CRM history while explicitly identifying the canonical current record.

## Human Review

Run the Streamlit application:

```bash
streamlit run app.py
```

The application allows a reviewer to:

- Inspect proposed changes
- Review matching evidence
- Approve or reject changes
- Resolve ambiguous matches
- Select canonical duplicate records

The review application itself does not modify CRM data.

## Safe CRM Write-Back

Write-back is intentionally separated from proposal generation and human review.

Dry run:

```bash
python apply_changes.py
```

The default behavior does not modify the CRM.

Actual approved write-back requires the explicit flag:

```bash
python apply_changes.py --execute
```

Only approved decisions are applied.

The writer includes idempotency checks so completed updates, existing current accounts, completed CHOW links, and resolved duplicates are skipped on subsequent executions.

## Daily Execution

`run_pipeline.py` executes the read-only reconciliation workflow:

```bash
python run_pipeline.py
```

It:

1. Refreshes website data.
2. Regenerates reconciliation proposals.
3. Detects duplicate candidates.

It intentionally does not automatically write changes to the CRM because CRM mutations remain behind the human-approval gate.

A GitHub Actions workflow in `.github/workflows/daily.yml` schedules this pipeline daily and also supports manual execution.

## Setup

Create a virtual environment and install dependencies:

```bash
pip install -r requirements.txt
```

Set the CRM API token as an environment variable.

PowerShell:

```powershell
$env:CRM_API_TOKEN="YOUR_TOKEN"
```

The token must not be committed to source control.

## Tests

Run:

```bash
python -m pytest -q
```

Tests cover normalization, address equivalence, care-type mapping, parent validation, and current-facility identity behavior.

## Project Structure

```text
bellhaven-crm/
├── .github/
│   └── workflows/
│       └── daily.yml
├── data/
├── tests/
│   └── test_reconciliation.py
├── app.py
├── apply_changes.py
├── crm_client.py
├── duplicates.py
├── matcher.py
├── proposals.py
├── run_pipeline.py
├── scraper.py
├── requirements.txt
├── .gitignore
└── README.md
```

## Safety and Design Decisions

The system is designed around several safeguards:

- Website data is treated as authoritative for current Bellhaven communities.
- Matching uses multiple identity signals rather than name alone.
- Ambiguous records require human resolution.
- CRM write-back is separated from reconciliation.
- Dry-run is the default behavior.
- Execution requires an explicit `--execute` flag.
- Historical CHOW accounts are preserved when financial history and receivables exist.
- Duplicate records are linked rather than deleted.
- Idempotency checks prevent repeated creation or modification during reruns.
- API credentials are supplied through environment variables and excluded from source control.