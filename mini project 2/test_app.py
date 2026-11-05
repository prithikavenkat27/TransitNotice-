"""
TransitNotice - Automated Test Suite
Covers unit tests, scraper parsing, robots.txt compliance, API endpoints,
and database revision detection.
"""

import pytest
from bs4 import BeautifulSoup
from database import (
    init_db,
    seed_default_data,
    get_db_connection,
    generate_content_hash,
    update_expired_statuses
)
from scraper import parse_notice_card, check_robots_permission
from app import app


@pytest.fixture
def client():
    """Sets up a Flask test client."""
    app.config["TESTING"] = True
    init_db()
    seed_default_data()
    with app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# 1. DATABASE TESTS
# ---------------------------------------------------------------------------
def test_database_tables_exist():
    """Verifies all required tables are created in SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()

    assert "sources" in tables
    assert "routes" in tables
    assert "notices" in tables
    assert "notice_history" in tables
    assert "scraper_logs" in tables


def test_seed_data_presence():
    """Verifies that sample routes and notices are properly populated."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) AS count FROM routes")
    assert cursor.fetchone()["count"] >= 5

    cursor.execute("SELECT COUNT(*) AS count FROM notices")
    assert cursor.fetchone()["count"] >= 5

    cursor.execute("SELECT COUNT(*) AS count FROM sources")
    assert cursor.fetchone()["count"] >= 2
    conn.close()


def test_hash_generation():
    """Verifies SHA-256 hash generation is deterministic."""
    h1 = generate_content_hash("101", "Diversion", "Grand Ave", "2026-11-01", "2026-11-05", "Detour active")
    h2 = generate_content_hash("101", "Diversion", "Grand Ave", "2026-11-01", "2026-11-05", "Detour active")
    h3 = generate_content_hash("101", "Diversion", "Grand Ave", "2026-11-01", "2026-11-06", "Detour extended")

    assert h1 == h2
    assert h1 != h3


def test_expiry_updater():
    """Verifies that past-dated active notices are transitioned to Expired."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notices (
            source_id, external_notice_id, route_number, affected_area,
            advisory_type, severity, title, description, start_date, end_date,
            status, version
        )
        VALUES (1, 'TEST-EXP-001', 'TEST', 'Area A', 'Delay', 'Low', 'Old Delay', 'Past', '2020-01-01', '2020-01-02', 'Active', 1)
    """)
    conn.commit()
    conn.close()

    update_expired_statuses()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM notices WHERE external_notice_id = 'TEST-EXP-001'")
    row = cursor.fetchone()
    conn.close()

    assert row["status"] == "Expired"


# ---------------------------------------------------------------------------
# 2. SCRAPER & ROBOTS.TXT UNIT TESTS
# ---------------------------------------------------------------------------
def test_parse_notice_card_html():
    """Verifies BeautifulSoup parses structured attributes from HTML cards."""
    sample_html = """
    <div class="transit-notice-card" data-notice-id="TEST-HTML-99">
        <span class="route-badge">101</span>
        <span class="advisory-type">Diversion</span>
        <span class="severity-badge">High</span>
        <h3 class="notice-title">Water Pipeline Repair Detour</h3>
        <div class="affected-area">Grand Avenue Crossing</div>
        <p class="notice-description">Detour via 4th Boulevard.</p>
        <span class="start-date" data-start-date="2026-11-01">2026-11-01</span>
        <span class="end-date" data-end-date="2026-11-08">2026-11-08</span>
        <a href="/bulletins/99">Link</a>
    </div>
    """
    soup = BeautifulSoup(sample_html, "html.parser")
    card = soup.select_one(".transit-notice-card")
    parsed = parse_notice_card(card)

    assert parsed is not None
    assert parsed["external_notice_id"] == "TEST-HTML-99"
    assert parsed["route_number"] == "101"
    assert parsed["advisory_type"] == "Diversion"
    assert parsed["severity"] == "High"
    assert parsed["affected_area"] == "Grand Avenue Crossing"
    assert parsed["start_date"] == "2026-11-01"
    assert parsed["end_date"] == "2026-11-08"


def test_robots_permission_localhost():
    """Verifies internal local simulated source is permitted."""
    allowed, reason = check_robots_permission("http://127.0.0.1:5000/mock-transit-portal")
    assert allowed is True


# ---------------------------------------------------------------------------
# 3. FLASK ROUTE & ENDPOINT TESTS
# ---------------------------------------------------------------------------
def test_home_page(client):
    """Verifies Home Dashboard returns HTTP 200 with metrics and title."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"TransitNotice" in response.data
    assert b"Active Advisories" in response.data


def test_notices_page(client):
    """Verifies Service Notices catalog page returns HTTP 200 and search query."""
    response = client.get("/notices")
    assert response.status_code == 200
    assert b"Service Notices" in response.data

    # Filter test
    filtered = client.get("/notices?type=Diversion")
    assert filtered.status_code == 200
    assert b"Diversion" in filtered.data


def test_route_details_page(client):
    """Verifies Route Details page loads progression and stops."""
    response = client.get("/routes?route=101")
    assert response.status_code == 200
    assert b"Station Stop Progression" in response.data
    assert b"Central Station" in response.data


def test_admin_page(client):
    """Verifies Admin panel loads configured sources and logs."""
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Admin Operations" in response.data
    assert b"Configured Transport Sources" in response.data


def test_mock_portals(client):
    """Verifies that simulated mock portals are reachable and render HTML notices."""
    mta = client.get("/mock-transit-portal")
    assert mta.status_code == 200
    assert b"Metro Transit Authority" in mta.data

    bus = client.get("/mock-bus-feed")
    assert bus.status_code == 200
    assert b"City Bus Corporation" in bus.data


def test_robots_txt_route(client):
    """Verifies /robots.txt serves valid directives."""
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert b"User-agent: TransitNoticeBot" in resp.data
    assert b"Allow: /mock-transit-portal" in resp.data


def test_api_dashboard_stats(client):
    """Verifies /api/dashboard-stats returns valid chart payloads."""
    resp = client.get("/api/dashboard-stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "types" in data
    assert "statuses" in data
    assert "routes" in data
    assert len(data["types"]["labels"]) > 0


def test_api_notice_history(client):
    """Verifies revision history endpoint returns current notice and historical versions."""
    # Notice 3 is the seeded revised notice
    resp = client.get("/api/notices/3/history")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "current" in data
    assert "history" in data
    assert len(data["history"]) >= 1


def test_scraper_handles_unreachable_source_gracefully():
    """Verifies that an unavailable source logs a clean error message rather than crashing."""
    from scraper import scrape_source
    results = scrape_source(source_url="http://127.0.0.1:59999/non-existent-endpoint")
    assert len(results) >= 1
    assert results[0]["status"] in ["FAILED", "WARNING"]
    assert "error" in results[0]["message"].lower() or "connection" in results[0]["message"].lower()

