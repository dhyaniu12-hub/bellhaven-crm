import csv
import json
import os
import re

from rapidfuzz.fuzz import ratio
from crm_client import CRMClient


BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"


CARE_MAP = {
    "short term rehabilitation and nursing": "Skilled Nursing",
    "memory support": "Memory Care",
    "assisted living": "Assisted Living",
}


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


def load_website():
    with open(
        "data/website_communities.csv",
        newline="",
        encoding="utf-8"
    ) as file:
        return list(csv.DictReader(file))


def expected_care_type(web_value):
    value = normalize(web_value)

    # Website may list multiple offerings.
    if "|" in web_value:
        return [
            CARE_MAP.get(
                normalize(item),
                item.strip()
            )
            for item in web_value.split("|")
        ]

    return CARE_MAP.get(value, web_value)


def candidate_score(web, crm):
    score = 0
    evidence = []

    if normalize(web["zip"]) == normalize(
        crm.get("billing_zip")
    ):
        score += 30
        evidence.append("exact_zip")

    if normalize(web["state"]) == normalize(
        crm.get("billing_state")
    ):
        score += 5
        evidence.append("exact_state")

    if normalize(web["city"]) == normalize(
        crm.get("billing_city")
    ):
        score += 15
        evidence.append("exact_city")

    web_street = normalize_street(
        web["street"]
    )

    crm_street = normalize_street(
        crm.get("billing_street")
    )

    if (
        web_street
        and web_street == crm_street
    ):
        score += 35
        evidence.append("exact_street")

    web_name = normalize(web["name"])
    crm_name = normalize(crm.get("name"))

    name_score = ratio(
        web_name,
        crm_name
    )

    if name_score >= 95:
        score += 15
        evidence.append(
            "very_high_name_similarity"
        )

    elif name_score >= 80:
        score += 10
        evidence.append(
            "high_name_similarity"
        )

    elif name_score >= 65:
        score += 5
        evidence.append(
            "moderate_name_similarity"
        )

    return score, evidence


def exact_physical_location(web, crm):
    return (
        normalize_street(web["street"])
        == normalize_street(
            crm.get("billing_street")
        )
        and normalize(web["city"])
        == normalize(
            crm.get("billing_city")
        )
        and normalize(web["state"])
        == normalize(
            crm.get("billing_state")
        )
    )


def build_update_fields(web, crm):
    changes = {}

    if normalize(web["name"]) != normalize(
        crm.get("name")
    ):
        changes["name"] = web["name"]

    if normalize_street(
        web["street"]
    ) != normalize_street(
        crm.get("billing_street")
    ):
        changes["billing_street"] = (
            web["street"]
        )

    if normalize(web["city"]) != normalize(
        crm.get("billing_city")
    ):
        changes["billing_city"] = (
            web["city"]
        )

    if normalize(web["state"]) != normalize(
        crm.get("billing_state")
    ):
        changes["billing_state"] = (
            web["state"]
        )

    if normalize(web["zip"]) != normalize(
        crm.get("billing_zip")
    ):
        changes["billing_zip"] = web["zip"]

    return changes


def review_proposal(
    web,
    physical_candidates,
    reason
):
    return {
        "website": web,
        "action": "REVIEW",
        "confidence": "low",
        "reason": reason,
        "candidates": [
            {
                "account_id": (
                    item["account"].get(
                        "account_id"
                    )
                ),
                "name": (
                    item["account"].get(
                        "name"
                    )
                ),
                "street": (
                    item["account"].get(
                        "billing_street"
                    )
                ),
                "city": (
                    item["account"].get(
                        "billing_city"
                    )
                ),
                "parent": (
                    item["account"].get(
                        "parent_name"
                    )
                ),
                "score": item["score"],
                "evidence": item["evidence"],
            }
            for item in physical_candidates
        ]
    }


def make_proposal(web, crm_accounts):
    candidates = []

    for crm in crm_accounts:
        score, evidence = candidate_score(
            web,
            crm
        )

        if score > 0:
            candidates.append({
                "score": score,
                "evidence": evidence,
                "account": crm,
            })

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    # ------------------------------------------
    # No candidates
    # ------------------------------------------

    if not candidates:
        return {
            "website": web,
            "action": "CREATE",
            "confidence": "high",
            "reason": (
                "No plausible CRM account found."
            ),
            "changes": {
                "name": web["name"],
                "parent_id": (
                    BELLHAVEN_PARENT_ID
                ),
                "billing_street": (
                    web["street"]
                ),
                "billing_city": (
                    web["city"]
                ),
                "billing_state": (
                    web["state"]
                ),
                "billing_zip": web["zip"],
                "care_type": (
                    expected_care_type(
                        web["care_offerings"]
                    )
                ),
            }
        }

    best = candidates[0]
    crm = best["account"]

    # ------------------------------------------
    # Find all exact physical matches
    # ------------------------------------------

    physical_candidates = [
        item
        for item in candidates
        if exact_physical_location(
            web,
            item["account"]
        )
    ]

    # ------------------------------------------
    # Multiple accounts at same location
    # ------------------------------------------

    if len(physical_candidates) > 1:

        bellhaven_physical = [
            item
            for item in physical_candidates
            if (
                item["account"].get(
                    "parent_id"
                )
                == BELLHAVEN_PARENT_ID
            )
        ]

        # If exactly one is already Bellhaven,
        # use that record as the current facility.
        if len(bellhaven_physical) == 1:
            best = bellhaven_physical[0]
            crm = best["account"]

        # If there is no single Bellhaven record,
        # do not guess which account is current.
        else:
            return review_proposal(
                web,
                physical_candidates,
                (
                    "Multiple CRM accounts match "
                    "the same physical facility "
                    "and no single current "
                    "Bellhaven account can be "
                    "selected safely."
                )
            )

    # ------------------------------------------
    # Weak candidate
    # ------------------------------------------

    if best["score"] < 50:
        return {
            "website": web,
            "action": "CREATE",
            "confidence": "high",
            "reason": (
                "No sufficiently strong CRM "
                "candidate. Best candidate "
                f"scored {best['score']}."
            ),
            "changes": {
                "name": web["name"],
                "parent_id": (
                    BELLHAVEN_PARENT_ID
                ),
                "billing_street": (
                    web["street"]
                ),
                "billing_city": (
                    web["city"]
                ),
                "billing_state": (
                    web["state"]
                ),
                "billing_zip": web["zip"],
                "care_type": (
                    expected_care_type(
                        web["care_offerings"]
                    )
                ),
            },
            "best_candidate": {
                "account_id": (
                    crm.get("account_id")
                ),
                "name": crm.get("name"),
                "score": best["score"],
            }
        }

    physical_match = (
        exact_physical_location(
            web,
            crm
        )
    )

    # ------------------------------------------
    # Strong physical match
    # ------------------------------------------

    if physical_match:
        changes = build_update_fields(
            web,
            crm
        )

        wrong_parent = (
            crm.get("parent_id")
            != BELLHAVEN_PARENT_ID
        )

        if wrong_parent:
            revenue = float(
                crm.get(
                    "lifetime_revenue"
                )
                or 0
            )

            ar = float(
                crm.get(
                    "outstanding_ar"
                )
                or 0
            )

            # ----------------------------------
            # CHOW preservation rule
            # ----------------------------------

            if revenue > 0 and ar > 0:
                return {
                    "website": web,
                    "action": (
                        "CHOW_CREATE"
                    ),
                    "confidence": "high",
                    "account_id": (
                        crm.get(
                            "account_id"
                        )
                    ),
                    "reason": (
                        "Facility is now "
                        "Bellhaven, but "
                        "historical CRM account "
                        "has both lifetime "
                        "revenue and outstanding "
                        "AR. Preserve historical "
                        "account and create a new "
                        "current Bellhaven "
                        "account."
                    ),
                    "old_account": crm,
                    "new_account": {
                        "name": web["name"],
                        "parent_id": (
                            BELLHAVEN_PARENT_ID
                        ),
                        "billing_street": (
                            web["street"]
                        ),
                        "billing_city": (
                            web["city"]
                        ),
                        "billing_state": (
                            web["state"]
                        ),
                        "billing_zip": (
                            web["zip"]
                        ),
                        "care_type": (
                            expected_care_type(
                                web[
                                    "care_offerings"
                                ]
                            )
                        ),
                    }
                }

            changes["parent_id"] = (
                BELLHAVEN_PARENT_ID
            )

        if changes:
            return {
                "website": web,
                "action": "UPDATE",
                "confidence": "high",
                "account_id": (
                    crm.get("account_id")
                ),
                "crm_account": crm,
                "reason": (
                    "Existing CRM account "
                    "represents the same "
                    "physical facility."
                ),
                "changes": changes,
            }

        return {
            "website": web,
            "action": "NO_CHANGE",
            "confidence": "high",
            "account_id": (
                crm.get("account_id")
            ),
            "reason": (
                "CRM record already aligns "
                "with website."
            ),
        }

    # ------------------------------------------
    # Same name + city, address difference
    # ------------------------------------------

    if (
        normalize(web["name"])
        == normalize(
            crm.get("name")
        )
        and normalize(web["city"])
        == normalize(
            crm.get("billing_city")
        )
    ):
        changes = build_update_fields(
            web,
            crm
        )

        if (
            crm.get("parent_id")
            != BELLHAVEN_PARENT_ID
        ):
            revenue = float(
                crm.get(
                    "lifetime_revenue"
                )
                or 0
            )

            ar = float(
                crm.get(
                    "outstanding_ar"
                )
                or 0
            )

            if revenue > 0 and ar > 0:
                return {
                    "website": web,
                    "action": (
                        "CHOW_CREATE"
                    ),
                    "confidence": "high",
                    "account_id": (
                        crm.get(
                            "account_id"
                        )
                    ),
                    "reason": (
                        "Ownership change "
                        "requires historical "
                        "preservation."
                    ),
                    "old_account": crm,
                    "new_account": {
                        "name": web["name"],
                        "parent_id": (
                            BELLHAVEN_PARENT_ID
                        ),
                        "billing_street": (
                            web["street"]
                        ),
                        "billing_city": (
                            web["city"]
                        ),
                        "billing_state": (
                            web["state"]
                        ),
                        "billing_zip": (
                            web["zip"]
                        ),
                        "care_type": (
                            expected_care_type(
                                web[
                                    "care_offerings"
                                ]
                            )
                        ),
                    }
                }

            changes["parent_id"] = (
                BELLHAVEN_PARENT_ID
            )

        return {
            "website": web,
            "action": "UPDATE",
            "confidence": "high",
            "account_id": (
                crm.get("account_id")
            ),
            "crm_account": crm,
            "reason": (
                "Same facility name/city "
                "with authoritative website "
                "address differences."
            ),
            "changes": changes,
        }

    # ------------------------------------------
    # No exact identity match
    # ------------------------------------------

    exact_name_candidates = [
        item
        for item in candidates
        if (
            normalize(
                item["account"].get(
                    "name"
                )
            )
            == normalize(web["name"])
        )
    ]

    remaining_physical_candidates = [
        item
        for item in candidates
        if exact_physical_location(
            web,
            item["account"]
        )
    ]

    # Similar city/name evidence alone should
    # never overwrite an unrelated CRM account.
    if (
        not exact_name_candidates
        and not remaining_physical_candidates
    ):
        return {
            "website": web,
            "action": "CREATE",
            "confidence": "high",
            "reason": (
                "No CRM account matches the "
                "authoritative facility name "
                "or physical address. Similar "
                "records are preserved rather "
                "than overwritten."
            ),
            "changes": {
                "name": web["name"],
                "parent_id": (
                    BELLHAVEN_PARENT_ID
                ),
                "billing_street": (
                    web["street"]
                ),
                "billing_city": (
                    web["city"]
                ),
                "billing_state": (
                    web["state"]
                ),
                "billing_zip": web["zip"],
                "care_type": (
                    expected_care_type(
                        web["care_offerings"]
                    )
                ),
            },
            "best_candidate": {
                "account_id": (
                    crm.get("account_id")
                ),
                "name": crm.get("name"),
                "score": best["score"],
            }
        }

    # ------------------------------------------
    # Remaining ambiguity
    # ------------------------------------------

    return {
        "website": web,
        "action": "REVIEW",
        "confidence": "low",
        "reason": (
            "Candidate exists but identity "
            "is not safe to infer "
            "automatically."
        ),
        "candidates": [
            {
                "account_id": (
                    item["account"].get(
                        "account_id"
                    )
                ),
                "name": (
                    item["account"].get(
                        "name"
                    )
                ),
                "street": (
                    item["account"].get(
                        "billing_street"
                    )
                ),
                "city": (
                    item["account"].get(
                        "billing_city"
                    )
                ),
                "parent": (
                    item["account"].get(
                        "parent_name"
                    )
                ),
                "score": item["score"],
                "evidence": (
                    item["evidence"]
                ),
            }
            for item in candidates[:3]
        ]
    }


def main():
    website = load_website()

    client = CRMClient()
    crm_accounts = (
        client.list_accounts()
    )

    proposals = [
        make_proposal(
            web,
            crm_accounts
        )
        for web in website
    ]

    os.makedirs(
        "data",
        exist_ok=True
    )

    with open(
        "data/proposals.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            proposals,
            file,
            indent=2,
            ensure_ascii=False
        )

    counts = {}

    for proposal in proposals:
        action = proposal["action"]

        counts[action] = (
            counts.get(action, 0)
            + 1
        )

    print("\nPROPOSAL SUMMARY")
    print("=" * 50)

    for action, count in sorted(
        counts.items()
    ):
        print(
            f"{action:15} {count}"
        )

    print(
        "\nITEMS REQUIRING ACTION"
    )
    print("=" * 50)

    for proposal in proposals:
        if (
            proposal["action"]
            == "NO_CHANGE"
        ):
            continue

        web = proposal["website"]

        print(
            f"\n{web['name']}"
            f"\n  Action: "
            f"{proposal['action']}"
            f"\n  Confidence: "
            f"{proposal['confidence']}"
            f"\n  Reason: "
            f"{proposal['reason']}"
        )

        if proposal.get(
            "account_id"
        ):
            print(
                "  CRM ID: "
                f"{proposal['account_id']}"
            )

        if proposal.get("changes"):
            print(
                "  Changes: "
                f"{proposal['changes']}"
            )

        if proposal.get(
            "candidates"
        ):
            print("  Candidates:")

            for candidate in (
                proposal["candidates"]
            ):
                print(
                    "    - "
                    f"{candidate['name']} "
                    f"["
                    f"{candidate['account_id']}"
                    f"] score="
                    f"{candidate['score']}"
                )

    print(
        "\nSaved full proposal report "
        "to data/proposals.json"
    )


if __name__ == "__main__":
    main()