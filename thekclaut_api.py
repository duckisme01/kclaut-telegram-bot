import requests
from typing import Dict, List, Optional

API_URL = "https://thekclaut.com/api/v2"

class TheKClautAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "TheKClautTelegramBot/1.0"})
        # cache
        self._services_cache = None
        self._services_cache_time = 0

    def _post(self, payload: dict):
        data = {"key": self.api_key, **payload}
        resp = self.session.post(API_URL, data=data, timeout=20)
        resp.raise_for_status()
        try:
            j = resp.json()
        except:
            raise Exception(f"Invalid JSON response: {resp.text[:300]}")
        # Perfect Panel returns {"error": "..."} on failure
        if isinstance(j, dict) and "error" in j:
            raise Exception(j["error"])
        return j

    def get_balance(self):
        return self._post({"action": "balance"})

    def get_services(self, force_refresh=False):
        import time
        # cache 5 minutes
        if not force_refresh and self._services_cache and (time.time() - self._services_cache_time < 300):
            return self._services_cache
        services = self._post({"action": "services"})
        if not isinstance(services, list):
            raise Exception(f"Unexpected services response: {services}")
        self._services_cache = services
        self._services_cache_time = time.time()
        return services

    def get_categories(self):
        services = self.get_services()
        cats = {}
        for s in services:
            cat = s.get("category", "Other")
            cats.setdefault(cat, []).append(s)
        return cats

    def create_order(self, service: int, link: str, quantity: int = None, **kwargs):
        payload = {"action": "add", "service": str(service), "link": link}
        if quantity is not None:
            payload["quantity"] = str(quantity)
        payload.update({k: str(v) for k, v in kwargs.items() if v is not None})
        return self._post(payload)

    def get_status(self, order_id: int):
        return self._post({"action": "status", "order": str(order_id)})

    def get_multi_status(self, order_ids: List[int]):
        return self._post({"action": "status", "orders": ",".join(map(str, order_ids))})

    def refill(self, order_id: int):
        return self._post({"action": "refill", "order": str(order_id)})

    def cancel(self, order_ids: List[int]):
        return self._post({"action": "cancel", "orders": ",".join(map(str, order_ids))})

    def get_refill_status(self, refill_id: int):
        return self._post({"action": "refill_status", "refill": str(refill_id)})
