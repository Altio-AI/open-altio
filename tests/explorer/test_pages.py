"""The page and its files, at the explorer's own addresses (pages.py).

Every page has a plain address with no "#": Home is "/", a product's
Overview /product/ADALIMUMAB/overview. The page is served at each, so a
reload or a link opens the page it names; the page script decides what to draw
there (test_page.py). Any other address goes home. The page and its files hold
no data, so they need nobody's sign-in.
"""

from __future__ import annotations

FRONT_END = '<script type="module" src="/ui/app.js">'
SCOPE_TABS = ["overview", "cases"]  # a product's and All cases' tabs, as their addresses name them

PAGES = (
    ["/", "/all", "/release", "/sql", "/downloads", "/methods"]
    + [f"/all/{tab}" for tab in SCOPE_TABS]
    + ["/product/ADALIMUMAB", "/product/A%2FB/cases"]
    + [f"/product/ADALIMUMAB/{tab}" for tab in SCOPE_TABS]
)
NOT_PAGES = (
    "/nothing",
    "/products",
    "/all/overview/more",
    "/favicon.ico",
    "/index.html",
    "/admin",
    "/admin/requests",
)
FILES = (
    "/ui/app.js",
    "/ui/icons.js",
    "/ui/css/app.css",
    "/ui/css/responsive.css",
    "/ui/css/theme.css",
    "/ui/icon.svg",
)


def test_the_page_is_served_at_every_pages_address(client):
    for address in PAGES:
        got = client.get(address, follow_redirects=False)
        assert got.status_code == 200 and FRONT_END in got.text, address
        assert got.headers["content-type"].startswith("text/html"), address
        assert got.headers["cache-control"] == "no-cache", address


def test_the_old_rules_address_forwards_to_how_we_clean_faers(client):
    got = client.get("/rules?open=ebgm", follow_redirects=False)
    assert got.status_code == 308 and got.headers["location"] == "/methods?open=ebgm"
    got = client.get("/rules", follow_redirects=False)
    assert got.status_code == 308 and got.headers["location"] == "/methods"


def test_the_page_names_its_files_and_each_is_served_to_be_checked_again(client):
    page = client.get("/").text
    for path in FILES:
        assert path in page or path.endswith(".js"), path  # app.js imports the other modules itself
        got = client.get(path)
        assert got.status_code == 200, path
        assert got.headers["cache-control"] == "no-cache", path
    assert "javascript" in client.get("/ui/app.js").headers["content-type"]


def test_only_the_pages_own_files_are_served(client):
    for path in ("/ui/..%2Fapp.py", "/ui/nothing.js", "/ui/index.html", "/ui/"):
        assert client.get(path).status_code == 404, path
    # "/ui/../app.py" is asked as "/app.py": no page, so home, never the file
    got = client.get("/ui/../app.py")
    assert got.url.path == "/" and FRONT_END in got.text and "create_app" not in got.text


def test_an_address_that_is_no_page_goes_home(client):
    for address in NOT_PAGES:
        got = client.get(address, follow_redirects=False)
        assert (got.status_code, got.headers.get("location")) == (302, "/"), address


def test_only_a_page_asked_for_with_get_goes_home(client):
    assert client.post("/nothing").status_code == 404
    assert client.post("/release").status_code == 405  # a known address asked the wrong way
    assert client.get("/api/sql").status_code == 405


def test_an_unknown_api_path_is_a_json_404(client):
    got = client.get("/api/no-such-thing")
    assert (got.status_code, got.json()) == (404, {"problem": "not found"})


def test_no_two_icons_share_a_drawing():
    import re
    from pathlib import Path

    import open_altio.explorer as explorer

    src = (Path(explorer.__file__).parent / "ui" / "icons.js").read_text()
    block = src.split("const PATHS = {", 1)[1].split("\n};", 1)[0]
    drawings = re.findall(r"^  (\w+): '(.*)',$", block, re.M)
    assert len(drawings) > 20
    seen = {}
    for name, drawing in drawings:
        assert drawing not in seen, f"{name} and {seen[drawing]} share a drawing"
        seen[drawing] = name
