"""Write demo/manifest.json: the Python files and fixtures the in-browser demo loads."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src" / "case_intake").glob("*.py"))
files += ["fixtures/sample_emails.json", "fixtures/sample_cases.json", "fixtures/recorded_model_outputs.json",
          "evals/expected_results.json"]
(ROOT / "demo" / "manifest.json").write_text(json.dumps({"files": files}, indent=1) + "\n")
print(f"{len(files)} files")
