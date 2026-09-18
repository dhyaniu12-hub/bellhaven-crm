import csv
import re
from rapidfuzz.fuzz import ratio
from crm_client import CRMClient


BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"


def normalize(value):
    if not value:
        return ""

    value = value.lower().strip()
    value = value.replace("&", "and")
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_street(value):
    value = normalize(value)

    replacements = {
        " street": " st",
        " road": " rd",
        " avenue": " ave",
        " boulevard": " blvd",
        " drive": " dr",
        " lane": " ln",
        " highway": " hwy",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    return value


def load_website():
    with open(
        "data/website_communities.csv",
        newline="",
        encoding="utf-8"
    ) as file:
        return list(csv.DictReader(file))


def score_match(web, crm):
    """
    Produce an explainable matching score.

    Address/ZIP evidence is intentionally weighted heavily because
    facility names can change while physical locations remain stable.
    """

    score = 0
    evidence = []

    web_zip = normalize(web["zip"])
    crm_zip = normalize(crm.get("billing_zip"))

    web_city = normalize(web["city"])
    crm_city = normalize(crm.get("billing_city"))

    web_state = normalize(web["state"])
    crm_state = normalize(crm.get("billing_state"))

    web_street = normalize_street(web["street"])
    crm_street = normalize_street(crm.get("billing_street"))

    web_name = normalize(web["name"])
    crm_name = normalize(crm.get("name"))

    # ZIP
    if web_zip and web_zip == crm_zip:
        score += 30
        evidence.append("exact ZIP")

    # State
    if web_state and web_state == crm_state:
        score += 5
        evidence.append("exact state")

    # City
    if web_city and web_city == crm_city:
        score += 15
        evidence.append("exact city")

    # Street
    if web_street and web_street == crm_street:
        score += 35
        evidence.append("exact normalized street")
    elif web_street and crm_street:
        street_similarity = ratio(web_street, crm_street)

        if street_similarity >= 90:
            score += 25
            evidence.append(
                f"street similarity {street_similarity:.0f}%"
            )

    # Name
    if web_name and crm_name:
        name_similarity = ratio(web_name, crm_name)

        if name_similarity >= 95:
            score += 15
            evidence.append(
                f"name similarity {name_similarity:.0f}%"
            )
        elif name_similarity >= 80:
            score += 10
            evidence.append(
                f"name similarity {name_similarity:.0f}%"
            )
        elif name_similarity >= 65:
            score += 5
            evidence.append(
                f"name similarity {name_similarity:.0f}%"
            )

    return score, evidence


def classify_match(web, crm, score, evidence):
    """
    Describe what appears to be wrong without modifying CRM.
    """

    issues = []

    if normalize(web["name"]) != normalize(crm.get("name")):
        issues.append("NAME_MISMATCH")

    if normalize_street(web["street"]) != normalize_street(
        crm.get("billing_street")
    ):
        issues.append("STREET_MISMATCH")

    if normalize(web["city"]) != normalize(crm.get("billing_city")):
        issues.append("CITY_MISMATCH")

    if normalize(web["state"]) != normalize(crm.get("billing_state")):
        issues.append("STATE_MISMATCH")

    if normalize(web["zip"]) != normalize(crm.get("billing_zip")):
        issues.append("ZIP_MISMATCH")

    if crm.get("parent_id") != BELLHAVEN_PARENT_ID:
        issues.append("WRONG_PARENT")

    return {
        "website_name": web["name"],
        "website_address": (
            f"{web['street']}, {web['city']}, "
            f"{web['state']} {web['zip']}"
        ),
        "crm_account_id": crm.get("account_id"),
        "crm_name": crm.get("name"),
        "crm_parent": crm.get("parent_name"),
        "score": score,
        "evidence": ", ".join(evidence),
        "issues": ", ".join(issues) if issues else "MATCH"
    }


def main():
    website = load_website()

    client = CRMClient()
    crm_accounts = client.list_accounts()

    print(f"Website communities: {len(website)}")
    print(f"CRM accounts: {len(crm_accounts)}")
    print("=" * 100)

    results = []

    for web in website:
        candidates = []

        for crm in crm_accounts:
            score, evidence = score_match(web, crm)

            if score > 0:
                candidates.append(
                    (score, crm, evidence)
                )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True
        )

        if not candidates:
            print(f"\n{web['name']}")
            print("  -> NO CRM CANDIDATE")
            continue

        best_score, best_crm, evidence = candidates[0]

        result = classify_match(
            web,
            best_crm,
            best_score,
            evidence
        )

        results.append(result)

        print(f"\n{web['name']}")
        print(
            f"  -> {best_crm.get('name')} "
            f"[{best_crm.get('account_id')}]"
        )
        print(
            f"  -> Parent: {best_crm.get('parent_name')}"
        )
        print(f"  -> Score: {best_score}")
        print(f"  -> Evidence: {', '.join(evidence)}")
        print(f"  -> Status: {result['issues']}")

        # Show close alternatives — important for detecting duplicates.
        if len(candidates) > 1:
            second_score, second_crm, _ = candidates[1]

            if second_score >= 70:
                print(
                    f"  -> ALSO POSSIBLE: "
                    f"{second_crm.get('name')} "
                    f"[{second_crm.get('account_id')}] "
                    f"score={second_score}"
                )


if __name__ == "__main__":
    main()