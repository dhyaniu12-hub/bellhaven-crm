import json
import re
from crm_client import CRMClient


def normalize(value):
    if not value:
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
    }

    value = f" {value} "

    for old, new in replacements.items():
        value = value.replace(old, new)

    return normalize(value)


def duplicate_key(account):
    """
    Facilities are considered exact duplicate candidates when
    normalized name + physical location agree.
    """
    return (
        normalize(account.get("name")),
        normalize_street(account.get("billing_street")),
        normalize(account.get("billing_city")),
        normalize(account.get("billing_state")),
        normalize(account.get("billing_zip")),
    )


def main():
    client = CRMClient()
    accounts = client.list_accounts()

    groups = {}

    for account in accounts:
        key = duplicate_key(account)

        # Ignore records missing important identifying information.
        if not all(key):
            continue

        groups.setdefault(key, []).append(account)

    duplicate_groups = [
        group
        for group in groups.values()
        if len(group) > 1
    ]

    print("\nDUPLICATE CANDIDATES")
    print("=" * 70)

    if not duplicate_groups:
        print("No exact duplicate candidates found.")
        return

    output = []

    for number, group in enumerate(duplicate_groups, start=1):
        print(f"\nDuplicate Group {number}")

        group_output = []

        for account in group:
            item = {
                "account_id": account.get("account_id"),
                "name": account.get("name"),
                "parent_id": account.get("parent_id"),
                "parent_name": account.get("parent_name"),
                "billing_street": account.get("billing_street"),
                "billing_city": account.get("billing_city"),
                "billing_state": account.get("billing_state"),
                "billing_zip": account.get("billing_zip"),
                "status": account.get("status"),
                "lifetime_revenue": account.get("lifetime_revenue"),
                "outstanding_ar": account.get("outstanding_ar"),
                "duplicate_of_account": account.get(
                    "duplicate_of_account"
                ),
                "created_by_candidate": account.get(
                    "created_by_candidate"
                ),
            }

            group_output.append(item)

            print(
                f"  {item['name']} "
                f"[{item['account_id']}]"
            )
            print(
                f"    Address: {item['billing_street']}, "
                f"{item['billing_city']}, "
                f"{item['billing_state']} "
                f"{item['billing_zip']}"
            )
            print(
                f"    Parent: {item['parent_name']}"
            )
            print(
                f"    Revenue: {item['lifetime_revenue']} | "
                f"AR: {item['outstanding_ar']} | "
                f"Status: {item['status']}"
            )

        output.append(group_output)

    with open(
        "data/duplicate_candidates.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        "\nSaved duplicate candidates to "
        "data/duplicate_candidates.json"
    )


if __name__ == "__main__":
    main()