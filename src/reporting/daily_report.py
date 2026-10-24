from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from src.models.database import SessionLocal, DailyMarketMetric


class DailyReportGenerator:
    """
    Generates the official daily 9 AM market intelligence report
    for Ahmedabad overall and each tracked area.
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self._owns_db = db is None

    def generate_report(self, observation_date: Optional[str] = None) -> str:
        date_str = observation_date or datetime.now().strftime("%Y-%m-%d")
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        date_formatted = dt.strftime("%d %b %Y")

        city_metric = (
            self.db.query(DailyMarketMetric)
            .filter(
                DailyMarketMetric.observation_date == date_str,
                DailyMarketMetric.area == "Ahmedabad",
            )
            .first()
        )

        area_metrics = (
            self.db.query(DailyMarketMetric)
            .filter(
                DailyMarketMetric.observation_date == date_str,
                DailyMarketMetric.area != "Ahmedabad",
            )
            .order_by(DailyMarketMetric.active_listings.desc())
            .all()
        )

        if not city_metric:
            return f"Ahmedabad Airbnb — {date_formatted}\n\nNo market snapshot found for {date_str}."

        # Overall section
        d7_pct = (
            f"{'+' if city_metric.active_listing_change_7d >= 0 else ''}"
            f"{(city_metric.active_listing_change_7d / max(1, city_metric.active_listings - city_metric.active_listing_change_7d)) * 100.0:.1f}%"
            if city_metric.active_listings > 0 else "0.0%"
        )
        d30_pct = (
            f"{'+' if city_metric.active_listing_change_30d >= 0 else ''}"
            f"{(city_metric.active_listing_change_30d / max(1, city_metric.active_listings - city_metric.active_listing_change_30d)) * 100.0:.1f}%"
            if city_metric.active_listings > 0 else "0.0%"
        )

        lines = [
            f"Ahmedabad Airbnb — {date_formatted}",
            "Filters: 2+ Bedrooms | 2+ Beds | Wi-Fi | Air Conditioned",
            "Tonight's Actual Observed Market",
            f"Observed Unavailability: {city_metric.observed_unavailability_rate * 100:.1f}%",
            f"ADR: ₹{city_metric.adr:,.0f}",
            f"Observed RevPAR Proxy: ₹{city_metric.revpar_proxy:,.0f}",
            f"Active Listings: {city_metric.active_listings:,}",
            f"7D Listing Change: {d7_pct} ({'+' if city_metric.active_listing_change_7d >= 0 else ''}{city_metric.active_listing_change_7d})",
            f"30D Listing Change: {d30_pct} ({'+' if city_metric.active_listing_change_30d >= 0 else ''}{city_metric.active_listing_change_30d})",
            f"Coverage: {city_metric.coverage_rate * 100:.1f}%",
            f"Status: {city_metric.status}",
            "",
            "Area Highlights",
            "",
        ]

        for m in area_metrics:
            chg7_sign = "+" if m.active_listing_change_7d >= 0 else ""
            lines.extend([
                m.area,
                f"Unavailability: {m.observed_unavailability_rate * 100:.1f}%",
                f"ADR: ₹{m.adr:,.0f}",
                f"RevPAR Proxy: ₹{m.revpar_proxy:,.0f}",
                f"Listings: {m.active_listings:,}",
                f"7D change: {chg7_sign}{m.active_listing_change_7d} listings",
                f"7D Unavailability shift: {m.unavailability_change_7d_pp:+.1f} pp",
                "",
            ])

        return "\n".join(lines)

    def close(self):
        if self._owns_db:
            self.db.close()
