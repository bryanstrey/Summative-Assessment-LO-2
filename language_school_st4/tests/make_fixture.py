# Creates the SYNTHETIC exchange-rate fixture used by --mode fixture.
# The rates are invented for demonstration; they are not market values.
# Run from the project root:  python tests/make_fixture.py   (refuses to overwrite)
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
import exchange_api as api  # noqa: E402

RATES = [("2026-10-14", 5.1000), ("2026-10-15", 5.1100), ("2026-10-16", 5.1200),
         ("2026-10-19", 5.1500), ("2026-10-20", 5.1800), ("2026-10-21", 5.2000),
         ("2026-10-22", 5.2500)]
payload = [{"date": d, "base": "USD", "quote": "BRL", "rate": r} for d, r in RATES]
content = (json.dumps(payload, indent=2) + "\n").encode()
folder = PROJECT / "data" / "fixtures"
folder.mkdir(parents=True, exist_ok=True)
stem = "frankfurter_FIXTURE_USDBRL_2026-10-14_2026-10-22_synthetic"
rates = api.validate_rates(api.rates_to_dataframe(payload))
fetched = {"content": content, "url": "n/a - synthetic fixture (no request was made)",
           "params": {"from": "2026-10-14", "to": "2026-10-22", "base": "USD",
                      "quotes": "BRL", "providers": "FIXTURE"},
           "http_status": 0, "acquired_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
meta = api.build_metadata(fetched, api.describe_coverage(rates), api.inspect_json(payload))
meta.update({
    "provider": "SYNTHETIC TEACHING FIXTURE - invented data, not market rates",
    "provider_key": "FIXTURE", "synthetic": True,
    "use_conditions": "Invented for demonstration and tests. Never use as real exchange rates."})
with (folder / f"{stem}.json").open("xb") as f:
    f.write(content)
with (folder / f"{stem}.metadata.json").open("x", encoding="utf-8") as f:
    json.dump(meta, f, indent=2, ensure_ascii=False)
    f.write("\n")
print("Created", stem)
