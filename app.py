import json
import os
import streamlit as st


PROPOSALS_FILE = "data/proposals.json"
DUPLICATES_FILE = "data/duplicate_candidates.json"
DECISIONS_FILE = "data/review_decisions.json"


st.set_page_config(
    page_title="Bellhaven CRM Reconciliation",
    page_icon="🏥",
    layout="wide"
)


def load_json(path, default=None):
    if default is None:
        default = []

    if not os.path.exists(path):
        return default

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


def load_decisions():
    return load_json(
        DECISIONS_FILE,
        {
            "proposals": {},
            "duplicates": {}
        }
    )


def save_decisions(decisions):
    os.makedirs(
        "data",
        exist_ok=True
    )

    with open(
        DECISIONS_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            decisions,
            file,
            indent=2,
            ensure_ascii=False
        )


proposals = load_json(
    PROPOSALS_FILE
)

duplicates = load_json(
    DUPLICATES_FILE
)

decisions = load_decisions()


# Make sure older decision files still have
# the expected sections.
decisions.setdefault(
    "proposals",
    {}
)

decisions.setdefault(
    "duplicates",
    {}
)

decisions.setdefault(
    "review_resolutions",
    {}
)


st.title(
    "Bellhaven CRM Reconciliation"
)

st.write(
    "Review proposed CRM corrections generated "
    "from the authoritative Bellhaven community "
    "website."
)

st.info(
    "This review screen does not modify the CRM. "
    "Decisions are saved locally and applied "
    "separately."
)


# ==================================================
# Summary
# ==================================================

st.header("Summary")

counts = {}

for proposal in proposals:
    action = proposal.get(
        "action",
        "UNKNOWN"
    )

    counts[action] = (
        counts.get(action, 0)
        + 1
    )


columns = st.columns(5)

summary_order = [
    "NO_CHANGE",
    "UPDATE",
    "CREATE",
    "CHOW_CREATE",
    "REVIEW"
]


for column, action in zip(
    columns,
    summary_order
):
    column.metric(
        action.replace(
            "_",
            " "
        ).title(),
        counts.get(action, 0)
    )


# ==================================================
# Proposed changes
# ==================================================

st.header(
    "Proposed CRM Changes"
)

actionable = [
    proposal
    for proposal in proposals
    if proposal.get("action")
    != "NO_CHANGE"
]


for index, proposal in enumerate(
    actionable
):
    web = proposal.get(
        "website",
        {}
    )

    name = web.get(
        "name",
        "Unknown Community"
    )

    action = proposal.get(
        "action",
        "UNKNOWN"
    )

    key = (
        proposal.get("account_id")
        or f"{action}:{name}"
    )

    existing = (
        decisions["proposals"].get(
            key,
            "Pending"
        )
    )

    with st.expander(
        f"{action} — {name}",
        expanded=(action == "REVIEW")
    ):

        left, right = st.columns(2)

        # ------------------------------------------
        # Website side
        # ------------------------------------------

        with left:
            st.subheader(
                "Authoritative Website"
            )

            st.write(
                f"**Name:** {name}"
            )

            st.write(
                "**Address:** "
                f"{web.get('street', '')}, "
                f"{web.get('city', '')}, "
                f"{web.get('state', '')} "
                f"{web.get('zip', '')}"
            )

            st.write(
                "**Care offerings:** "
                f"{web.get('care_offerings', '')}"
            )

            if web.get("source_url"):
                st.write(
                    "**Source:** "
                    f"{web['source_url']}"
                )

        # ------------------------------------------
        # Proposal side
        # ------------------------------------------

        with right:
            st.subheader(
                "Proposed Action"
            )

            st.write(
                f"**Action:** `{action}`"
            )

            st.write(
                "**Confidence:** "
                f"{proposal.get('confidence', '')}"
            )

            st.write(
                "**Reason:** "
                f"{proposal.get('reason', '')}"
            )

            if proposal.get(
                "account_id"
            ):
                st.write(
                    "**Existing CRM account:** "
                    f"`{proposal['account_id']}`"
                )

        # ------------------------------------------
        # Standard field changes
        # ------------------------------------------

        if proposal.get("changes"):
            st.subheader(
                "Fields to Change"
            )

            st.json(
                proposal["changes"]
            )

        # ------------------------------------------
        # CHOW
        # ------------------------------------------

        if proposal.get(
            "new_account"
        ):
            st.subheader(
                "New Current Account"
            )

            st.json(
                proposal["new_account"]
            )

            st.warning(
                "CHOW rule: preserve the historical "
                "account. After creating the new "
                "Bellhaven account, the old account "
                "must reference the new account "
                "through chow_current_account."
            )

        # ------------------------------------------
        # Candidate display
        # ------------------------------------------

        if proposal.get(
            "candidates"
        ):
            st.subheader(
                "Possible CRM Candidates"
            )

            for candidate in (
                proposal["candidates"]
            ):
                st.write(
                    f"**{candidate.get('name')}** — "
                    f"`{candidate.get('account_id')}`"
                )

                st.write(
                    f"{candidate.get('street', '')}, "
                    f"{candidate.get('city', '')}"
                )

                st.write(
                    "Parent: "
                    f"{candidate.get('parent', '')}"
                )

                st.write(
                    "Match score: "
                    f"{candidate.get('score', '')}"
                )

                st.divider()

        # ==========================================
        # Special human resolution for REVIEW
        # ==========================================

        if (
            action == "REVIEW"
            and proposal.get("candidates")
        ):
            st.subheader(
                "Human Resolution"
            )

            st.write(
                "The automated matcher intentionally "
                "did not select an account. Choose "
                "how this ambiguity should be "
                "resolved."
            )

            resolution_key = (
                f"review_resolution:{name}"
            )

            existing_resolution = (
                decisions[
                    "review_resolutions"
                ].get(
                    resolution_key,
                    {}
                )
            )

            resolution_options = [
                "Pending",
                "Use an existing CRM account",
                "Create a new Bellhaven account",
                "Handled separately / no direct change"
            ]

            old_resolution = (
                existing_resolution.get(
                    "resolution",
                    "Pending"
                )
            )

            if (
                old_resolution
                not in resolution_options
            ):
                old_resolution = "Pending"

            resolution = st.selectbox(
                "Resolution",
                resolution_options,
                index=resolution_options.index(
                    old_resolution
                ),
                key=(
                    f"resolution_"
                    f"{index}_{key}"
                )
            )

            selected_account = None

            if (
                resolution
                == "Use an existing CRM account"
            ):
                candidate_map = {
                    (
                        f"{candidate.get('name')} — "
                        f"{candidate.get('account_id')}"
                    ):
                    candidate.get("account_id")
                    for candidate
                    in proposal["candidates"]
                }

                candidate_labels = list(
                    candidate_map.keys()
                )

                old_account = (
                    existing_resolution.get(
                        "selected_account_id"
                    )
                )

                selected_index = 0

                if old_account:
                    for candidate_index, label in (
                        enumerate(candidate_labels)
                    ):
                        if (
                            candidate_map[label]
                            == old_account
                        ):
                            selected_index = (
                                candidate_index
                            )
                            break

                selected_label = st.selectbox(
                    "CRM account to use",
                    candidate_labels,
                    index=selected_index,
                    key=(
                        f"candidate_"
                        f"{index}_{key}"
                    )
                )

                selected_account = (
                    candidate_map[
                        selected_label
                    ]
                )

                st.info(
                    "Because the selected account "
                    "has no historical revenue/AR "
                    "preservation requirement, the "
                    "approved write-back can rename "
                    "and re-parent that account to "
                    "Bellhaven."
                )

            elif (
                resolution
                == "Create a new Bellhaven account"
            ):
                st.info(
                    "A new current Bellhaven account "
                    "will be proposed using the "
                    "authoritative website name, "
                    "address, and care offering. "
                    "Existing ambiguous CRM records "
                    "will be preserved."
                )

            elif (
                resolution
                == (
                    "Handled separately / "
                    "no direct change"
                )
            ):
                st.info(
                    "Use this when another workflow, "
                    "such as duplicate resolution, "
                    "handles the issue."
                )

            resolution_note = st.text_input(
                "Resolution note (optional)",
                value=existing_resolution.get(
                    "note",
                    ""
                ),
                key=(
                    f"resolution_note_"
                    f"{index}_{key}"
                )
            )

            if st.button(
                "Save human resolution",
                key=(
                    f"save_resolution_"
                    f"{index}_{key}"
                )
            ):
                decisions[
                    "review_resolutions"
                ][resolution_key] = {
                    "resolution": resolution,
                    "selected_account_id": (
                        selected_account
                    ),
                    "note": resolution_note
                }

                save_decisions(
                    decisions
                )

                st.success(
                    "Human resolution saved."
                )

            st.divider()

        # ==========================================
        # Standard approval
        # ==========================================

        choice_options = [
            "Pending",
            "Approve",
            "Reject"
        ]

        default_index = (
            choice_options.index(existing)
            if existing in choice_options
            else 0
        )

        choice = st.radio(
            "Review decision",
            choice_options,
            index=default_index,
            horizontal=True,
            key=(
                f"decision_"
                f"{index}_{key}"
            )
        )

        note = st.text_input(
            "Reviewer note (optional)",
            value=(
                decisions["proposals"]
                .get(
                    f"{key}:note",
                    ""
                )
            ),
            key=(
                f"note_{index}_{key}"
            )
        )

        if st.button(
            "Save decision",
            key=(
                f"save_{index}_{key}"
            )
        ):
            decisions[
                "proposals"
            ][key] = choice

            decisions[
                "proposals"
            ][f"{key}:note"] = note

            save_decisions(
                decisions
            )

            st.success(
                "Decision saved."
            )


# ==================================================
# Duplicate review
# ==================================================

st.header(
    "Duplicate Candidates"
)

if not duplicates:
    st.write(
        "No exact duplicate candidates detected."
    )


for group_index, group in enumerate(
    duplicates
):
    if len(group) < 2:
        continue

    title = (
        group[0].get("name")
        or (
            f"Duplicate Group "
            f"{group_index + 1}"
        )
    )

    with st.expander(
        f"Possible Duplicate — {title}",
        expanded=True
    ):
        st.write(
            "These CRM records normalize to the "
            "same facility name and physical "
            "address."
        )

        for account in group:
            st.write(
                f"### {account.get('name')}"
            )

            st.write(
                "Account ID: "
                f"`{account.get('account_id')}`"
            )

            st.write(
                "Address: "
                f"{account.get('billing_street')}, "
                f"{account.get('billing_city')}, "
                f"{account.get('billing_state')} "
                f"{account.get('billing_zip')}"
            )

            st.write(
                "Revenue: "
                f"${account.get('lifetime_revenue', 0):,.2f}"
            )

            st.write(
                "Outstanding AR: "
                f"${account.get('outstanding_ar', 0):,.2f}"
            )

            st.divider()

        canonical_options = [
            account["account_id"]
            for account in group
        ]

        group_key = (
            f"duplicate_group_"
            f"{group_index}"
        )

        existing_duplicate = (
            decisions["duplicates"].get(
                group_key,
                {}
            )
        )

        existing_canonical = (
            existing_duplicate.get(
                "canonical_account"
            )
        )

        default_index = 0

        if (
            existing_canonical
            in canonical_options
        ):
            default_index = (
                canonical_options.index(
                    existing_canonical
                )
            )

        canonical = st.selectbox(
            "Canonical account to retain",
            canonical_options,
            index=default_index,
            key=(
                f"canonical_"
                f"{group_index}"
            )
        )

        duplicate_options = [
            "Pending",
            "Approve duplicate",
            "Reject duplicate"
        ]

        existing_duplicate_decision = (
            existing_duplicate.get(
                "decision",
                "Pending"
            )
        )

        if (
            existing_duplicate_decision
            not in duplicate_options
        ):
            existing_duplicate_decision = (
                "Pending"
            )

        duplicate_decision = st.radio(
            "Duplicate decision",
            duplicate_options,
            index=(
                duplicate_options.index(
                    existing_duplicate_decision
                )
            ),
            horizontal=True,
            key=(
                f"duplicate_decision_"
                f"{group_index}"
            )
        )

        if st.button(
            "Save duplicate decision",
            key=(
                f"save_duplicate_"
                f"{group_index}"
            )
        ):
            decisions[
                "duplicates"
            ][group_key] = {
                "decision": (
                    duplicate_decision
                ),
                "canonical_account": (
                    canonical
                ),
                "duplicate_accounts": [
                    account["account_id"]
                    for account in group
                    if (
                        account["account_id"]
                        != canonical
                    )
                ]
            }

            save_decisions(
                decisions
            )

            st.success(
                "Duplicate review "
                "decision saved."
            )


# ==================================================
# Review status
# ==================================================

st.header(
    "Review Status"
)

approved = 0
rejected = 0
pending = 0


for proposal in actionable:
    key = (
        proposal.get("account_id")
        or (
            f"{proposal.get('action')}:"
            f"{proposal.get('website', {}).get('name')}"
        )
    )

    decision = (
        decisions["proposals"].get(
            key,
            "Pending"
        )
    )

    if decision == "Approve":
        approved += 1

    elif decision == "Reject":
        rejected += 1

    else:
        pending += 1


c1, c2, c3 = st.columns(3)

c1.metric(
    "Approved",
    approved
)

c2.metric(
    "Rejected",
    rejected
)

c3.metric(
    "Pending",
    pending
)