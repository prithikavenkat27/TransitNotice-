"""
TransitNotice - Database Module
Handles SQLite schema creation, connection management, seed data, and query utilities.
"""

import sqlite3
import os
import json
import hashlib
from datetime import datetime, date, timedelta

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transit_notice.db")


def get_db_connection():
    """Returns a SQLite database connection with row factory configured."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initializes tables in the SQLite database if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Sources table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            robots_url TEXT,
            is_active INTEGER DEFAULT 1,
            last_checked_at TIMESTAMP,
            last_status TEXT DEFAULT 'Pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Routes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            route_number TEXT UNIQUE NOT NULL,
            route_name TEXT NOT NULL,
            transport_mode TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            total_stops INTEGER DEFAULT 10,
            stops_list TEXT,
            status TEXT DEFAULT 'Normal'
        )
    """)

    # 3. Notices table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            external_notice_id TEXT,
            route_number TEXT NOT NULL,
            affected_area TEXT NOT NULL,
            advisory_type TEXT NOT NULL,
            severity TEXT DEFAULT 'Medium',
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            original_url TEXT,
            status TEXT DEFAULT 'Active',
            content_hash TEXT,
            version INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE SET NULL
        )
    """)

    # 4. Notice History table (tracks every revision/change)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notice_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notice_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            route_number TEXT,
            advisory_type TEXT,
            affected_area TEXT,
            description TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            change_summary TEXT,
            FOREIGN KEY (notice_id) REFERENCES notices (id) ON DELETE CASCADE
        )
    """)

    # 5. Scraper Logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraper_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT,
            source_url TEXT,
            status TEXT,
            items_found INTEGER DEFAULT 0,
            items_new INTEGER DEFAULT 0,
            items_updated INTEGER DEFAULT 0,
            error_details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def generate_content_hash(route_number, advisory_type, affected_area, start_date, end_date, description):
    """Calculates SHA256 hash to identify content modifications for revision detection."""
    raw = f"{route_number}|{advisory_type}|{affected_area}|{start_date}|{end_date}|{description.strip()}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def update_expired_statuses():
    """Updates notice statuses to Expired if end_date is in the past and notice was Active."""
    conn = get_db_connection()
    today_str = date.today().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE notices
        SET status = 'Expired', updated_at = CURRENT_TIMESTAMP
        WHERE status = 'Active' AND date(end_date) < date(?)
    """, (today_str,))
    conn.commit()
    conn.close()


def seed_default_data():
    """Seeds default routes, sources, and sample notices if database is empty."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if already seeded
    cursor.execute("SELECT COUNT(*) AS count FROM routes")
    if cursor.fetchone()["count"] > 0:
        conn.close()
        return

    today = date.today()
    yesterday = today - timedelta(days=1)
    past_week = today - timedelta(days=7)
    next_week = today + timedelta(days=7)
    next_month = today + timedelta(days=30)

    # 1. Seed Sources
    sources_data = [
        (
            "Metro Transit Authority Alerts (Mock Portal)",
            "http://127.0.0.1:5000/mock-transit-portal",
            "http://127.0.0.1:5000/robots.txt",
            1,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Success",
            None
        ),
        (
            "City Bus Corporation Disruption Feed",
            "http://127.0.0.1:5000/mock-bus-feed",
            "http://127.0.0.1:5000/robots.txt",
            1,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Success",
            None
        ),
        (
            "Regional Rail Planned Maintenance Service (Sample Restricted)",
            "https://example-transport.gov/notices/restricted",
            "https://example-transport.gov/robots.txt",
            0,
            None,
            "Inactive",
            "Disallowed by robots.txt policy"
        )
    ]

    cursor.executemany("""
        INSERT INTO sources (name, url, robots_url, is_active, last_checked_at, last_status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, sources_data)

    source_id_metro = 1
    source_id_bus = 2

    # 2. Seed Routes
    routes_data = [
        (
            "101",
            "Downtown Express",
            "Bus",
            "Central Station",
            "West End Terminal",
            12,
            json.dumps(["Central Station", "Market Square", "Civic Center", "Financial District", "Grand Avenue", "Riverfront", "High Street", "Tech Park", "University Gate", "West End Terminal"]),
            "Diverted"
        ),
        (
            "204B",
            "Suburban Crosstown",
            "Bus",
            "North Point Plaza",
            "South Hills Depot",
            14,
            json.dumps(["North Point Plaza", "Valley View", "Oakridge Park", "Pine Junction", "Kings Cross Rd", "Maple Lane", "Cedar Heights", "South Hills Depot"]),
            "Delayed"
        ),
        (
            "BLUE-METRO",
            "Blue Line Metro Corridor",
            "Metro",
            "Airport Station",
            "City Center Interchange",
            10,
            json.dumps(["Airport Station", "Cargo Terminal", "Industrial Zone", "Airport Bypass", "North Avenue", "Union Square", "Heritage Park", "City Center Interchange"]),
            "Maintenance"
        ),
        (
            "RED-METRO",
            "Red Line Rapid Metro",
            "Metro",
            "Harbor Bay",
            "Eastern Hills",
            11,
            json.dumps(["Harbor Bay", "Port Pier 4", "Fisherman Wharf", "Convention Hall", "Government Center", "Old City", "Stadium Complex", "Eastern Hills"]),
            "Normal"
        ),
        (
            "TRAM-05",
            "Heritage Streetcar",
            "Tram",
            "Old Harbor",
            "Botanical Gardens",
            8,
            json.dumps(["Old Harbor", "Art Museum", "Grand Library", "Clock Tower Square", "Rose Garden", "Botanical Gardens"]),
            "Suspended"
        ),
        (
            "RAIL-SUB",
            "Northern Commuter Rail",
            "Suburban Rail",
            "Union Station",
            "Lakeside Junction",
            9,
            json.dumps(["Union Station", "Greenwood", "Sunnyvale", "Eastgate", "Fairfield", "Lakeside Junction"]),
            "Normal"
        )
    ]

    cursor.executemany("""
        INSERT INTO routes (route_number, route_name, transport_mode, origin, destination, total_stops, stops_list, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, routes_data)

    # 3. Seed Notices (Active, Expired, Revised with History, and Cancelled)
    notices_data = [
        # Notice 1: Active Diversion
        {
            "source_id": source_id_bus,
            "external_notice_id": "ADV-2026-001",
            "route_number": "101",
            "affected_area": "Grand Avenue & Riverfront",
            "advisory_type": "Diversion",
            "severity": "High",
            "title": "Pipeline Repair Diversion on Grand Avenue",
            "description": "Due to emergency water pipeline repair on Grand Avenue, Route 101 buses will detour via 4th Boulevard. Riverfront stop is temporarily relocated 200m north.",
            "start_date": today.isoformat(),
            "end_date": next_week.isoformat(),
            "original_url": "http://127.0.0.1:5000/mock-bus-feed#ADV-2026-001",
            "status": "Active",
            "version": 1
        },
        # Notice 2: Active Delay
        {
            "source_id": source_id_bus,
            "external_notice_id": "ADV-2026-002",
            "route_number": "204B",
            "affected_area": "Pine Junction to Maple Lane",
            "advisory_type": "Delay",
            "severity": "Medium",
            "title": "Road Resurfacing Work Causing 15-20 Min Delays",
            "description": "Lane closures for asphalt resurfacing between Pine Junction and Maple Lane are resulting in heavy congestion. Passengers are advised to allow extra travel time.",
            "start_date": yesterday.isoformat(),
            "end_date": (today + timedelta(days=3)).isoformat(),
            "original_url": "http://127.0.0.1:5000/mock-bus-feed#ADV-2026-002",
            "status": "Active",
            "version": 1
        },
        # Notice 3: Revised Notice (with history)
        {
            "source_id": source_id_metro,
            "external_notice_id": "ADV-2026-003",
            "route_number": "BLUE-METRO",
            "affected_area": "Airport Station to Industrial Zone",
            "advisory_type": "Maintenance",
            "severity": "High",
            "title": "Track Upgrades: Single Line Working Extended",
            "description": "REVISED: Nightly track stabilization and overhead wire modernization between Airport Station and Industrial Zone will continue through weekend. Shuttle trains operating at 25-minute intervals.",
            "start_date": past_week.isoformat(),
            "end_date": next_week.isoformat(),
            "original_url": "http://127.0.0.1:5000/mock-transit-portal#ADV-2026-003",
            "status": "Revised",
            "version": 2
        },
        # Notice 4: Expired Notice
        {
            "source_id": source_id_metro,
            "external_notice_id": "ADV-2026-004",
            "route_number": "RED-METRO",
            "affected_area": "Convention Hall",
            "advisory_type": "Special Service",
            "severity": "Low",
            "title": "Special Late Night Trains for Technology Expo",
            "description": "Additional late-night frequency provided for attendees of the International Tech Expo at Convention Hall. Normal schedule resumes after event completion.",
            "start_date": (today - timedelta(days=10)).isoformat(),
            "end_date": yesterday.isoformat(),
            "original_url": "http://127.0.0.1:5000/mock-transit-portal#ADV-2026-004",
            "status": "Expired",
            "version": 1
        },
        # Notice 5: Cancelled Notice
        {
            "source_id": source_id_bus,
            "external_notice_id": "ADV-2026-005",
            "route_number": "TRAM-05",
            "affected_area": "Art Museum to Rose Garden",
            "advisory_type": "Cancellation",
            "severity": "Critical",
            "title": "Full Suspension on Heritage Line due to Power Grid Failure",
            "description": "Overhead traction power failure near Clock Tower Square. Heritage Tram services temporarily suspended until emergency substation repair finishes.",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=2)).isoformat(),
            "original_url": "http://127.0.0.1:5000/mock-transit-portal#ADV-2026-005",
            "status": "Cancelled",
            "version": 1
        },
        # Notice 6: Active Planned Maintenance
        {
            "source_id": source_id_bus,
            "external_notice_id": "ADV-2026-006",
            "route_number": "RAIL-SUB",
            "affected_area": "Greenwood Station Crossing",
            "advisory_type": "Maintenance",
            "severity": "Low",
            "title": "Platform 2 Escalator Replacement",
            "description": "Platform 2 north escalator under scheduled maintenance. Elevator and stair access remain fully operational for passenger mobility.",
            "start_date": today.isoformat(),
            "end_date": next_month.isoformat(),
            "original_url": "http://127.0.0.1:5000/mock-bus-feed#ADV-2026-006",
            "status": "Active",
            "version": 1
        }
    ]

    for item in notices_data:
        h = generate_content_hash(
            item["route_number"],
            item["advisory_type"],
            item["affected_area"],
            item["start_date"],
            item["end_date"],
            item["description"]
        )
        cursor.execute("""
            INSERT INTO notices (
                source_id, external_notice_id, route_number, affected_area, advisory_type,
                severity, title, description, start_date, end_date, original_url,
                status, content_hash, version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item["source_id"],
            item["external_notice_id"],
            item["route_number"],
            item["affected_area"],
            item["advisory_type"],
            item["severity"],
            item["title"],
            item["description"],
            item["start_date"],
            item["end_date"],
            item["original_url"],
            item["status"],
            h,
            item["version"]
        ))
        notice_id = cursor.lastrowid

        # If notice is Revised, seed version 1 in notice_history
        if item["status"] == "Revised" and item["version"] == 2:
            cursor.execute("""
                INSERT INTO notice_history (
                    notice_id, version, route_number, advisory_type, affected_area,
                    description, start_date, end_date, status, change_summary, changed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                notice_id,
                1,
                item["route_number"],
                item["advisory_type"],
                item["affected_area"],
                "Initial Notice: Scheduled 2-day track inspection between Airport Station and Industrial Zone. Single line working from 11 PM to 4 AM.",
                item["start_date"],
                (today + timedelta(days=2)).isoformat(),
                "Active",
                "Work duration extended by 5 days and frequency reduced to 25 mins",
                (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
            ))

    # 4. Seed initial scraper logs
    cursor.execute("""
        INSERT INTO scraper_logs (source_name, source_url, status, items_found, items_new, items_updated, error_details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "Metro Transit Authority Alerts (Mock Portal)",
        "http://127.0.0.1:5000/mock-transit-portal",
        "SUCCESS",
        4,
        4,
        0,
        "Scraped successfully. All robots.txt directives complied with."
    ))

    cursor.execute("""
        INSERT INTO scraper_logs (source_name, source_url, status, items_found, items_new, items_updated, error_details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "City Bus Corporation Disruption Feed",
        "http://127.0.0.1:5000/mock-bus-feed",
        "SUCCESS",
        3,
        2,
        1,
        "Scraped successfully. Revision detected on notice ADV-2026-003."
    ))

    cursor.execute("""
        INSERT INTO scraper_logs (source_name, source_url, status, items_found, items_new, items_updated, error_details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "Regional Rail Planned Maintenance Service",
        "https://example-transport.gov/notices/restricted",
        "WARNING",
        0,
        0,
        0,
        "Source skipped: Path disallowed by robots.txt (User-agent: TransitNoticeBot)."
    ))

    conn.commit()
    conn.close()


def reset_and_reseed_db():
    """Drops tables and reinitializes with sample data for demonstration reset."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS notice_history")
    cursor.execute("DROP TABLE IF EXISTS notices")
    cursor.execute("DROP TABLE IF EXISTS routes")
    cursor.execute("DROP TABLE IF EXISTS sources")
    cursor.execute("DROP TABLE IF EXISTS scraper_logs")
    conn.commit()
    conn.close()
    init_db()
    seed_default_data()


if __name__ == "__main__":
    init_db()
    seed_default_data()
    print("TransitNotice Database initialized and seeded successfully.")
