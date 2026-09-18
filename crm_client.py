import os
import requests

BASE_URL = "https://analyst-assessment-production.up.railway.app/api/v1"


class CRMClient:
    def __init__(self, token=None):
        self.token = token or os.getenv("CRM_API_TOKEN")

        if not self.token:
            raise ValueError(
                "CRM_API_TOKEN is missing. "
                "Set it as an environment variable before running."
            )

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _request(self, method, endpoint, **kwargs):
        response = self.session.request(
            method,
            f"{BASE_URL}{endpoint}",
            timeout=30,
            **kwargs
        )

        response.raise_for_status()

        if not response.content:
            return None

        return response.json()

    def get_me(self):
        return self._request("GET", "/me")

    def list_accounts(self, **filters):
        """
        Retrieve accounts with automatic pagination.
        Supports API filters such as:
        q, city, state, zip, street, parent_id
        """
        accounts = []
        page = 1

        while True:
            params = {
                **filters,
                "page": page,
                "page_size": 50
            }

            payload = self._request(
                "GET",
                "/accounts",
                params=params
            )

            data = payload.get("data", [])
            accounts.extend(data)

            total = payload.get("total", len(accounts))

            if len(accounts) >= total or not data:
                break

            page += 1

        return accounts

    def get_account(self, account_id):
        return self._request(
            "GET",
            f"/accounts/{account_id}"
        )

    def create_account(self, account_data):
        return self._request(
            "POST",
            "/accounts",
            json=account_data
        )

    def update_account(self, account_id, changes):
        return self._request(
            "PATCH",
            f"/accounts/{account_id}",
            json=changes
        )


if __name__ == "__main__":
    client = CRMClient()

    me = client.get_me()
    print("Authentication OK:")
    print(me)

    accounts = client.list_accounts()

    print(f"\nTotal CRM accounts retrieved: {len(accounts)}")