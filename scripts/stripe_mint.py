"""Create the Reality Check product, price, and Payment Link on the team Stripe account.
Idempotent: reuses an existing active product named 'Reality Check' and its $8 price/link.
Key from keychain ZEROHUMAN_STRIPE_WRITE_KEY (or env). Prints the link URL only."""
import os
import subprocess
import sys

import httpx

PRODUCTS = {
    "reality_check": ("Reality Check", 800,
        "Human-verified reality check: at least three real people tell you what your page or pitch says, "
        "more when the models disagree, plus the verdict and the minority view."),
    "full_reality_check": ("Full Reality Check", 2500,
        "One paste, every lens: do strangers get it (clarity), is there demand (six-point gate), do your autonomy "
        "claims hold, and what the evidence cost. Human-verified, model consensus, objective QA where a URL exists."),
}
SKU = sys.argv[1] if len(sys.argv) > 1 else "reality_check"
NAME, PRICE_CENTS, DESC = PRODUCTS[SKU]


def key() -> str:
    k = os.environ.get("ZEROHUMAN_STRIPE_WRITE_KEY") or subprocess.run(
        ["security", "find-generic-password", "-s", "ZEROHUMAN_STRIPE_WRITE_KEY", "-w"], capture_output=True, text=True).stdout.strip()
    if not k.startswith("rk_"):
        sys.exit("no ZEROHUMAN_STRIPE_WRITE_KEY")
    return k


def main() -> None:
    c = httpx.Client(base_url="https://api.stripe.com/v1", auth=(key(), ""), timeout=30)
    prods = c.get("/products", params={"active": "true", "limit": 100}).raise_for_status().json()["data"]
    prod = next((p for p in prods if p["name"] == NAME), None)
    if not prod:
        prod = c.post("/products", data={"name": NAME, "description": DESC}).raise_for_status().json()
    prices = c.get("/prices", params={"product": prod["id"], "active": "true", "limit": 100}).raise_for_status().json()["data"]
    price = next((p for p in prices if p["unit_amount"] == PRICE_CENTS and p["currency"] == "usd" and not p.get("recurring")), None)
    if not price:
        price = c.post("/prices", data={"product": prod["id"], "unit_amount": PRICE_CENTS, "currency": "usd"}).raise_for_status().json()
    links = c.get("/payment_links", params={"active": "true", "limit": 100}).raise_for_status().json()["data"]
    link = None
    for l in links:
        items = c.get(f"/payment_links/{l['id']}/line_items").raise_for_status().json()["data"]
        if any(i["price"]["id"] == price["id"] for i in items):
            link = l
            break
    if not link:
        link = c.post("/payment_links", data={
            "line_items[0][price]": price["id"], "line_items[0][quantity]": 1,
            "line_items[0][adjustable_quantity][enabled]": "true", "line_items[0][adjustable_quantity][minimum]": 1, "line_items[0][adjustable_quantity][maximum]": 10,
            "after_completion[type]": "hosted_confirmation",
            "after_completion[hosted_confirmation][custom_message]": "Paid. Show this screen at the Reality Check table, or paste your page URL to the agent that sent you here. Your verdict page link arrives when the job settles.",
            "metadata[product]": SKU,
        }).raise_for_status().json()
    print(link["url"])


if __name__ == "__main__":
    main()
