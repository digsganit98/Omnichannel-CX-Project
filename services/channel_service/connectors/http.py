import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ConnectorError(RuntimeError):
    pass


def get_json(url: str, token: str, query: dict[str, str] | None = None) -> dict:
    if query:
        url = f"{url}?{urlencode(query)}"
    request = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ConnectorError(f"GET {url} failed with {exc.code}: {detail}") from exc


def post_json(url: str, token: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ConnectorError(f"POST {url} failed with {exc.code}: {detail}") from exc
