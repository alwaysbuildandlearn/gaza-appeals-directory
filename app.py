"""Local Gaza appeals directory. Run python app.py."""
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parent
DB = ROOT / "appeals.sqlite3"
PAGE = 20
CATEGORIES = ("Food & essentials", "Medical care", "Shelter", "Education")
PROVIDERS = {"chuffed.org": "Chuffed", "www.chuffed.org": "Chuffed",
             "gofundme.com": "GoFundMe", "www.gofundme.com": "GoFundMe"}
ADMIN_PASSWORD = os.getenv("APPEALS_ADMIN_PASSWORD") or secrets.token_urlsafe(18)
ADMIN_PATH = "/review"
FRESH_DAYS = 7


@contextmanager
def database():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def initialize():
    with database() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS appeals (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
                story TEXT NOT NULL, url TEXT NOT NULL, provider TEXT NOT NULL,
                contact TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
                cents INTEGER, checked TEXT, demo INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS appeal_status ON appeals(status);
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, expires INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS metadata (name TEXT PRIMARY KEY);
        """)
        if os.getenv("APPEALS_DEMO", "1") == "1":
            seeded = conn.execute("INSERT OR IGNORE INTO metadata VALUES ('demo')").rowcount
            if seeded:
                titles = (
                    "Food parcels for displaced families", "Medical supplies for a community clinic",
                    "Help replace a damaged shelter", "Learning supplies for displaced students",
                    "Clean water for a neighbourhood", "Support a family's medical expenses",
                    "Winter blankets for families", "Books and supplies for a learning space",
                )
                for index in range(26):
                    title = titles[index % len(titles)]
                    if index >= len(titles):
                        title += f" · Example {index + 1}"
                    provider = "Chuffed" if index % 2 == 0 else "GoFundMe"
                    conn.execute("""
                        INSERT INTO appeals(title, category, story, url, provider, status, cents, checked, demo)
                        VALUES (?, ?, ?, '', ?, 'active', ?, ?, 1)
                    """, (title, CATEGORIES[index % 4],
                          "This fictional listing demonstrates how an organiser's story appears. "
                          "It does not represent a live fundraiser and cannot accept donations.",
                          provider, None if index == 25 else index * 725,
                          (date.today() - timedelta(days=10 if index == 24 else 0)).isoformat()))


def e(value):
    return escape(str(value), quote=True)


def current_cutoff():
    return (date.today() - timedelta(days=FRESH_DAYS)).isoformat()


def amount_label(row):
    if row["cents"] is None or not row["checked"]:
        return "Recent total unavailable"
    if row["checked"] < current_cutoff():
        return "Recent total out of date"
    return f"${row['cents'] / 100:,.2f} USD"


def layout(title, content):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>{e(title)} · Gaza Appeals</title>
<link rel="stylesheet" href="/style.css"><script src="/browse.js" defer></script></head>
<body><a class="skip" href="#main">Skip to content</a>
<header class="site-header"><nav aria-label="Main navigation"><a class="brand" href="/"><span class="mark" aria-hidden="true"></span>Gaza Appeals</a><a href="/submit">Submit an appeal <span aria-hidden="true">↗</span></a></nav></header>
<main id="main">{content}</main><footer><a href="/">Gaza Appeals</a><a href="/review">Reviewer sign-in</a></footer></body></html>"""


def donation(row):
    if row["demo"]:
        return '<span class="demo-note">Example appeal</span>'
    return f'<a class="button" href="{e(row["url"])}" rel="noreferrer">Donate on {e(row["provider"])} ↗</a>'


def card(row):
    return f"""<article class="card"><p class="category">{e(row['category'])}</p>
<h3><a href="/appeals/{row['id']}">{e(row['title'])}</a></h3>
<div class="amount"><span>Received in the past 5 weeks</span><strong>{e(amount_label(row))}</strong></div>
<div class="card-actions"><a href="/appeals/{row['id']}">Read the appeal</a>{donation(row)}</div></article>"""


def listing(query):
    search = query.get("q", [""])[0].strip()[:120]
    category = query.get("category", [""])[0]
    try:
        page = min(1000000, max(1, int(query.get("page", ["1"])[0])))
    except ValueError:
        page = 1
    conditions = ["status = 'active'"]
    params = []
    if search:
        conditions.append("(instr(lower(title), lower(?)) > 0 OR instr(lower(story), lower(?)) > 0)")
        params.extend((search, search))
    if category in CATEGORIES:
        conditions.append("category = ?")
        params.append(category)
    where = " AND ".join(conditions)
    with database() as conn:
        total = conn.execute(f"SELECT count(*) FROM appeals WHERE {where}", params).fetchone()[0]
        page = min(page, max(1, (total + PAGE - 1) // PAGE))
        offset = (page - 1) * PAGE
        cutoff = current_cutoff()
        rows = conn.execute(f"""
            SELECT * FROM appeals WHERE {where}
            ORDER BY CASE WHEN cents IS NULL OR checked IS NULL OR checked < ? THEN 1 ELSE 0 END,
                     CASE WHEN checked >= ? THEN cents END ASC NULLS LAST, id
            LIMIT ? OFFSET ?
        """, (*params, cutoff, cutoff, PAGE, offset)).fetchall()
        demo = conn.execute("SELECT 1 FROM appeals WHERE status = 'active' AND demo = 1 LIMIT 1").fetchone()
    options = '<option value="">All categories</option>' + ''.join(
        f'<option{" selected" if category == item else ""}>{e(item)}</option>' for item in CATEGORIES)
    links = []
    for number, label in ((page - 1, "← Previous 20"), (page + 1, "Show 20 more →")):
        if 1 <= number <= (total + PAGE - 1) // PAGE:
            href = urlencode({"q": search, "category": category, "page": number})
            relation = "next" if number > page else "prev"
            links.append(f'<a class="button secondary" rel="{relation}" href="/?{e(href)}#appeals">{label}</a>')
    count = f"{offset + 1}–{offset + len(rows)} of {total} appeals" if rows else "No matching appeals"
    examples = '<p class="demo-banner">Demo directory · Example appeals cannot accept donations.</p>' if demo else ''
    cards = ''.join(map(card, rows)) or '<p class="empty">Try a different search or <a href="/">clear the filters</a>.</p>'
    return layout("Find an appeal", f"""
<section class="hero"><div class="wrap hero-inner"><p class="eyebrow">FUNDRAISING DIRECTORY</p>
<h1>Find a Gaza appeal.</h1><p>Browse fundraisers for families and community efforts in Gaza. Appeals receiving the least support over the past five weeks appear first.</p>
<a class="button hero-button" href="#appeals">Browse appeals ↓</a></div></section>
<section class="wrap directory" id="appeals"><div class="section-head"><h2>Browse appeals</h2><p id="result-count" role="status">{count}</p></div>
{examples}
<form class="search" method="get" action="/#appeals"><label>Search appeals<input type="search" name="q" value="{e(search)}" placeholder="Try a name or keyword" maxlength="120"></label>
<label>Category<select name="category">{options}</select></label><button class="button">Search</button></form>
<div class="grid">{cards}</div><nav class="pagination" aria-label="Appeal pages">{''.join(links)}</nav></section>""")


def submission(error="", values=None):
    values = values or {}
    def value(key):
        return e(values.get(key, ""))
    options = ''.join(f'<option{" selected" if values.get("category") == item else ""}>{e(item)}</option>' for item in CATEGORIES)
    notice = f'<p class="error" role="alert">{e(error)}</p>' if error else ''
    return layout("Submit an appeal", f"""<section class="narrow"><a href="/">← Browse appeals</a>
<h1>Submit an appeal</h1><p>Send an existing Chuffed or GoFundMe campaign for review. Your contact email is visible only to reviewers.</p>{notice}
<form method="post" class="stack">
<label>Appeal title<input name="title" maxlength="120" required value="{value('title')}"></label>
<label>Category<select name="category">{options}</select></label>
<label>Campaign link<input type="url" name="url" maxlength="500" required value="{value('url')}"></label>
<label>Public story<textarea name="story" maxlength="3000" rows="6" required>{value('story')}</textarea></label>
<label>Contact email<input type="email" name="contact" maxlength="160" required value="{value('contact')}"></label>
<button class="button">Send for review</button></form></section>""")


def provider_for(raw):
    try:
        url = urlsplit(raw)
        provider = PROVIDERS.get(url.netloc.lower())
        expected_path = "/project/" if provider == "Chuffed" else "/f/"
        if url.scheme == "https" and provider and url.path.startswith(expected_path) and url.path[len(expected_path):].strip("/"):
            return provider
    except ValueError:
        pass
    return None


def request_values(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if not 0 < length <= 30000:
        raise ValueError
    form = parse_qs(handler.rfile.read(length).decode(), keep_blank_values=True, max_num_fields=12)
    return {key: values[0].strip() for key, values in form.items()}


def detail(row):
    checked = f"<p>Donation data last checked {e(row['checked'])}.</p>" if row["checked"] else ""
    return layout(row["title"], f"""<article class="narrow"><a href="/">← Browse appeals</a>
<p class="category">{e(row['category'])}</p><h1>{e(row['title'])}</h1>
<div class="story">{e(row['story'])}</div>
<div class="amount"><span>Received in the past 5 weeks</span><strong>{e(amount_label(row))}</strong></div>{checked}
<p>Share this appeal using the link in your address bar.</p>{donation(row)}</article>""")


def review(token):
    with database() as conn:
        rows = conn.execute("SELECT * FROM appeals WHERE demo = 0 ORDER BY status != 'pending', id DESC").fetchall()
    forms = []
    for row in rows:
        choices = ''.join(f'<option value="{status}"{" selected" if row["status"] == status else ""}>{status.title()}</option>'
                          for status in ("pending", "active", "paused"))
        amount = "" if row["cents"] is None else f"{row['cents'] / 100:.2f}"
        forms.append(f"""<article class="card"><h2>{e(row['title'])}</h2>
<p class="story">{e(row['story'])}</p><p>Contact {e(row['contact'])}</p>
<p><a href="{e(row['url'])}" rel="noreferrer">Review the campaign on {e(row['provider'])} ↗</a></p>
<form method="post" class="stack"><input type="hidden" name="csrf" value="{e(token)}">
<input type="hidden" name="id" value="{row['id']}">
<label>Listing status<select name="status">{choices}</select></label>
<label>Total received in the last five weeks (USD)<input type="number" name="amount" min="0" max="999999999" step="0.01" value="{amount}"></label>
<label>Date this total was checked<input type="date" name="checked" max="{date.today()}" value="{e(row['checked'] or '')}"></label>
<button class="button">Save appeal</button></form></article>""")
    empty = "<p>No appeals submitted yet.</p>"
    return layout("Review appeals", f"""<section class="narrow"><h1>Review appeals</h1>
<p>Enter the total for the 35 days ending on the check date. Leave both fields blank when the total is unknown.</p>
<form method="post"><input type="hidden" name="csrf" value="{e(token)}">
<button class="button secondary" name="logout" value="1">Sign out</button></form>
<div class="stack">{''.join(forms) or empty}</div></section>""")


class Handler(BaseHTTPRequestHandler):
    def page(self, content, status=200, content_type="text/html; charset=utf-8"):
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, path, cookie=None):
        self.send_response(303)
        self.send_header("Location", path)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def message(self, heading, message, status=200):
        link = ADMIN_PATH if heading == "Invalid update" else "/"
        label = "Back to review" if link == ADMIN_PATH else "Browse appeals"
        self.page(layout(heading, f'<section class="narrow"><h1>{e(heading)}</h1><p>{e(message)}</p><a href="{link}">{label}</a></section>'), status)

    def session(self):
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        if "review_session" not in cookie:
            return None
        token = cookie["review_session"].value
        with database() as conn:
            found = conn.execute("SELECT token FROM sessions WHERE token = ? AND expires > unixepoch()", (token,)).fetchone()
        return found["token"] if found else None

    def do_GET(self):
        parsed = urlsplit(self.path)
        path = parsed.path
        if path == "/":
            self.page(listing(parse_qs(parsed.query)))
        elif path == "/style.css":
            self.page((ROOT / "style.css").read_text(encoding="utf-8"), content_type="text/css; charset=utf-8")
        elif path == "/browse.js":
            self.page((ROOT / "browse.js").read_text(encoding="utf-8"), content_type="text/javascript; charset=utf-8")
        elif path == "/submit":
            self.page(submission())
        elif path == "/submitted":
            self.message("Appeal submitted", "Your appeal will appear in the directory after a reviewer approves it.")
        elif path == ADMIN_PATH:
            token = self.session()
            if token:
                self.page(review(token))
            else:
                self.page(layout("Reviewer sign-in", """<section class="narrow">
<h1>Reviewer sign-in</h1><form method="post" class="stack"><label>Password
<input type="password" name="password" autocomplete="current-password" required></label>
<button class="button">Sign in</button></form></section>"""))
        elif path.startswith("/appeals/") and path[9:].isascii() and path[9:].isdigit() and len(path[9:]) <= 18:
            with database() as conn:
                row = conn.execute("SELECT * FROM appeals WHERE id = ? AND status = 'active'", (int(path[9:]),)).fetchone()
            if row:
                self.page(detail(row))
            else:
                self.message("Appeal unavailable", "This appeal is not currently listed.", 404)
        else:
            self.message("Page unavailable", "This address does not match a page in the directory.", 404)

    def do_POST(self):
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.message("Request declined", "Open the form from the directory and try again.", 403)
            return
        try:
            form = request_values(self)
        except (ValueError, UnicodeError):
            self.message("Invalid form", "Check your submission and try again.", 400)
            return
        if self.path == "/submit":
            self.submit(form)
        elif self.path == ADMIN_PATH:
            self.update(form)
        else:
            self.message("Page unavailable", "This address does not match a form.", 404)

    def submit(self, form):
        title, category, url, story, contact = (form.get(k, "") for k in ("title", "category", "url", "story", "contact"))
        provider = provider_for(url)
        if not (0 < len(title) <= 120 and category in CATEGORIES and len(url) <= 500 and provider
                and 0 < len(story) <= 3000 and 0 < len(contact) <= 160 and "@" in contact):
            self.page(submission("Check the required fields and supply a supported HTTPS campaign link.", form), 400)
            return
        with database() as conn:
            conn.execute("INSERT INTO appeals(title, category, url, provider, story, contact) VALUES (?, ?, ?, ?, ?, ?)",
                         (title, category, url, provider, story, contact))
        self.redirect("/submitted")

    def update(self, form):
        token = self.session()
        if not token:
            if not hmac.compare_digest(form.get("password", "").encode(), ADMIN_PASSWORD.encode()):
                self.message("Sign-in failed", "Open Reviewer sign-in to try again.", 403)
                return
            token = secrets.token_urlsafe(32)
            with database() as conn:
                conn.execute("DELETE FROM sessions WHERE expires <= unixepoch()")
                conn.execute("INSERT INTO sessions VALUES (?, unixepoch() + 28800)", (token,))
            self.redirect(ADMIN_PATH, f"review_session={token}; HttpOnly; SameSite=Strict; Path=/review; Max-Age=28800")
            return
        if not hmac.compare_digest(form.get("csrf", "").encode(), token.encode()):
            self.message("Invalid update", "Refresh the review page and try again.", 403)
            return
        if form.get("logout") == "1":
            with database() as conn:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            self.redirect(ADMIN_PATH, "review_session=; HttpOnly; SameSite=Strict; Path=/review; Max-Age=0")
            return
        try:
            appeal_id = int(form.get("id", ""))
            status = form.get("status", "")
            checked = form.get("checked", "")
            raw = form.get("amount", "")
            if not 0 < appeal_id < 2**63 or status not in ("pending", "active", "paused") or bool(raw) != bool(checked):
                raise ValueError
            cents = Decimal(raw) * 100 if raw else None
            if cents is not None and (
                not cents.is_finite() or not 0 <= cents <= 99999999900 or cents != cents.to_integral_value()
                or date.fromisoformat(checked) > date.today()
            ):
                raise ValueError
            if checked:
                checked = date.fromisoformat(checked).isoformat()
        except (InvalidOperation, ValueError):
            self.message("Invalid update", "Supply a valid status, amount, and check date.", 400)
            return
        with database() as conn:
            result = conn.execute("UPDATE appeals SET status=?, cents=?, checked=? WHERE id=? AND demo=0",
                                  (status, int(cents) if cents is not None else None, checked or None, appeal_id))
        if not result.rowcount:
            self.message("Invalid update", "This appeal is unavailable for review.", 404)
            return
        self.redirect(ADMIN_PATH)


if __name__ == "__main__":
    initialize()
    port = int(os.getenv("APPEALS_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Gaza Appeals: http://127.0.0.1:{port}/", flush=True)
    if not os.getenv("APPEALS_ADMIN_PASSWORD"):
        print(f"Temporary reviewer password: {ADMIN_PASSWORD}", flush=True)
    server.serve_forever()

