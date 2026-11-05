"""
TransitNotice - Web Scraping & Change Detection Module
Collects official transit alerts, parses HTML using BeautifulSoup, checks robots.txt permissions,
avoids duplicates, detects revisions, and updates SQLite database with complete history.
"""

import urllib.robotparser
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
from database import (
    get_db_connection,
    generate_content_hash,
    update_expired_statuses
)

# Polite user agent identifying the college project crawler
USER_AGENT = "TransitNoticeBot/1.0 (+http://localhost:5000/robots.txt; College Mini Project)"


def check_robots_permission(target_url, custom_robots_url=None):
    """
    Checks robots.txt for the given target URL using urllib.robotparser.
    Returns (is_allowed: bool, reason: str).
    """
    try:
        parsed = urlparse(target_url)
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid URL structure."

        # If it's our internal localhost mock portal, allow it explicitly
        if "127.0.0.1" in parsed.netloc or "localhost" in parsed.netloc:
            return True, "Internal mock source - permitted for demonstration."

        robots_url = custom_robots_url or f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        
        # Polite fetch with timeout
        resp = requests.get(robots_url, headers={"User-Agent": USER_AGENT}, timeout=5)
        if resp.status_code in [401, 403]:
            return False, f"Access to robots.txt forbidden (HTTP {resp.status_code})."
        elif resp.status_code == 404:
            # Standard practice: if no robots.txt exists, crawling is typically allowed
            return True, "No robots.txt found (HTTP 404) - crawling default allowed."
        elif resp.status_code == 200:
            rp.parse(resp.text.splitlines())
            allowed = rp.can_fetch(USER_AGENT, target_url) or rp.can_fetch("*", target_url)
            if allowed:
                return True, "Permitted by robots.txt directives."
            else:
                return False, "Disallowed by robots.txt policy for this user-agent."
        else:
            return False, f"Unexpected robots.txt response (HTTP {resp.status_code})."
    except requests.RequestException as e:
        return False, f"Unable to reach robots.txt: {str(e)}"
    except Exception as e:
        return False, f"Robots check error: {str(e)}"


def parse_notice_card(card_element):
    """
    Extracts structured fields from an HTML card or table row element using BeautifulSoup.
    Works with standard class hooks (.notice-card, .notice-row, etc.).
    """
    try:
        # 1. External Notice ID
        ext_id = (
            card_element.get("data-notice-id")
            or (card_element.select_one(".notice-id") and card_element.select_one(".notice-id").get_text(strip=True))
            or f"AUTO-{datetime.now().strftime('%Y%m%d%H%M%S%f')[:16]}"
        )

        # 2. Route Number
        route_el = card_element.select_one(".route-badge, .route-number, .badge-route")
        route_number = route_el.get_text(strip=True) if route_el else "ALL"

        # 3. Advisory Type (Diversion, Delay, Maintenance, Cancellation, Special Service)
        type_el = card_element.select_one(".advisory-type, .type-tag, .notice-type")
        advisory_type = type_el.get_text(strip=True) if type_el else "Advisory"
        # Standardize advisory type casing
        type_mapping = {
            "diversion": "Diversion",
            "detour": "Diversion",
            "delay": "Delay",
            "delays": "Delay",
            "maintenance": "Maintenance",
            "cancellation": "Cancellation",
            "cancelled": "Cancellation",
            "special": "Special Service",
            "special service": "Special Service"
        }
        advisory_type = type_mapping.get(advisory_type.lower(), advisory_type.title())

        # 4. Severity (Low, Medium, High, Critical)
        sev_el = card_element.select_one(".severity-badge, .badge-severity")
        severity = sev_el.get_text(strip=True).title() if sev_el else "Medium"
        if severity not in ["Low", "Medium", "High", "Critical"]:
            severity = "Medium"

        # 5. Affected Area / Station
        area_el = card_element.select_one(".affected-area, .station-affected, .location")
        affected_area = area_el.get_text(strip=True) if area_el else "System-wide"

        # 6. Title
        title_el = card_element.select_one(".notice-title, h3, h4, .title")
        title = title_el.get_text(strip=True) if title_el else "Service Announcement"

        # 7. Description
        desc_el = card_element.select_one(".notice-description, .description, p")
        description = desc_el.get_text(strip=True) if desc_el else "No detailed description provided."

        # 8. Start and End Dates (format: YYYY-MM-DD)
        start_el = card_element.select_one(".start-date, [data-start-date]")
        start_date_val = (
            start_el.get("data-start-date") if (start_el and start_el.get("data-start-date"))
            else (start_el.get_text(strip=True) if start_el else date.today().isoformat())
        )

        end_el = card_element.select_one(".end-date, [data-end-date]")
        end_date_val = (
            end_el.get("data-end-date") if (end_el and end_el.get("data-end-date"))
            else (end_el.get_text(strip=True) if end_el else date.today().isoformat())
        )

        # 9. Source Link / Original URL
        link_el = card_element.select_one("a[href]")
        original_url = link_el["href"] if link_el else ""

        # 10. Status in markup if present
        status_el = card_element.select_one(".notice-status, .badge-status")
        initial_status = status_el.get_text(strip=True).title() if status_el else "Active"
        if initial_status not in ["Active", "Expired", "Revised", "Cancelled"]:
            initial_status = "Active"

        return {
            "external_notice_id": ext_id,
            "route_number": route_number,
            "affected_area": affected_area,
            "advisory_type": advisory_type,
            "severity": severity,
            "title": title,
            "description": description,
            "start_date": start_date_val,
            "end_date": end_date_val,
            "original_url": original_url,
            "status": initial_status
        }
    except Exception as e:
        print(f"Error parsing notice card element: {e}")
        return None


def scrape_source(source_id=None, source_url=None):
    """
    Executes scraper on a single source or active sources in database.
    Performs HTTP GET, BeautifulSoup parsing, change detection, history archiving, and logging.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if source_id:
        cursor.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
        sources = cursor.fetchall()
    elif source_url:
        cursor.execute("SELECT * FROM sources WHERE url = ?", (source_url,))
        sources = cursor.fetchall()
        if not sources:
            # Ephemeral source run
            sources = [{"id": None, "name": "Custom Test Target", "url": source_url, "robots_url": None, "is_active": 1}]
    else:
        cursor.execute("SELECT * FROM sources WHERE is_active = 1")
        sources = cursor.fetchall()

    overall_results = []

    for src in sources:
        src_id = src["id"]
        src_name = src["name"]
        url = src["url"]
        robots_url = src.get("robots_url") if isinstance(src, dict) or hasattr(src, 'keys') else None

        items_found = 0
        items_new = 0
        items_updated = 0
        error_details = None
        status_flag = "SUCCESS"

        # Step 1: Robots.txt compliance check
        is_allowed, robot_reason = check_robots_permission(url, robots_url)
        if not is_allowed:
            status_flag = "WARNING"
            error_details = f"Robots.txt check prevented scraping: {robot_reason}"
            if src_id:
                cursor.execute("""
                    UPDATE sources
                    SET last_checked_at = CURRENT_TIMESTAMP, last_status = 'Restricted', error_message = ?
                    WHERE id = ?
                """, (error_details, src_id))
            
            cursor.execute("""
                INSERT INTO scraper_logs (source_name, source_url, status, items_found, items_new, items_updated, error_details)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (src_name, url, status_flag, 0, 0, 0, error_details))
            conn.commit()

            overall_results.append({
                "source_id": src_id,
                "source_name": src_name,
                "status": status_flag,
                "items_found": 0,
                "items_new": 0,
                "items_updated": 0,
                "message": error_details
            })
            continue

        # Step 2: Fetch Page Content via Requests
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=8)
            if resp.status_code != 200:
                raise requests.RequestException(f"HTTP status code {resp.status_code}")

            # Step 3: Parse HTML via BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # Look for notice cards / containers
            card_elements = soup.select(".transit-notice-card, tr.notice-row, .notice-item, .alert-box")

            for card in card_elements:
                parsed = parse_notice_card(card)
                if not parsed:
                    continue

                items_found += 1
                new_hash = generate_content_hash(
                    parsed["route_number"],
                    parsed["advisory_type"],
                    parsed["affected_area"],
                    parsed["start_date"],
                    parsed["end_date"],
                    parsed["description"]
                )

                # Step 4: Check if already exists in SQLite
                cursor.execute("""
                    SELECT * FROM notices
                    WHERE external_notice_id = ? OR (route_number = ? AND title = ?)
                """, (parsed["external_notice_id"], parsed["route_number"], parsed["title"]))
                existing = cursor.fetchone()

                if not existing:
                    # Brand New Announcement -> Insert
                    cursor.execute("""
                        INSERT INTO notices (
                            source_id, external_notice_id, route_number, affected_area,
                            advisory_type, severity, title, description, start_date,
                            end_date, original_url, status, content_hash, version
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """, (
                        src_id,
                        parsed["external_notice_id"],
                        parsed["route_number"],
                        parsed["affected_area"],
                        parsed["advisory_type"],
                        parsed["severity"],
                        parsed["title"],
                        parsed["description"],
                        parsed["start_date"],
                        parsed["end_date"],
                        parsed["original_url"] or url,
                        parsed["status"],
                        new_hash
                    ))
                    items_new += 1
                else:
                    # Announcement exists -> Check for changes / revision detection
                    old_hash = existing["content_hash"]
                    if old_hash != new_hash:
                        # REVISION DETECTED: Archive prior version into notice_history
                        old_version = existing["version"]
                        diff_notes = []
                        if existing["description"] != parsed["description"]:
                            diff_notes.append("Description modified")
                        if existing["end_date"] != parsed["end_date"]:
                            diff_notes.append(f"End date updated from {existing['end_date']} to {parsed['end_date']}")
                        if existing["affected_area"] != parsed["affected_area"]:
                            diff_notes.append("Affected area scope altered")
                        if existing["advisory_type"] != parsed["advisory_type"]:
                            diff_notes.append(f"Type changed to {parsed['advisory_type']}")
                        summary = "; ".join(diff_notes) if diff_notes else "General advisory revision"

                        cursor.execute("""
                            INSERT INTO notice_history (
                                notice_id, version, route_number, advisory_type,
                                affected_area, description, start_date, end_date,
                                status, change_summary, changed_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """, (
                            existing["id"],
                            old_version,
                            existing["route_number"],
                            existing["advisory_type"],
                            existing["affected_area"],
                            existing["description"],
                            existing["start_date"],
                            existing["end_date"],
                            existing["status"],
                            summary
                        ))

                        # Update notice with new revision
                        cursor.execute("""
                            UPDATE notices
                            SET affected_area = ?, advisory_type = ?, severity = ?,
                                title = ?, description = ?, start_date = ?, end_date = ?,
                                original_url = ?, status = 'Revised', content_hash = ?,
                                version = version + 1, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (
                            parsed["affected_area"],
                            parsed["advisory_type"],
                            parsed["severity"],
                            parsed["title"],
                            parsed["description"],
                            parsed["start_date"],
                            parsed["end_date"],
                            parsed["original_url"] or url,
                            new_hash,
                            existing["id"]
                        ))
                        items_updated += 1

            # Update Source status
            if src_id:
                cursor.execute("""
                    UPDATE sources
                    SET last_checked_at = CURRENT_TIMESTAMP, last_status = 'Success', error_message = NULL
                    WHERE id = ?
                """, (src_id,))

            error_details = f"Scrape completed cleanly. Found {items_found} notices ({items_new} new, {items_updated} revised)."

        except requests.RequestException as req_err:
            status_flag = "FAILED"
            error_details = f"Source connection error: {str(req_err)}"
            if src_id:
                cursor.execute("""
                    UPDATE sources
                    SET last_checked_at = CURRENT_TIMESTAMP, last_status = 'Error', error_message = ?
                    WHERE id = ?
                """, (error_details, src_id))

        except Exception as gen_err:
            status_flag = "FAILED"
            error_details = f"HTML Parsing error: {str(gen_err)}"
            if src_id:
                cursor.execute("""
                    UPDATE sources
                    SET last_checked_at = CURRENT_TIMESTAMP, last_status = 'Error', error_message = ?
                    WHERE id = ?
                """, (error_details, src_id))

        # Log this scrape execution
        cursor.execute("""
            INSERT INTO scraper_logs (source_name, source_url, status, items_found, items_new, items_updated, error_details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (src_name, url, status_flag, items_found, items_new, items_updated, error_details))
        conn.commit()

        overall_results.append({
            "source_id": src_id,
            "source_name": src_name,
            "status": status_flag,
            "items_found": items_found,
            "items_new": items_new,
            "items_updated": items_updated,
            "message": error_details
        })

    # Auto-update any notices that have expired based on today's date
    update_expired_statuses()

    conn.close()
    return overall_results


if __name__ == "__main__":
    print("Testing Scraper module directly...")
    # Test robots check on simulated URL
    allowed, reason = check_robots_permission("http://127.0.0.1:5000/mock-transit-portal")
    print(f"Robots check result: {allowed} ({reason})")
