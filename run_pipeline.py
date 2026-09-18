import subprocess
import sys


def run_step(script, description):
    print("\n" + "=" * 70)
    print(description)
    print("=" * 70)

    result = subprocess.run(
        [sys.executable, script],
        check=False
    )

    if result.returncode != 0:
        print(f"\nFAILED: {description}")
        sys.exit(result.returncode)

    print(f"\nCOMPLETED: {description}")


def main():
    print("=" * 70)
    print("BELLHAVEN DAILY RECONCILIATION PIPELINE")
    print("=" * 70)

    run_step(
        "scraper.py",
        "Step 1: Scrape authoritative Bellhaven website"
    )

    run_step(
        "proposals.py",
        "Step 2: Match website communities to CRM and generate proposals"
    )

    run_step(
        "duplicates.py",
        "Step 3: Detect potential duplicate CRM accounts"
    )

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print(
        "Proposals are ready for human review. "
        "No CRM write-back was performed."
    )


if __name__ == "__main__":
    main()