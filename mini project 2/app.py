"""
TransitNotice - Main Flask Application
Public Transport Service Update Tracker
Handles routing, views, REST API endpoints, mock transport portals, and admin controls.
"""

import os
import json
from datetime import datetime, date
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash,
    Response
)
from database import (
    init_db,
    seed_default_data,
    get_db_connection,
    update_expired_statuses,
    reset_and_reseed_db,
    generate_content_hash
)
from scraper import scrape_source, check_robots_permission

app = Flask(__name__)
app.secret_key = "transit-notice-secret-key-college-demo"

# Ensure DB is initialized when Flask boots
init_db()
seed_default_data()


# ---------------------------------------------------------------------------
# ROBOTS.TXT ROUTE (Demonstrates crawler compliance)
# ---------------------------------------------------------------------------
@app.route("/robots.txt")
def robots_txt():
    """Serves robots.txt to demonstrate crawler permission compliance."""
    rules = [
        "User-agent: TransitNoticeBot",
        "Allow: /mock-transit-portal",
        "Allow: /mock-bus-feed",
        "Disallow: /admin",
        "Disallow: /api/",
        "",
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin"
    ]
    return Response("\n".join(rules), mimetype="text/plain")


# ---------------------------------------------------------------------------
# SIMULATED / MOCK OFFICIAL TRANSPORT PORTALS (FOR OFFLINE / RELIABLE DEMO)
# ---------------------------------------------------------------------------
@app.route("/mock-transit-portal")
def mock_transit_portal():
    """
    Renders an official-looking Metro Transit Authority public bulletin page.
    This provides an actual HTML webpage that our Requests & BeautifulSoup scraper
    can parse reliably during viva evaluation even with zero internet.
    """
    today_str = date.today().isoformat()
    return render_template("mock_portal.html", today=today_str, portal_name="Metro Transit Authority")


@app.route("/mock-bus-feed")
def mock_bus_feed():
    """Second simulated transport portal for City Bus Corporation."""
    today_str = date.today().isoformat()
    return render_template("mock_bus_feed.html", today=today_str)


# ---------------------------------------------------------------------------
# 1. HOME / DASHBOARD ROUTE
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Renders the Home Dashboard with KPI statistics, urgent alerts, and charts."""
    update_expired_statuses()
    conn = get_db_connection()
    cursor = conn.cursor()

    # KPI Metrics
    cursor.execute("SELECT COUNT(*) AS total_notices FROM notices")
    total_notices = cursor.fetchone()["total_notices"]

    cursor.execute("SELECT COUNT(*) AS active_notices FROM notices WHERE status = 'Active'")
    active_notices = cursor.fetchone()["active_notices"]

    cursor.execute("SELECT COUNT(*) AS revised_notices FROM notices WHERE status = 'Revised'")
    revised_notices = cursor.fetchone()["revised_notices"]

    cursor.execute("SELECT COUNT(*) AS cancelled_notices FROM notices WHERE status = 'Cancelled'")
    cancelled_notices = cursor.fetchone()["cancelled_notices"]

    cursor.execute("SELECT COUNT(*) AS expired_notices FROM notices WHERE status = 'Expired'")
    expired_notices = cursor.fetchone()["expired_notices"]

    cursor.execute("SELECT COUNT(*) AS total_routes FROM routes")
    total_routes = cursor.fetchone()["total_routes"]

    cursor.execute("SELECT COUNT(*) AS total_sources FROM sources WHERE is_active = 1")
    active_sources = cursor.fetchone()["total_sources"]

    # Last Checked Scrape Time
    cursor.execute("SELECT timestamp, status FROM scraper_logs ORDER BY timestamp DESC LIMIT 1")
    last_scrape_row = cursor.fetchone()
    last_checked_time = last_scrape_row["timestamp"] if last_scrape_row else "Never"
    last_scrape_status = last_scrape_row["status"] if last_scrape_row else "Pending"

    # High-Priority or Recent Active Notices for ticker and spotlight grid
    cursor.execute("""
        SELECT n.*, s.name AS source_name
        FROM notices n
        LEFT JOIN sources s ON n.source_id = s.id
        WHERE n.status IN ('Active', 'Revised')
        ORDER BY
            CASE n.severity
                WHEN 'Critical' THEN 1
                WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3
                ELSE 4
            END,
            n.updated_at DESC
        LIMIT 6
    """)
    recent_notices = cursor.fetchall()

    # Get distinct routes for quick filter pills
    cursor.execute("SELECT DISTINCT route_number FROM notices ORDER BY route_number")
    routes_list = [r["route_number"] for r in cursor.fetchall()]

    conn.close()

    return render_template(
        "index.html",
        total_notices=total_notices,
        active_notices=active_notices,
        revised_notices=revised_notices,
        cancelled_notices=cancelled_notices,
        expired_notices=expired_notices,
        total_routes=total_routes,
        active_sources=active_sources,
        last_checked_time=last_checked_time,
        last_scrape_status=last_scrape_status,
        recent_notices=recent_notices,
        routes_list=routes_list
    )


# ---------------------------------------------------------------------------
# 2. SERVICE NOTICES ROUTE (ADVANCED SEARCH & FILTERING)
# ---------------------------------------------------------------------------
@app.route("/notices")
def notices():
    """Renders comprehensive Service Notices catalog with multi-field search and filters."""
    update_expired_statuses()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Query Parameters
    q = request.args.get("q", "").strip()
    route_filter = request.args.get("route", "").strip()
    type_filter = request.args.get("type", "").strip()
    status_filter = request.args.get("status", "").strip()
    date_filter = request.args.get("date", "").strip()

    sql = """
        SELECT n.*, s.name AS source_name
        FROM notices n
        LEFT JOIN sources s ON n.source_id = s.id
        WHERE 1=1
    """
    params = []

    if q:
        sql += " AND (n.title LIKE ? OR n.affected_area LIKE ? OR n.description LIKE ?)"
        term = f"%{q}%"
        params.extend([term, term, term])

    if route_filter:
        sql += " AND n.route_number = ?"
        params.append(route_filter)

    if type_filter:
        sql += " AND n.advisory_type = ?"
        params.append(type_filter)

    if status_filter:
        sql += " AND n.status = ?"
        params.append(status_filter)

    if date_filter:
        sql += " AND date(n.start_date) <= date(?) AND date(n.end_date) >= date(?)"
        params.extend([date_filter, date_filter])

    sql += " ORDER BY n.updated_at DESC"

    cursor.execute(sql, params)
    notices_list = cursor.fetchall()

    # Available filter dropdown options
    cursor.execute("SELECT DISTINCT route_number FROM notices ORDER BY route_number")
    all_routes = [r["route_number"] for r in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT advisory_type FROM notices ORDER BY advisory_type")
    all_types = [t["advisory_type"] for t in cursor.fetchall()]

    conn.close()

    return render_template(
        "notices.html",
        notices=notices_list,
        all_routes=all_routes,
        all_types=all_types,
        selected_q=q,
        selected_route=route_filter,
        selected_type=type_filter,
        selected_status=status_filter,
        selected_date=date_filter,
        total_results=len(notices_list)
    )


# ---------------------------------------------------------------------------
# 3. ROUTE DETAILS & INTERACTIVE STOP PROGRESSION
# ---------------------------------------------------------------------------
@app.route("/routes")
def routes():
    """Renders Route Details page with route selector and interactive transit progression."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM routes ORDER BY route_number")
    all_routes = cursor.fetchall()

    selected_route_num = request.args.get("route", "")
    selected_route = None

    if selected_route_num:
        cursor.execute("SELECT * FROM routes WHERE route_number = ?", (selected_route_num,))
        selected_route = cursor.fetchone()

    # Default to first route if none selected
    if not selected_route and all_routes:
        selected_route = all_routes[0]

    route_notices = []
    parsed_stops = []
    affected_stops = set()

    if selected_route:
        # Load associated notices
        cursor.execute("""
            SELECT n.*, s.name AS source_name
            FROM notices n
            LEFT JOIN sources s ON n.source_id = s.id
            WHERE n.route_number = ?
            ORDER BY n.updated_at DESC
        """, (selected_route["route_number"],))
        route_notices = cursor.fetchall()

        # Parse stop progression JSON
        try:
            parsed_stops = json.loads(selected_route["stops_list"]) if selected_route["stops_list"] else []
        except Exception:
            parsed_stops = ["Origin", "Station A", "Station B", "Destination"]

        # Determine which stops match active notice affected areas
        for notice in route_notices:
            if notice["status"] in ["Active", "Revised"]:
                area = notice["affected_area"].lower()
                for stop in parsed_stops:
                    if stop.lower() in area or any(part.strip() in stop.lower() for part in area.split()):
                        affected_stops.add(stop)

    conn.close()

    return render_template(
        "route_detail.html",
        all_routes=all_routes,
        selected_route=selected_route,
        route_notices=route_notices,
        stops=parsed_stops,
        affected_stops=affected_stops
    )


# ---------------------------------------------------------------------------
# 4. ADMIN DASHBOARD & SYSTEM MONITORING
# ---------------------------------------------------------------------------
@app.route("/admin")
def admin():
    """Renders Admin Dashboard for scraper triggering, logs, and manual notice management."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Configured sources
    cursor.execute("SELECT * FROM sources ORDER BY id")
    sources = cursor.fetchall()

    # Recent scraper logs
    cursor.execute("SELECT * FROM scraper_logs ORDER BY timestamp DESC LIMIT 20")
    logs = cursor.fetchall()

    # All notices for administrative actions (edit/delete)
    cursor.execute("""
        SELECT n.*, s.name as source_name
        FROM notices n
        LEFT JOIN sources s ON n.source_id = s.id
        ORDER BY n.id DESC
    """)
    all_notices = cursor.fetchall()

    # Routes for the Add Notice dropdown
    cursor.execute("SELECT route_number, route_name FROM routes ORDER BY route_number")
    route_choices = cursor.fetchall()

    conn.close()

    return render_template(
        "admin.html",
        sources=sources,
        logs=logs,
        notices=all_notices,
        route_choices=route_choices
    )


# ---------------------------------------------------------------------------
# REST API ENDPOINTS
# ---------------------------------------------------------------------------
@app.route("/api/dashboard-stats")
def api_dashboard_stats():
    """Returns aggregated data for Chart.js interactive visualizations."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Notices by Advisory Type
    cursor.execute("""
        SELECT advisory_type, COUNT(*) AS count
        FROM notices
        GROUP BY advisory_type
        ORDER BY count DESC
    """)
    type_rows = cursor.fetchall()
    type_labels = [r["advisory_type"] for r in type_rows]
    type_counts = [r["count"] for r in type_rows]

    # 2. Notices by Status
    cursor.execute("""
        SELECT status, COUNT(*) AS count
        FROM notices
        GROUP BY status
        ORDER BY count DESC
    """)
    status_rows = cursor.fetchall()
    status_labels = [r["status"] for r in status_rows]
    status_counts = [r["count"] for r in status_rows]

    # 3. Notices by Transport Route
    cursor.execute("""
        SELECT route_number, COUNT(*) AS count
        FROM notices
        GROUP BY route_number
        ORDER BY count DESC
        LIMIT 6
    """)
    route_rows = cursor.fetchall()
    route_labels = [r["route_number"] for r in route_rows]
    route_counts = [r["count"] for r in route_rows]

    conn.close()

    return jsonify({
        "types": {"labels": type_labels, "data": type_counts},
        "statuses": {"labels": status_labels, "data": status_counts},
        "routes": {"labels": route_labels, "data": route_counts}
    })


@app.route("/api/scraper/trigger", methods=["POST"])
def api_scraper_trigger():
    """
    API endpoint to trigger the web scraper asynchronously or on-demand.
    Can trigger all sources or a specific source ID.
    """
    data = request.get_json(silent=True) or {}
    source_id = data.get("source_id")

    try:
        results = scrape_source(source_id=source_id)
        total_found = sum(r["items_found"] for r in results)
        total_new = sum(r["items_new"] for r in results)
        total_updated = sum(r["items_updated"] for r in results)

        return jsonify({
            "success": True,
            "message": f"Scraper execution finished: {total_found} parsed, {total_new} added, {total_updated} revised.",
            "results": results
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Scraper execution error: {str(e)}"
        }), 500


@app.route("/api/notices/<int:notice_id>/history")
def api_notice_history(notice_id):
    """Returns the revision history for a specific notice to display in the History Modal."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM notice_history
        WHERE notice_id = ?
        ORDER BY version DESC, changed_at DESC
    """, (notice_id,))
    history_records = [dict(row) for row in cursor.fetchall()]

    # Also retrieve current notice state
    cursor.execute("SELECT * FROM notices WHERE id = ?", (notice_id,))
    current = cursor.fetchone()
    current_dict = dict(current) if current else None

    conn.close()

    return jsonify({
        "success": True,
        "notice_id": notice_id,
        "current": current_dict,
        "history": history_records
    })


@app.route("/api/check-robots", methods=["POST"])
def api_check_robots():
    """Tests robots.txt permission for an arbitrary URL."""
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"allowed": False, "reason": "No target URL provided."}), 400

    allowed, reason = check_robots_permission(url)
    return jsonify({"url": url, "allowed": allowed, "reason": reason})


# ---------------------------------------------------------------------------
# ADMINISTRATIVE ACTIONS (MANUAL CRUD & DB RESET)
# ---------------------------------------------------------------------------
@app.route("/admin/notice/add", methods=["POST"])
def admin_add_notice():
    """Manual notice creation through Admin dashboard."""
    route_number = request.form.get("route_number", "").strip()
    affected_area = request.form.get("affected_area", "").strip()
    advisory_type = request.form.get("advisory_type", "Advisory").strip()
    severity = request.form.get("severity", "Medium").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    start_date = request.form.get("start_date", date.today().isoformat()).strip()
    end_date = request.form.get("end_date", date.today().isoformat()).strip()
    original_url = request.form.get("original_url", "").strip() or "http://127.0.0.1:5000/notices"

    if not (route_number and affected_area and title and description):
        flash("Please fill in all mandatory notice fields.", "error")
        return redirect(url_for("admin"))

    h = generate_content_hash(route_number, advisory_type, affected_area, start_date, end_date, description)
    ext_id = f"MANUAL-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notices (
            source_id, external_notice_id, route_number, affected_area,
            advisory_type, severity, title, description, start_date,
            end_date, original_url, status, content_hash, version
        )
        VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?, 1)
    """, (ext_id, route_number, affected_area, advisory_type, severity, title, description, start_date, end_date, original_url, h))
    conn.commit()
    conn.close()

    flash(f"Service notice for Route {route_number} added successfully.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/notice/delete/<int:notice_id>", methods=["POST"])
def admin_delete_notice(notice_id):
    """Deletes a notice and cascades to history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notices WHERE id = ?", (notice_id,))
    conn.commit()
    conn.close()
    flash(f"Notice #{notice_id} has been deleted.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/notice/mark-status/<int:notice_id>", methods=["POST"])
def admin_mark_status(notice_id):
    """Updates notice status directly (e.g. Cancelled, Expired, Active)."""
    new_status = request.form.get("new_status", "Active")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE notices
        SET status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (new_status, notice_id))
    conn.commit()
    conn.close()
    flash(f"Notice #{notice_id} status updated to {new_status}.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/source/add", methods=["POST"])
def admin_add_source():
    """Adds a new transport data source for scraping."""
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    robots_url = request.form.get("robots_url", "").strip() or None

    if not (name and url):
        flash("Source name and URL are required.", "error")
        return redirect(url_for("admin"))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sources (name, url, robots_url, is_active, last_status)
        VALUES (?, ?, ?, 1, 'Pending')
    """, (name, url, robots_url))
    conn.commit()
    conn.close()
    flash(f"Scraper source '{name}' added successfully.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/source/toggle/<int:source_id>", methods=["POST"])
def admin_toggle_source(source_id):
    """Toggles active state of a scraping source."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sources SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END WHERE id = ?", (source_id,))
    conn.commit()
    conn.close()
    flash("Source status toggled.", "info")
    return redirect(url_for("admin"))


@app.route("/admin/reset-db", methods=["POST"])
def admin_reset_db():
    """Resets database and reseeds with realistic demo data."""
    reset_and_reseed_db()
    flash("Database reset and sample dataset re-seeded successfully.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    print("Starting TransitNotice - Public Transport Service Update Tracker...")
    print("Running on: http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
