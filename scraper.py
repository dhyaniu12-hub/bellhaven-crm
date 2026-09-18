import csv
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://analyst-assessment-production.up.railway.app"
COMMUNITIES_URL = f"{BASE_URL}/communities"

HEADERS = {
    "User-Agent": "BellhavenCRMReconciliation/1.0"
}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get_community_links():
    """Discover all community detail pages across pagination."""
    links = []
    page = 1

    while True:
        url = COMMUNITIES_URL if page == 1 else f"{COMMUNITIES_URL}?page={page}"

        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        page_links = []

        for link in soup.find_all("a", href=True):
            href = link["href"]

            if href.startswith("/communities/"):
                full_url = urljoin(BASE_URL, href)

                if full_url not in page_links:
                    page_links.append(full_url)

                if full_url not in links:
                    links.append(full_url)

        print(f"Page {page}: {len(page_links)} communities")

        next_link = soup.find(
            "a",
            string=lambda text: text and "Next" in text
        )

        if not next_link:
            break

        page += 1

    return links


def get_definition_value(soup, label):
    """
    Extract the <dd> associated with a <dt> label.

    Example:
        <dt>Address</dt>
        <dd>210 Orchard Lane<br>Maplewood, OH 44280</dd>
    """
    dt = soup.find(
        "dt",
        string=lambda text: text and clean(text).lower() == label.lower()
    )

    if not dt:
        return None

    return dt.find_next_sibling("dd")


def parse_location(location_line):
    """
    Parse:
        Maplewood, OH 44280
    """

    match = re.match(
        r"^(.+?),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$",
        clean(location_line)
    )

    if not match:
        return "", "", ""

    return (
        clean(match.group(1)),
        clean(match.group(2)),
        clean(match.group(3))
    )


def scrape_community(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    h1 = soup.find("h1")

    if not h1:
        raise ValueError("Community name not found")

    name = clean(h1.get_text(" ", strip=True))

    # ----- Address -----
    address_dd = get_definition_value(soup, "Address")

    if not address_dd:
        raise ValueError("Address not found")

    address_parts = [
        clean(part)
        for part in address_dd.stripped_strings
        if clean(part)
    ]

    street = address_parts[0] if address_parts else ""
    location_line = address_parts[1] if len(address_parts) > 1 else ""

    city, state, zip_code = parse_location(location_line)

    # ----- Care offerings -----
    care_dd = get_definition_value(soup, "Care Offerings")

    if care_dd:
        care_offerings = clean(
            " | ".join(care_dd.stripped_strings)
        )
    else:
        care_offerings = ""

    return {
        "name": name,
        "street": street,
        "city": city,
        "state": state,
        "zip": zip_code,
        "care_offerings": care_offerings,
        "source_url": url
    }


def save_csv(communities):
    os.makedirs("data", exist_ok=True)

    path = os.path.join("data", "website_communities.csv")

    fieldnames = [
        "name",
        "street",
        "city",
        "state",
        "zip",
        "care_offerings",
        "source_url"
    ]

    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(communities)

    return path


def main():
    links = get_community_links()

    print(f"\nFound {len(links)} unique communities.\n")

    communities = []

    for index, url in enumerate(links, start=1):
        try:
            community = scrape_community(url)
            communities.append(community)

            print(
                f"[{index:02}/{len(links)}] "
                f"{community['name']} | "
                f"{community['street']} | "
                f"{community['city']}, "
                f"{community['state']} "
                f"{community['zip']} | "
                f"{community['care_offerings']}"
            )

        except Exception as exc:
            print(f"[ERROR] {url}: {exc}")

    path = save_csv(communities)

    print("\n--------------------------------")
    print(f"Successfully scraped: {len(communities)}")
    print(f"Saved to: {path}")
    print("--------------------------------")


if __name__ == "__main__":
    main()