from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.models.database import Listing, CalendarObservation, DailyMarketMetric
from config.settings import settings, load_market_config


class DailyAggregator:
    """
    Computes deterministic market metrics for:
    1. Each configured Ahmedabad area
    2. Ahmedabad overall (City-wide aggregate strictly of configured areas)
    """

    def __init__(self, db: Session, observation_date: str):
        self.db = db
        self.observation_date = observation_date

    def _get_past_metric(self, area: str, days_ago: int) -> Optional[DailyMarketMetric]:
        try:
            curr_dt = datetime.strptime(self.observation_date, "%Y-%m-%d")
            past_date = (curr_dt - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            return (
                self.db.query(DailyMarketMetric)
                .filter(DailyMarketMetric.area == area, DailyMarketMetric.observation_date == past_date)
                .first()
            )
        except Exception:
            return None

    def calculate_for_area(
        self, area: str, expected_listings: int, observed_listings: int
    ) -> DailyMarketMetric:
        """
        Calculates daily market metrics for a specific area, including
        the exact matrix for Tonight (1D), Next 2 Days (2D), Next 3 Days (3D), and Next 7 Days (7D).
        Example: in Sola with 3 properties: (3/7 + 1/7 + 6/7) = 10/21 occupancy.
        """
        # Calendar records for this area on observation_date
        records = (
            self.db.query(CalendarObservation)
            .join(Listing, CalendarObservation.listing_id == Listing.listing_id)
            .filter(
                Listing.area == area,
                CalendarObservation.observation_date == self.observation_date,
            )
            .all()
        )

        obs_dt = datetime.strptime(self.observation_date, "%Y-%m-%d")
        d1_dates = {self.observation_date}
        d2_dates = {(obs_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(2)}
        d3_dates = {(obs_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)}
        d7_dates = {(obs_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}

        def calc_window(dates_set):
            sub = [r for r in records if r.calendar_date in dates_set]
            total_n = len(sub)
            unavail_n = sum(1 for r in sub if r.status in ("unavailable", "blocked", "booked"))
            rate = round(unavail_n / total_n, 4) if total_n > 0 else 0.0
            prices = [r.price for r in sub if r.price is not None and r.price > 0]
            avg_adr = round(sum(prices) / len(prices), 2) if prices else 3200.0
            revpar = round(avg_adr * rate, 2)
            return total_n, unavail_n, rate, avg_adr, revpar

        n_tot_1d, n_unavail_1d, unavail_1d, adr_1d, revpar_1d = calc_window(d1_dates)
        n_tot_2d, n_unavail_2d, unavail_2d, adr_2d, revpar_2d = calc_window(d2_dates)
        n_tot_3d, n_unavail_3d, unavail_3d, adr_3d, revpar_3d = calc_window(d3_dates)
        n_tot_7d, n_unavail_7d, unavail_7d, adr_7d, revpar_7d = calc_window(d7_dates)

        available_nights_1d = max(0, n_tot_1d - n_unavail_1d)
        booked_nights_1d = sum(1 for r in records if r.calendar_date == self.observation_date and r.status == "booked")
        has_true_booked = any(r.status == "booked" for r in records if r.calendar_date == self.observation_date)
        booking_occ = round(booked_nights_1d / n_tot_1d, 4) if (has_true_booked and n_tot_1d > 0) else None

        # Coverage
        coverage = round(observed_listings / max(1, expected_listings), 4)
        status = "COMPLETE" if coverage >= 0.95 else "PARTIAL"

        # Trend lookups
        past_1d = self._get_past_metric(area, 1)
        past_7d = self._get_past_metric(area, 7)
        past_30d = self._get_past_metric(area, 30)

        change_1d_list = observed_listings - (past_1d.active_listings if past_1d else observed_listings)
        change_7d_list = observed_listings - (past_7d.active_listings if past_7d else observed_listings)
        change_30d_list = observed_listings - (past_30d.active_listings if past_30d else observed_listings)

        change_1d_unavail_pp = round((unavail_1d - (past_1d.observed_unavailability_rate if past_1d else unavail_1d)) * 100.0, 2)
        change_7d_unavail_pp = round((unavail_1d - (past_7d.observed_unavailability_rate if past_7d else unavail_1d)) * 100.0, 2)
        change_30d_unavail_pp = round((unavail_1d - (past_30d.observed_unavailability_rate if past_30d else unavail_1d)) * 100.0, 2)

        metric = DailyMarketMetric(
            observation_date=self.observation_date,
            area=area,
            active_listings=observed_listings,
            available_listing_nights=available_nights_1d,
            unavailable_listing_nights=n_unavail_1d,
            booked_listing_nights=booked_nights_1d,
            observed_unavailability_rate=unavail_1d,
            booking_occupancy=booking_occ,
            adr=adr_1d,
            revpar_proxy=revpar_1d,
            unavailability_1d=unavail_1d,
            unavailability_2d=unavail_2d,
            unavailability_3d=unavail_3d,
            unavailability_7d=unavail_7d,
            adr_1d=adr_1d,
            adr_2d=adr_2d,
            adr_3d=adr_3d,
            adr_7d=adr_7d,
            revpar_1d=revpar_1d,
            revpar_2d=revpar_2d,
            revpar_3d=revpar_3d,
            revpar_7d=revpar_7d,
            nights_total_1d=n_tot_1d,
            nights_unavail_1d=n_unavail_1d,
            nights_total_2d=n_tot_2d,
            nights_unavail_2d=n_unavail_2d,
            nights_total_3d=n_tot_3d,
            nights_unavail_3d=n_unavail_3d,
            nights_total_7d=n_tot_7d,
            nights_unavail_7d=n_unavail_7d,
            active_listing_change_1d=change_1d_list,
            active_listing_change_7d=change_7d_list,
            active_listing_change_30d=change_30d_list,
            unavailability_change_1d_pp=change_1d_unavail_pp,
            unavailability_change_7d_pp=change_7d_unavail_pp,
            unavailability_change_30d_pp=change_30d_unavail_pp,
            coverage_rate=coverage,
            status=status,
        )
        return metric

    def calculate_city_overall(
        self, area_metrics: List[DailyMarketMetric], expected_total: int, observed_total: int
    ) -> DailyMarketMetric:
        """
        Combines area metrics into the overall Ahmedabad city metric.
        RULE: City-wise calculation is strictly the aggregation of configured production
        areas only. No external or non-configured locations are ever included.
        """
        valid_configured_areas = set(load_market_config().areas)
        filtered_metrics = [m for m in area_metrics if m.area in valid_configured_areas]

        actual_active = sum(m.active_listings for m in filtered_metrics)
        observed_cnt = actual_active if actual_active > 0 else observed_total

        # 1D Horizon (Tonight)
        n_tot_1d = sum(
            m.nights_total_1d if m.nights_total_1d is not None
            else ((m.available_listing_nights or 0) + (m.unavailable_listing_nights or 0)) if (m.available_listing_nights is not None and m.unavailable_listing_nights is not None)
            else m.active_listings
            for m in filtered_metrics
        )
        n_unavail_1d = sum((m.nights_unavail_1d if m.nights_unavail_1d is not None else (m.unavailable_listing_nights or 0)) for m in filtered_metrics)
        city_unavail_1d = round(n_unavail_1d / n_tot_1d, 4) if n_tot_1d > 0 else 0.0

        # 2D Horizon (Next 2 Days)
        n_tot_2d = sum((m.nights_total_2d or (m.active_listings * 2)) for m in filtered_metrics)
        n_unavail_2d = sum((m.nights_unavail_2d or 0) for m in filtered_metrics)
        city_unavail_2d = round(n_unavail_2d / n_tot_2d, 4) if n_tot_2d > 0 else 0.0

        # 3D Horizon (Next 3 Days)
        n_tot_3d = sum((m.nights_total_3d or (m.active_listings * 3)) for m in filtered_metrics)
        n_unavail_3d = sum((m.nights_unavail_3d or 0) for m in filtered_metrics)
        city_unavail_3d = round(n_unavail_3d / n_tot_3d, 4) if n_tot_3d > 0 else 0.0

        # 7D Horizon (Next 7 Days, e.g. 10/21)
        n_tot_7d = sum((m.nights_total_7d or (m.active_listings * 7)) for m in filtered_metrics)
        n_unavail_7d = sum((m.nights_unavail_7d or 0) for m in filtered_metrics)
        city_unavail_7d = round(n_unavail_7d / n_tot_7d, 4) if n_tot_7d > 0 else 0.0

        # Weighted ADRs across 40 areas
        adr_1d = round(sum((m.adr_1d or m.adr) * m.active_listings for m in filtered_metrics) / observed_cnt, 2) if observed_cnt > 0 else 0.0
        adr_2d = round(sum((m.adr_2d or m.adr) * m.active_listings for m in filtered_metrics) / observed_cnt, 2) if observed_cnt > 0 else 0.0
        adr_3d = round(sum((m.adr_3d or m.adr) * m.active_listings for m in filtered_metrics) / observed_cnt, 2) if observed_cnt > 0 else 0.0
        adr_7d = round(sum((m.adr_7d or m.adr) * m.active_listings for m in filtered_metrics) / observed_cnt, 2) if observed_cnt > 0 else 0.0

        revpar_1d = round(adr_1d * city_unavail_1d, 2)
        revpar_2d = round(adr_2d * city_unavail_2d, 2)
        revpar_3d = round(adr_3d * city_unavail_3d, 2)
        revpar_7d = round(adr_7d * city_unavail_7d, 2)

        total_available = sum((m.available_listing_nights or 0) for m in filtered_metrics)
        if total_available == 0 and n_tot_1d > 0:
            total_available = max(0, n_tot_1d - n_unavail_1d)
        total_booked = sum((m.booked_listing_nights or 0) for m in filtered_metrics)
        has_booked = any(m.booking_occupancy is not None for m in filtered_metrics)
        city_booking_occ = round(total_booked / n_tot_1d, 4) if (has_booked and n_tot_1d > 0) else None

        coverage = round(observed_total / max(1, expected_total), 4)
        status = "COMPLETE" if coverage >= 0.95 else "PARTIAL"

        past_1d = self._get_past_metric("Ahmedabad", 1)
        past_7d = self._get_past_metric("Ahmedabad", 7)
        past_30d = self._get_past_metric("Ahmedabad", 30)

        change_1d_list = observed_total - (past_1d.active_listings if past_1d else observed_total)
        change_7d_list = observed_total - (past_7d.active_listings if past_7d else observed_total)
        change_30d_list = observed_total - (past_30d.active_listings if past_30d else observed_total)

        change_1d_unavail_pp = round((city_unavail_1d - (past_1d.observed_unavailability_rate if past_1d else city_unavail_1d)) * 100.0, 2)
        change_7d_unavail_pp = round((city_unavail_1d - (past_7d.observed_unavailability_rate if past_7d else city_unavail_1d)) * 100.0, 2)
        change_30d_unavail_pp = round((city_unavail_1d - (past_30d.observed_unavailability_rate if past_30d else city_unavail_1d)) * 100.0, 2)

        return DailyMarketMetric(
            observation_date=self.observation_date,
            area="Ahmedabad",
            active_listings=observed_cnt,
            available_listing_nights=total_available,
            unavailable_listing_nights=n_unavail_1d,
            booked_listing_nights=total_booked,
            observed_unavailability_rate=city_unavail_1d,
            booking_occupancy=city_booking_occ,
            adr=adr_1d,
            revpar_proxy=revpar_1d,
            unavailability_1d=city_unavail_1d,
            unavailability_2d=city_unavail_2d,
            unavailability_3d=city_unavail_3d,
            unavailability_7d=city_unavail_7d,
            adr_1d=adr_1d,
            adr_2d=adr_2d,
            adr_3d=adr_3d,
            adr_7d=adr_7d,
            revpar_1d=revpar_1d,
            revpar_2d=revpar_2d,
            revpar_3d=revpar_3d,
            revpar_7d=revpar_7d,
            nights_total_1d=n_tot_1d,
            nights_unavail_1d=n_unavail_1d,
            nights_total_2d=n_tot_2d,
            nights_unavail_2d=n_unavail_2d,
            nights_total_3d=n_tot_3d,
            nights_unavail_3d=n_unavail_3d,
            nights_total_7d=n_tot_7d,
            nights_unavail_7d=n_unavail_7d,
            active_listing_change_1d=change_1d_list,
            active_listing_change_7d=change_7d_list,
            active_listing_change_30d=change_30d_list,
            unavailability_change_1d_pp=change_1d_unavail_pp,
            unavailability_change_7d_pp=change_7d_unavail_pp,
            unavailability_change_30d_pp=change_30d_unavail_pp,
            coverage_rate=coverage,
            status=status,
        )
