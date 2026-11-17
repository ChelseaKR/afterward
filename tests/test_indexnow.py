"""IndexNow selection and submission (indexnow.py), with fixtures, a fake HTTP
client and negative controls. Nothing here touches the network."""

from __future__ import annotations

import http.client
import json
import socket
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import urlsplit

import pytest

from afterward import indexnow as ix

BASE = "https://example.test"
KEY = "ab" * 16  # built, so a secret scanner does not read a fixture as a credential

PAGE = "<html><head><title>t</title></head><body>x</body></html>"
NOINDEX = '<html><head><meta name="robots" content="noindex,follow"></head></html>'


def _sitemap(entries: dict[str, str]) -> str:
    rows = "\n".join(
        f"  <url><loc>{u}</loc>" + (f"<lastmod>{m}</lastmod>" if m else "") + "</url>"
        for u, m in entries.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{rows}\n</urlset>\n'
    )


def _site(tmp_path: Path, pages: dict[str, str]) -> Path:
    """A built site: index.html per directory path, a key file, robots.txt."""
    root = tmp_path / "site"
    for rel, html in pages.items():
        f = root / rel / "index.html" if rel else root / "index.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(html, encoding="utf-8")
    (root / f"{KEY}.txt").write_text(KEY + "\n", encoding="utf-8")
    (root / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8"
    )
    return root


class FakeClient:
    def __init__(self, status: int = 200, raises: Exception | None = None) -> None:
        self.status, self.raises = status, raises
        self.calls: list[tuple[str, Any, dict[str, str]]] = []

    def post_json(self, url: str, body: bytes, headers: Mapping[str, str]) -> int:
        self.calls.append((url, json.loads(body), dict(headers)))
        if self.raises:
            raise self.raises
        return self.status


def test_sitemap_parse_keeps_missing_lastmod_as_empty_not_a_date() -> None:
    got = ix.parse_sitemap(_sitemap({f"{BASE}/": "2026-10-01", f"{BASE}/about/": ""}))
    assert got == {f"{BASE}/": "2026-10-01", f"{BASE}/about/": ""}


def test_new_and_changed_urls_are_selected_unchanged_are_not() -> None:
    prev = {f"{BASE}/a/": "1", f"{BASE}/b/": "1", f"{BASE}/c/": ""}
    cur = {f"{BASE}/a/": "1", f"{BASE}/b/": "2", f"{BASE}/c/": "", f"{BASE}/d/": "1"}
    assert ix.select_changed(prev, cur) == [f"{BASE}/b/", f"{BASE}/d/"]


def test_an_unreadable_previous_site_selects_nothing_but_an_empty_one_selects_all() -> None:
    cur = {f"{BASE}/a/": "1"}
    assert ix.select_changed(None, cur) == []
    assert ix.select_changed({}, cur) == [f"{BASE}/a/"]


def test_filter_drops_noindex_foreign_host_and_unbuilt_pages(tmp_path: Path) -> None:
    site = _site(tmp_path, {"": PAGE, "a": PAGE, "thin": NOINDEX})
    urls = [
        f"{BASE}/a/",
        f"{BASE}/thin/",
        "https://evil.test/a/",
        f"{BASE}/missing/",
        "http://example.test/a/",
        "https://example.test:8443/a/",
    ]
    kept, notes = ix.filter_submittable(urls, base_url=BASE, site_dir=site)
    assert kept == [f"{BASE}/a/"]
    assert len(notes) == 5
    assert any("noindex" in n for n in notes)


def test_validate_passes_a_clean_list(tmp_path: Path) -> None:
    site = _site(tmp_path, {"a": PAGE})
    ix.validate_submission([f"{BASE}/a/"], base_url=BASE, site_dir=site)


@pytest.mark.parametrize(
    ("page", "url", "why"),
    [
        (NOINDEX, f"{BASE}/a/", "noindex"),
        (PAGE, "https://evil.test/a/", "not on"),
    ],
)
def test_negative_control_validate_rejects_noindex_and_foreign_host(
    tmp_path: Path, page: str, url: str, why: str
) -> None:
    site = _site(tmp_path, {"a": page})
    # The sabotage applied: the very same list passes when the fault is absent.
    if why == "noindex":
        assert ix.is_noindex(page) and not ix.is_noindex(PAGE)
    else:
        assert ix.host_of(BASE) != urlsplit(url).hostname
    with pytest.raises(ix.IndexNowError, match=why):
        ix.validate_submission([url], base_url=BASE, site_dir=site)


def test_negative_control_validate_rejects_over_cap_and_duplicates(tmp_path: Path) -> None:
    site = _site(tmp_path, {"a": PAGE})
    over = [f"{BASE}/p{i}/" for i in range(ix.MAX_URLS + 1)]
    assert len(over) > ix.MAX_URLS
    with pytest.raises(ix.IndexNowError, match="exceeds"):
        ix.validate_submission(over, base_url=BASE, site_dir=site)
    with pytest.raises(ix.IndexNowError, match="duplicate"):
        ix.validate_submission([f"{BASE}/a/", f"{BASE}/a/"], base_url=BASE, site_dir=site)


def test_the_key_file_must_exist_once_and_match_its_name(tmp_path: Path) -> None:
    site = _site(tmp_path, {"": PAGE})
    assert ix.find_key(site) == KEY
    (site / f"{KEY}.txt").write_text("wrong\n", encoding="utf-8")
    with pytest.raises(ix.IndexNowError, match="body must equal"):
        ix.find_key(site)
    (site / f"{KEY}.txt").unlink()
    with pytest.raises(ix.IndexNowError, match="exactly one"):
        ix.find_key(site)


def test_payload_follows_the_documented_shape() -> None:
    p = ix.build_payload(BASE, KEY, [f"{BASE}/a/"])
    assert p == {
        "host": "example.test",
        "key": KEY,
        "keyLocation": f"{BASE}/{KEY}.txt",
        "urlList": [f"{BASE}/a/"],
    }


def test_submit_posts_json_to_the_endpoint_and_reports_acceptance() -> None:
    c = FakeClient(200)
    msg = ix.submit(ix.build_payload(BASE, KEY, [f"{BASE}/a/"]), c)
    url, body, headers = c.calls[0]
    assert url == ix.ENDPOINT
    assert body["urlList"] == [f"{BASE}/a/"]
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert "accepted 1 URLs" in msg


def test_submit_never_raises_and_sends_nothing_for_an_empty_list() -> None:
    empty = FakeClient()
    assert "nothing to submit" in ix.submit(ix.build_payload(BASE, KEY, []), empty)
    assert empty.calls == []
    for client in (
        FakeClient(403),
        FakeClient(429),
        FakeClient(raises=OSError("down")),
    ):
        msg = ix.submit(ix.build_payload(BASE, KEY, [f"{BASE}/a/"]), client)
        assert "normal crawl" in msg
        assert client.calls  # the failure path was really exercised


def test_robots_must_allow_bingbot_and_list_the_sitemap() -> None:
    ok = f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n"
    assert ix.check_robots(ok, BASE) == []
    blocked = f"User-agent: bingbot\nDisallow: /\n\nSitemap: {BASE}/sitemap.xml\n"
    assert ix.check_robots(blocked, BASE) == ["robots.txt does not allow Bingbot at the site root"]
    assert len(ix.check_robots("User-agent: *\nAllow: /\n", BASE)) == 1


def _run_select(
    tmp_path: Path,
    site: Path,
    live_text: str | None,
    kind: str = "sitemap",
    file: str = "sitemap.xml",
    *,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    def fake_fetch(url: str, missing_is_empty: bool) -> str | None:
        return live_text

    monkeypatch.setattr(ix, "fetch_text", fake_fetch)
    out = tmp_path / "urls.json"
    rc = ix.main(
        [
            "select",
            "--site-dir",
            str(site),
            "--base-url",
            BASE,
            "--kind",
            kind,
            "--file",
            file,
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    payload: dict[str, Any] = json.loads(out.read_text())
    return payload


def test_select_end_to_end_on_a_sitemap_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _site(tmp_path, {"": PAGE, "a": PAGE, "b": PAGE, "thin": NOINDEX})
    new = {f"{BASE}/": "1", f"{BASE}/a/": "2", f"{BASE}/b/": "1", f"{BASE}/thin/": "9"}
    (site / "sitemap.xml").write_text(_sitemap(new), encoding="utf-8")
    live = _sitemap({f"{BASE}/": "1", f"{BASE}/a/": "1"})
    payload = _run_select(tmp_path, site, live, monkeypatch=monkeypatch)
    # a changed, b new, thin is noindex (dropped even though it changed)
    assert payload["urlList"] == [f"{BASE}/a/", f"{BASE}/b/"]
    assert payload["key"] == KEY
    assert "noindex" in capsys.readouterr().out


def _manifest(d: dict[str, str]) -> str:
    pages = {p: {"fingerprint": f, "changed_at": None} for p, f in d.items()}
    return json.dumps({"schema": 1, "pages": pages})


def test_select_end_to_end_on_a_manifest_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = _site(tmp_path, {"": PAGE, "a": PAGE, "b": PAGE})
    (site / "sitemap.xml").write_text(
        _sitemap({f"{BASE}/a/": "", f"{BASE}/b/": ""}), encoding="utf-8"
    )
    (site / "lastmod.json").write_text(
        _manifest({"/a/": "x2", "/b/": "y", "/": "z"}), encoding="utf-8"
    )
    payload = _run_select(
        tmp_path,
        site,
        _manifest({"/a/": "x1", "/b/": "y"}),
        "manifest",
        "lastmod.json",
        monkeypatch=monkeypatch,
    )
    # "/" changed in the manifest but is not in the sitemap, so it is not announced.
    assert payload["urlList"] == [f"{BASE}/a/"]


def test_select_with_an_unreadable_live_site_submits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _site(tmp_path, {"a": PAGE})
    (site / "sitemap.xml").write_text(_sitemap({f"{BASE}/a/": "1"}), encoding="utf-8")
    payload = _run_select(tmp_path, site, None, monkeypatch=monkeypatch)
    assert payload["urlList"] == []
    assert "submitting nothing" in capsys.readouterr().out


def test_select_never_fails_the_job_when_robots_blocks_bingbot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    site = _site(tmp_path, {"a": PAGE})
    (site / "sitemap.xml").write_text(_sitemap({f"{BASE}/a/": "1"}), encoding="utf-8")
    (site / "robots.txt").write_text("User-agent: bingbot\nDisallow: /\n", encoding="utf-8")
    payload = _run_select(tmp_path, site, _sitemap({}), monkeypatch=monkeypatch)
    assert payload["urlList"] == []
    assert "skipped" in capsys.readouterr().out


def test_submit_command_exits_zero_even_when_the_list_is_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert ix.main(["submit", "--list", str(tmp_path / "nope.json")]) == 0
    assert "::notice" in capsys.readouterr().out


class _FakeResponse:
    def __init__(self, status: int, data: bytes, location: str | None) -> None:
        self.status, self._data, self._location = status, data, location

    def read(self) -> bytes:
        return self._data

    def getheader(self, name: str) -> str | None:
        return self._location if name == "Location" else None


class _FakeConn:
    """Stands in for http.client.HTTPSConnection: serves canned responses."""

    script: ClassVar[dict[str, tuple[int, bytes, str | None]]] = {}
    seen: ClassVar[list[tuple[str, str]]] = []

    def __init__(self, host: str, port: int | None = None, timeout: float | None = None) -> None:
        self.host = host

    def request(
        self,
        method: str,
        target: str,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.key = f"{self.host}{target}"
        _FakeConn.seen.append((method, self.key))

    def getresponse(self) -> _FakeResponse:
        status, data, location = _FakeConn.script[self.key]
        return _FakeResponse(status, data, location)

    def close(self) -> None:
        pass


def test_fetch_text_follows_a_redirect_and_distinguishes_404_from_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConn)
    _FakeConn.seen = []
    _FakeConn.script = {
        "example.test/sitemap.xml": (301, b"", "https://www.example.test/sitemap.xml"),
        "www.example.test/sitemap.xml": (200, b"<urlset/>", None),
        "example.test/gone": (404, b"", None),
        "example.test/boom": (503, b"", None),
    }
    assert ix.fetch_text("https://example.test/sitemap.xml", missing_is_empty=True) == "<urlset/>"
    assert _FakeConn.seen[-1] == ("GET", "www.example.test/sitemap.xml")
    assert ix.fetch_text("https://example.test/gone", missing_is_empty=True) == ""
    assert ix.fetch_text("https://example.test/gone", missing_is_empty=False) is None
    assert ix.fetch_text("https://example.test/boom", missing_is_empty=True) is None
    # a redirect off https is refused, so the read is "unknown", not followed
    _FakeConn.script["example.test/down"] = (302, b"", "http://example.test/x")
    assert ix.fetch_text("https://example.test/down", missing_is_empty=True) is None


def test_the_default_client_posts_over_https_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http.client, "HTTPSConnection", _FakeConn)
    _FakeConn.seen = []
    _FakeConn.script = {"api.indexnow.org/indexnow": (202, b"", None)}
    msg = ix.submit(ix.build_payload(BASE, KEY, [f"{BASE}/a/"]))
    assert _FakeConn.seen == [("POST", "api.indexnow.org/indexnow")]
    assert "HTTP 202" in msg
    with pytest.raises(ix.IndexNowError, match="only https"):
        ix.HttpsClient().post_json("http://api.indexnow.org/indexnow", b"{}", {})


def test_sitemap_parse_unescapes_entities_and_ignores_doctype_tricks() -> None:
    xml = (
        '<!DOCTYPE x [<!ENTITY e "boom">]>'
        "<urlset><url><loc>https://example.test/a?x=1&amp;y=2</loc></url></urlset>"
    )
    assert ix.parse_sitemap(xml) == {"https://example.test/a?x=1&y=2": ""}


def test_a_host_that_does_not_resolve_is_an_empty_site_only_when_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Dead:
        def __init__(self, *a: object, **k: object) -> None:
            raise socket.gaierror("no such host")

    monkeypatch.setattr(http.client, "HTTPSConnection", Dead)
    assert ix.fetch_text("https://nothere.example/x", missing_is_empty=True) == ""
    assert ix.fetch_text("https://nothere.example/x", missing_is_empty=False) is None
