import argparse
import json
import os
import re
from datetime import datetime, timezone

from crm_client import CRMClient


PROPOSALS_FILE = "data/proposals.json"
DECISIONS_FILE = "data/review_decisions.json"
LOG_FILE = "data/writeback_log.json"

BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"


def load_json(path, default=None):
    if default is None:
        default = {}

    if not os.path.exists(path):
        return default

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def normalize(value):
    if value is None:
        return ""

    value = str(value).lower().strip()
    value = value.replace("&", "and")
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_street(value):
    value = normalize(value)

    replacements = {
        " northwest ": " nw ",
        " southwest ": " sw ",
        " northeast ": " ne ",
        " southeast ": " se ",
        " west ": " w ",
        " east ": " e ",
        " north ": " n ",
        " south ": " s ",
        " street": " st",
        " road": " rd",
        " avenue": " ave",
        " boulevard": " blvd",
        " drive": " dr",
        " lane": " ln",
        " parkway": " pkwy",
        " pike": " pk",
    }

    value = f" {value} "

    for old, new in replacements.items():
        value = value.replace(old, new)

    return normalize(value)


def expected_care_type(web_value):
    value = normalize(web_value)

    mapping = {
        "short term rehabilitation and nursing":
            "Skilled Nursing",
        "memory support":
            "Memory Care",
        "assisted living":
            "Assisted Living",
    }

    # CRM care_type is singular.
    # For a new account, use the first authoritative
    # website offering as the primary CRM care type.
    if "|" in str(web_value):
        first = str(web_value).split("|")[0].strip()
        return mapping.get(
            normalize(first),
            first
        )

    return mapping.get(
        value,
        web_value
    )


def proposal_key(proposal):
    action = proposal.get("action")

    name = (
        proposal.get("website", {})
        .get("name", "")
    )

    return (
        proposal.get("account_id")
        or f"{action}:{name}"
    )


def same_current_facility(account, payload):
    return (
        account.get("parent_id")
        == BELLHAVEN_PARENT_ID
        and normalize(account.get("name"))
        == normalize(payload.get("name"))
        and normalize_street(
            account.get("billing_street")
        )
        == normalize_street(
            payload.get("billing_street")
        )
        and normalize(account.get("billing_city"))
        == normalize(payload.get("billing_city"))
        and normalize(account.get("billing_state"))
        == normalize(payload.get("billing_state"))
        and normalize(account.get("billing_zip"))
        == normalize(payload.get("billing_zip"))
    )


def find_existing_current(accounts, payload):
    for account in accounts:
        if same_current_facility(
            account,
            payload
        ):
            return account

    return None


def create_payload_from_website(web):
    return {
        "name": web["name"],
        "parent_id": BELLHAVEN_PARENT_ID,
        "billing_street": web["street"],
        "billing_city": web["city"],
        "billing_state": web["state"],
        "billing_zip": web["zip"],
        "care_type": expected_care_type(
            web.get("care_offerings", "")
        ),
    }


def record_log(logs, **entry):
    entry["timestamp"] = (
        datetime.now(timezone.utc)
        .isoformat()
    )

    logs.append(entry)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Apply approved Bellhaven CRM "
            "reconciliation decisions."
        )
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Actually modify the CRM. "
            "Without this flag the script "
            "only performs a dry run."
        )
    )

    args = parser.parse_args()

    execute = args.execute

    proposals = load_json(
        PROPOSALS_FILE,
        []
    )

    decisions = load_json(
        DECISIONS_FILE,
        {
            "proposals": {},
            "duplicates": {},
            "review_resolutions": {},
        }
    )

    client = CRMClient()

    # Fresh CRM snapshot for idempotency checks.
    accounts = client.list_accounts()

    logs = []

    print()
    print("=" * 70)

    if execute:
        print("MODE: EXECUTE — CRM CHANGES ENABLED")
    else:
        print("MODE: DRY RUN — CRM WILL NOT BE MODIFIED")

    print("=" * 70)

    # =================================================
    # Standard proposal decisions
    # =================================================

    for proposal in proposals:
        action = proposal.get("action")

        if action == "NO_CHANGE":
            continue

        key = proposal_key(proposal)

        decision = (
            decisions.get("proposals", {})
            .get(key, "Pending")
        )

        web = proposal.get("website", {})
        name = web.get("name", "Unknown")

        print()
        print("-" * 70)
        print(f"{name}")
        print(
            f"Proposal: {action} | "
            f"Decision: {decision}"
        )

        if decision != "Approve":
            print("SKIP — proposal not approved.")

            record_log(
                logs,
                facility=name,
                action=action,
                status="SKIPPED_NOT_APPROVED",
            )

            continue

        # =============================================
        # UPDATE
        # =============================================

        if action == "UPDATE":
            account_id = proposal["account_id"]
            changes = proposal.get(
                "changes",
                {}
            )

            if not changes:
                print(
                    "SKIP — no fields need changing."
                )
                continue

            current = client.get_account(
                account_id
            )

            needed = {}

            for field, value in changes.items():
                if str(
                    current.get(field, "")
                ) != str(value):
                    needed[field] = value

            if not needed:
                print(
                    "SKIP — CRM already contains "
                    "the approved values."
                )

                record_log(
                    logs,
                    facility=name,
                    action="UPDATE",
                    account_id=account_id,
                    status="ALREADY_CURRENT",
                )

                continue

            print(
                f"PATCH {account_id}"
            )
            print(
                json.dumps(
                    needed,
                    indent=2
                )
            )

            if execute:
                result = client.update_account(
                    account_id,
                    needed
                )

                print("SUCCESS")

                record_log(
                    logs,
                    facility=name,
                    action="UPDATE",
                    account_id=account_id,
                    status="UPDATED",
                    changes=needed,
                )

            else:
                record_log(
                    logs,
                    facility=name,
                    action="UPDATE",
                    account_id=account_id,
                    status="DRY_RUN",
                    changes=needed,
                )

        # =============================================
        # CREATE
        # =============================================

        elif action == "CREATE":
            payload = proposal.get(
                "changes"
            ) or create_payload_from_website(
                web
            )

            # Make sure care_type is singular.
            if isinstance(
                payload.get("care_type"),
                list
            ):
                payload["care_type"] = (
                    payload["care_type"][0]
                )

            existing = find_existing_current(
                accounts,
                payload
            )

            if existing:
                print(
                    "SKIP — current Bellhaven "
                    "account already exists:"
                )
                print(
                    existing["account_id"]
                )

                record_log(
                    logs,
                    facility=name,
                    action="CREATE",
                    account_id=(
                        existing["account_id"]
                    ),
                    status="ALREADY_EXISTS",
                )

                continue

            print("POST /accounts")
            print(
                json.dumps(
                    payload,
                    indent=2
                )
            )

            if execute:
                created = (
                    client.create_account(
                        payload
                    )
                )

                new_id = (
                    created.get("account_id")
                    or created.get("id")
                )

                if not new_id:
                    raise RuntimeError(
                        "Account was created but "
                        "the API response did not "
                        "contain an account ID."
                    )

                print(
                    f"SUCCESS — created {new_id}"
                )

                # Add to local snapshot so a later
                # operation in this same run cannot
                # create it again.
                accounts.append(created)

                record_log(
                    logs,
                    facility=name,
                    action="CREATE",
                    account_id=new_id,
                    status="CREATED",
                    payload=payload,
                )

            else:
                record_log(
                    logs,
                    facility=name,
                    action="CREATE",
                    status="DRY_RUN",
                    payload=payload,
                )

        # =============================================
        # CHOW CREATE
        # =============================================

        elif action == "CHOW_CREATE":
            old_id = proposal["account_id"]

            old_account = client.get_account(
                old_id
            )

            payload = proposal.get(
                "new_account"
            ) or create_payload_from_website(
                web
            )

            if isinstance(
                payload.get("care_type"),
                list
            ):
                payload["care_type"] = (
                    payload["care_type"][0]
                )

            # If historical account is already linked,
            # do not create another current account.
            existing_link = (
                old_account.get(
                    "chow_current_account"
                )
            )

            if existing_link:
                print(
                    "SKIP — historical account "
                    "already has chow_current_account:"
                )
                print(existing_link)

                record_log(
                    logs,
                    facility=name,
                    action="CHOW_CREATE",
                    account_id=old_id,
                    status="ALREADY_LINKED",
                    current_account=(
                        existing_link
                    ),
                )

                continue

            existing_current = (
                find_existing_current(
                    accounts,
                    payload
                )
            )

            if existing_current:
                new_id = (
                    existing_current[
                        "account_id"
                    ]
                )

                print(
                    "Current Bellhaven account "
                    "already exists:"
                )
                print(new_id)

            else:
                print(
                    "POST new current account:"
                )

                print(
                    json.dumps(
                        payload,
                        indent=2
                    )
                )

                if execute:
                    created = (
                        client.create_account(
                            payload
                        )
                    )

                    new_id = (
                        created.get(
                            "account_id"
                        )
                        or created.get("id")
                    )

                    if not new_id:
                        raise RuntimeError(
                            "CHOW current account "
                            "creation returned no ID."
                        )

                    accounts.append(created)

                    print(
                        "Created current account: "
                        f"{new_id}"
                    )

                else:
                    new_id = (
                        "<NEW_ACCOUNT_ID>"
                    )

            print(
                f"PATCH historical account "
                f"{old_id}"
            )

            print(
                json.dumps(
                    {
                        "chow_current_account":
                            new_id
                    },
                    indent=2
                )
            )

            if execute:
                client.update_account(
                    old_id,
                    {
                        "chow_current_account":
                            new_id
                    }
                )

                print(
                    "SUCCESS — CHOW linkage complete"
                )

                record_log(
                    logs,
                    facility=name,
                    action="CHOW_CREATE",
                    account_id=old_id,
                    current_account=new_id,
                    status="CHOW_COMPLETED",
                )

            else:
                record_log(
                    logs,
                    facility=name,
                    action="CHOW_CREATE",
                    account_id=old_id,
                    current_account=new_id,
                    status="DRY_RUN",
                    payload=payload,
                )

        # =============================================
        # REVIEW
        # =============================================

        elif action == "REVIEW":
            resolution_key = (
                f"review_resolution:{name}"
            )

            resolution = (
                decisions.get(
                    "review_resolutions",
                    {}
                ).get(
                    resolution_key,
                    {}
                )
            )

            resolution_type = (
                resolution.get(
                    "resolution",
                    "Pending"
                )
            )

            print(
                "Human resolution: "
                f"{resolution_type}"
            )

            # -----------------------------------------
            # Create new account
            # -----------------------------------------

            if (
                resolution_type
                == "Create a new Bellhaven account"
            ):
                payload = (
                    create_payload_from_website(
                        web
                    )
                )

                existing = (
                    find_existing_current(
                        accounts,
                        payload
                    )
                )

                if existing:
                    print(
                        "SKIP — current Bellhaven "
                        "account already exists:"
                    )
                    print(
                        existing["account_id"]
                    )

                    record_log(
                        logs,
                        facility=name,
                        action="REVIEW_CREATE",
                        account_id=(
                            existing[
                                "account_id"
                            ]
                        ),
                        status="ALREADY_EXISTS",
                    )

                    continue

                print(
                    "POST /accounts "
                    "(human-approved resolution)"
                )

                print(
                    json.dumps(
                        payload,
                        indent=2
                    )
                )

                if execute:
                    created = (
                        client.create_account(
                            payload
                        )
                    )

                    new_id = (
                        created.get(
                            "account_id"
                        )
                        or created.get("id")
                    )

                    if not new_id:
                        raise RuntimeError(
                            "Human-review account "
                            "creation returned no ID."
                        )

                    accounts.append(created)

                    print(
                        f"SUCCESS — created {new_id}"
                    )

                    record_log(
                        logs,
                        facility=name,
                        action="REVIEW_CREATE",
                        account_id=new_id,
                        status="CREATED",
                        payload=payload,
                    )

                else:
                    record_log(
                        logs,
                        facility=name,
                        action="REVIEW_CREATE",
                        status="DRY_RUN",
                        payload=payload,
                    )

            # -----------------------------------------
            # Existing account selected
            # -----------------------------------------

            elif (
                resolution_type
                == "Use an existing CRM account"
            ):
                account_id = resolution.get(
                    "selected_account_id"
                )

                if not account_id:
                    raise RuntimeError(
                        f"{name}: human resolution "
                        "selected existing account "
                        "but no account ID was saved."
                    )

                current = client.get_account(
                    account_id
                )

                changes = {
                    "name": web["name"],
                    "parent_id":
                        BELLHAVEN_PARENT_ID,
                    "billing_street":
                        web["street"],
                    "billing_city":
                        web["city"],
                    "billing_state":
                        web["state"],
                    "billing_zip":
                        web["zip"],
                }

                needed = {
                    field: value
                    for field, value
                    in changes.items()
                    if str(
                        current.get(field, "")
                    ) != str(value)
                }

                if not needed:
                    print(
                        "SKIP — selected account "
                        "already matches."
                    )
                    continue

                print(
                    f"PATCH {account_id}"
                )

                print(
                    json.dumps(
                        needed,
                        indent=2
                    )
                )

                if execute:
                    client.update_account(
                        account_id,
                        needed
                    )

                    print("SUCCESS")

                    record_log(
                        logs,
                        facility=name,
                        action="REVIEW_UPDATE",
                        account_id=account_id,
                        status="UPDATED",
                        changes=needed,
                    )

                else:
                    record_log(
                        logs,
                        facility=name,
                        action="REVIEW_UPDATE",
                        account_id=account_id,
                        status="DRY_RUN",
                        changes=needed,
                    )

            elif (
                resolution_type
                == (
                    "Handled separately / "
                    "no direct change"
                )
            ):
                print(
                    "SKIP — handled separately."
                )

            else:
                raise RuntimeError(
                    f"{name}: approved REVIEW "
                    "proposal has no completed "
                    "human resolution."
                )

    # =================================================
    # Duplicate decisions
    # =================================================

    print()
    print("=" * 70)
    print("DUPLICATE RESOLUTIONS")
    print("=" * 70)

    duplicate_decisions = decisions.get(
        "duplicates",
        {}
    )

    for group_key, duplicate in (
        duplicate_decisions.items()
    ):
        if (
            duplicate.get("decision")
            != "Approve duplicate"
        ):
            continue

        canonical = duplicate.get(
            "canonical_account"
        )

        duplicate_accounts = (
            duplicate.get(
                "duplicate_accounts",
                []
            )
        )

        for duplicate_id in (
            duplicate_accounts
        ):
            current = client.get_account(
                duplicate_id
            )

            if (
                current.get(
                    "duplicate_of_account"
                )
                == canonical
            ):
                print(
                    f"{duplicate_id}: already "
                    f"marked duplicate of "
                    f"{canonical}"
                )
                continue

            print(
                f"PATCH {duplicate_id}"
            )

            print(
                json.dumps(
                    {
                        "duplicate_of_account":
                            canonical
                    },
                    indent=2
                )
            )

            if execute:
                client.update_account(
                    duplicate_id,
                    {
                        "duplicate_of_account":
                            canonical
                    }
                )

                print("SUCCESS")

                record_log(
                    logs,
                    facility=group_key,
                    action="DUPLICATE",
                    account_id=duplicate_id,
                    canonical_account=canonical,
                    status="UPDATED",
                )

            else:
                record_log(
                    logs,
                    facility=group_key,
                    action="DUPLICATE",
                    account_id=duplicate_id,
                    canonical_account=canonical,
                    status="DRY_RUN",
                )

    # =================================================
    # Save local execution log
    # =================================================

    os.makedirs(
        "data",
        exist_ok=True
    )

    with open(
        LOG_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            logs,
            file,
            indent=2,
            ensure_ascii=False
        )

    print()
    print("=" * 70)

    if execute:
        print(
            "EXECUTION COMPLETE"
        )
    else:
        print(
            "DRY RUN COMPLETE — "
            "NO CRM DATA WAS MODIFIED"
        )

    print(
        f"Log saved to {LOG_FILE}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()