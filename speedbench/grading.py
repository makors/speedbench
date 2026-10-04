"""No model judge: URL and visible semantic heading must both match."""
import re
import unicodedata
from urllib.parse import unquote


def normalized(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def grade(task, page):
    expected = task["expected"]
    checks = {
        "url": bool(re.search(expected["url_regex"], unquote(page.get("url", "")))),
        "heading": any(re.search(expected["heading_regex"], normalized(h), re.I)
                       for h in page.get("headings", [])),
        "document_loaded": page.get("ready") == "complete",
    }
    return {"passed": all(checks.values()), "checks": checks}
