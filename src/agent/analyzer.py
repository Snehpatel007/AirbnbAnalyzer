import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from src.models.database import SessionLocal, DailyMarketMetric, Listing
from config.settings import settings, load_market_config


class MarketAnalysisAgent:
    """
    Natural Language Analysis Agent that queries stored historical market metrics
    and generates grounded answers to investment & operational leasing queries.
    Never invents or fabricates data.
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self._owns_db = db is None

    def _get_latest_date(self) -> Optional[str]:
        latest = (
            self.db.query(DailyMarketMetric.observation_date)
            .order_by(desc(DailyMarketMetric.observation_date))
            .first()
        )
        return latest[0] if latest else None

    def get_latest_metrics(self) -> List[Dict]:
        latest_date = self._get_latest_date()
        if not latest_date:
            return []
        rows = (
            self.db.query(DailyMarketMetric)
            .filter(DailyMarketMetric.observation_date == latest_date)
            .all()
        )
        return [r.to_dict() for r in rows]

    def answer_query(self, query: str) -> Dict[str, Any]:
        """
        Interprets natural language queries using historical DB queries and facts.
        """
        q = query.lower()
        latest_date = self._get_latest_date()
        if not latest_date:
            return {
                "query": query,
                "answer": "No historical market observations found in the database. Please trigger a daily collection first.",
                "metrics_used": {},
                "sources": ["daily_market_metrics"],
            }

        all_metrics = self.get_latest_metrics()
        area_metrics = [m for m in all_metrics if m["area"] != "Ahmedabad"]
        city_metric = next((m for m in all_metrics if m["area"] == "Ahmedabad"), None)

        # 1. Compare Bopal vs Shilaj (or any two areas)
        cfg_areas = load_market_config().areas
        for a1 in cfg_areas:
            for a2 in cfg_areas:
                if a1 != a2:
                    match1 = (a1.lower() in q) or (a1.lower() == "south bopal" and "bopal" in q)
                    match2 = (a2.lower() in q) or (a2.lower() == "south bopal" and "bopal" in q)
                    if match1 and match2:
                        res = self._compare_two_areas(a1, a2, latest_date)
                        if "bopal" in q and a1 == "South Bopal":
                            res["answer"] = res["answer"].replace("South Bopal", "Bopal (South Bopal)")
                        return res

        # 2. Highest ADR
        if "highest adr" in q or "top adr" in q or "most expensive" in q:
            sorted_by_adr = sorted(area_metrics, key=lambda x: x["adr"], reverse=True)
            top = sorted_by_adr[0]
            answer = (
                f"**{top['area']}** currently commands the highest Average Daily Rate (ADR) in Ahmedabad at **₹{top['adr']:,.0f}**, "
                f"with an observed unavailability rate of {top['observed_unavailability_rate']*100:.1f}% "
                f"and an Observed RevPAR Proxy of ₹{top['revpar_proxy']:,.0f} across {top['active_listings']} active listings (as of {latest_date}).\n\n"
                f"**Top 3 Areas by ADR:**\n"
            )
            for idx, item in enumerate(sorted_by_adr[:3], 1):
                answer += f"{idx}. **{item['area']}**: ₹{item['adr']:,.0f} ADR | {item['observed_unavailability_rate']*100:.1f}% Unavailability | ₹{item['revpar_proxy']:,.0f} RevPAR\n"
            return {
                "query": query,
                "answer": answer,
                "metrics_used": {"top_area": top["area"], "adr": top["adr"], "date": latest_date},
                "sources": ["daily_market_metrics"],
            }

        # 3. Best combination of occupancy / unavailability, ADR and RevPAR
        if "best combination" in q or "highest revpar" in q or "best performance" in q or "best area" in q:
            sorted_by_revpar = sorted(area_metrics, key=lambda x: x["revpar_proxy"], reverse=True)
            best = sorted_by_revpar[0]
            answer = (
                f"For a lease-model Airbnb business, **{best['area']}** currently offers the strongest market fundamentals with the highest Observed RevPAR Proxy of **₹{best['revpar_proxy']:,.0f}**.\n\n"
                f"• **ADR:** ₹{best['adr']:,.0f}\n"
                f"• **Observed Unavailability Rate:** {best['observed_unavailability_rate']*100:.1f}%\n"
                f"• **Active Listings:** {best['active_listings']}\n"
                f"• **7-Day Unavailability Shift:** {best['unavailability_change_7d_pp']:+.1f} percentage points\n\n"
                f"**Full RevPAR Proxy Ranking (Snapshot: {latest_date}):**\n"
            )
            for idx, item in enumerate(sorted_by_revpar, 1):
                answer += f"{idx}. **{item['area']}**: ₹{item['revpar_proxy']:,.0f} RevPAR Proxy (ADR ₹{item['adr']:,.0f}, Unavailability {item['observed_unavailability_rate']*100:.1f}%)\n"
            return {
                "query": query,
                "answer": answer,
                "metrics_used": {"best_area": best["area"], "revpar_proxy": best["revpar_proxy"]},
                "sources": ["daily_market_metrics"],
            }

        # 4. Which area improved the most in last 30 days
        if "improved the most" in q or "growth" in q or "best improvement" in q:
            # Sort by 30D unavailability rate percentage points improvement
            sorted_by_growth = sorted(area_metrics, key=lambda x: x["unavailability_change_30d_pp"], reverse=True)
            top_growth = sorted_by_growth[0]
            answer = (
                f"**{top_growth['area']}** showed the largest improvement over the last 30 days, "
                f"with observed unavailability increasing by **{top_growth['unavailability_change_30d_pp']:+.1f} percentage points** "
                f"(current unavailability: {top_growth['observed_unavailability_rate']*100:.1f}%).\n\n"
                f"• **Current ADR:** ₹{top_growth['adr']:,.0f}\n"
                f"• **Current RevPAR Proxy:** ₹{top_growth['revpar_proxy']:,.0f}\n"
                f"• **30-Day Listing Supply Change:** {'+' if top_growth['active_listing_change_30d'] >= 0 else ''}{top_growth['active_listing_change_30d']} listings\n"
            )
            return {
                "query": query,
                "answer": answer,
                "metrics_used": {"top_growth_area": top_growth["area"], "change_30d_pp": top_growth["unavailability_change_30d_pp"]},
                "sources": ["daily_market_metrics"],
            }

        # 5. Increasing demand but decreasing supply
        if "increasing demand" in q or "decreasing supply" in q or "supply" in q and "demand" in q:
            divergent = [
                m for m in area_metrics
                if m["unavailability_change_7d_pp"] > 0 and m["active_listing_change_7d"] <= 0
            ]
            if not divergent:
                # Check 30D window
                divergent = [
                    m for m in area_metrics
                    if m["unavailability_change_30d_pp"] > 0 and m["active_listing_change_30d"] <= 0
                ]
            
            if divergent:
                div = divergent[0]
                answer = (
                    f"**{div['area']}** exhibits a favorable supply-demand squeeze for lease operators:\n\n"
                    f"• **Demand signal:** Observed unavailability increased by **{div['unavailability_change_7d_pp']:+.1f} pp** over 7 days.\n"
                    f"• **Supply signal:** Active listings changed by **{div['active_listing_change_7d']}** listings.\n"
                    f"• **Current ADR:** ₹{div['adr']:,.0f} | **RevPAR Proxy:** ₹{div['revpar_proxy']:,.0f}\n\n"
                    f"This indicates tightening inventory where new guest demand is absorbing available nights faster than new host supply is entering."
                )
            else:
                answer = "Currently, no tracked area exhibits an acute supply contraction alongside demand expansion in the 7-day window. Most areas have experienced steady supply growth."
            return {
                "query": query,
                "answer": answer,
                "metrics_used": {"candidates": [d["area"] for d in divergent]},
                "sources": ["daily_market_metrics"],
            }

        # 6. Specific Area Query (e.g. "Show me Ghuma", "Bopal status")
        for area in settings.market_config.areas:
            if area.lower() in q:
                return self._get_area_detailed_report(area, latest_date)

        # Default: Market Overview Summary
        if city_metric:
            answer = (
                f"**Ahmedabad Market Overview (as of {latest_date}):**\n\n"
                f"• **Total Active Listings:** {city_metric['active_listings']:,} ({'+' if city_metric['active_listing_change_7d'] >= 0 else ''}{city_metric['active_listing_change_7d']} in 7D)\n"
                f"• **Observed Unavailability Rate:** {city_metric['observed_unavailability_rate']*100:.1f}%\n"
                f"• **Average Daily Rate (ADR):** ₹{city_metric['adr']:,.0f}\n"
                f"• **Observed RevPAR Proxy:** ₹{city_metric['revpar_proxy']:,.0f}\n"
                f"• **Collection Coverage:** {city_metric['coverage_rate']*100:.1f}%\n\n"
                f"You can ask comparative questions such as:\n"
                f"- *'Compare Bopal vs Shilaj'*\n"
                f"- *'Which area has the highest ADR?'*\n"
                f"- *'Which area has improved the most in the last 30 days?'*\n"
                f"- *'Show me Ghuma's last 30 days'*."
            )
            return {
                "query": query,
                "answer": answer,
                "metrics_used": city_metric,
                "sources": ["daily_market_metrics"],
            }

        return {
            "query": query,
            "answer": "Unable to process query. Please ask about a tracked Ahmedabad area or market metric.",
            "metrics_used": {},
            "sources": ["daily_market_metrics"],
        }

    def _compare_two_areas(self, area1: str, area2: str, latest_date: str) -> Dict[str, Any]:
        m1 = (
            self.db.query(DailyMarketMetric)
            .filter(DailyMarketMetric.area == area1, DailyMarketMetric.observation_date == latest_date)
            .first()
        )
        m2 = (
            self.db.query(DailyMarketMetric)
            .filter(DailyMarketMetric.area == area2, DailyMarketMetric.observation_date == latest_date)
            .first()
        )
        if not m1 or not m2:
            return {
                "query": f"Compare {area1} vs {area2}",
                "answer": f"Incomplete data to compare {area1} and {area2}.",
                "metrics_used": {},
                "sources": ["daily_market_metrics"],
            }

        adr_diff = m1.adr - m2.adr
        revpar_diff = m1.revpar_proxy - m2.revpar_proxy
        unavail_diff_pp = (m1.observed_unavailability_rate - m2.observed_unavailability_rate) * 100.0

        answer = (
            f"### Head-to-Head Comparison: **{area1}** vs **{area2}** ({latest_date})\n\n"
            f"| Metric | {area1} | {area2} | Difference |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"| **Active Listings** | {m1.active_listings:,} | {m2.active_listings:,} | {m1.active_listings - m2.active_listings:+,} listings |\n"
            f"| **Observed Unavailability** | {m1.observed_unavailability_rate*100:.1f}% | {m2.observed_unavailability_rate*100:.1f}% | {unavail_diff_pp:+.1f} percentage points |\n"
            f"| **ADR** | ₹{m1.adr:,.0f} | ₹{m2.adr:,.0f} | ₹{adr_diff:+,.0f} |\n"
            f"| **Observed RevPAR Proxy** | ₹{m1.revpar_proxy:,.0f} | ₹{m2.revpar_proxy:,.0f} | ₹{revpar_diff:+,.0f} |\n"
            f"| **7-Day Supply Change** | {'+' if m1.active_listing_change_7d >= 0 else ''}{m1.active_listing_change_7d} | {'+' if m2.active_listing_change_7d >= 0 else ''}{m2.active_listing_change_7d} | — |\n"
            f"| **7-Day Unavailability Shift** | {m1.unavailability_change_7d_pp:+.1f} pp | {m2.unavailability_change_7d_pp:+.1f} pp | — |\n\n"
            f"**Strategic Takeaway:**\n"
            f"• **Higher RevPAR Proxy:** **{area1 if revpar_diff > 0 else area2}** yields higher revenue per available room night (+₹{abs(revpar_diff):,.0f}).\n"
            f"• **Pricing Power:** **{area1 if adr_diff > 0 else area2}** has higher rate premium (+₹{abs(adr_diff):,.0f} ADR).\n"
            f"• **Market Depth:** **{area1 if m1.active_listings > m2.active_listings else area2}** offers deeper supply liquidity with {max(m1.active_listings, m2.active_listings)} listings."
        )

        return {
            "query": f"Compare {area1} vs {area2}",
            "answer": answer,
            "metrics_used": {area1: m1.to_dict(), area2: m2.to_dict()},
            "sources": ["daily_market_metrics"],
        }

    def _get_area_detailed_report(self, area: str, latest_date: str) -> Dict[str, Any]:
        records = (
            self.db.query(DailyMarketMetric)
            .filter(DailyMarketMetric.area == area)
            .order_by(DailyMarketMetric.observation_date.desc())
            .limit(30)
            .all()
        )
        if not records:
            return {"query": area, "answer": f"No data for {area}.", "metrics_used": {}, "sources": []}

        latest = records[0]
        oldest = records[-1]
        
        days_span = len(records)
        answer = (
            f"### **{area}** Performance Analysis ({days_span} Days Observed)\n\n"
            f"• **Active Listings:** {latest.active_listings:,} ({'+' if latest.active_listing_change_7d >= 0 else ''}{latest.active_listing_change_7d} in 7D | {'+' if latest.active_listing_change_30d >= 0 else ''}{latest.active_listing_change_30d} in 30D)\n"
            f"• **Observed Unavailability Rate:** {latest.observed_unavailability_rate*100:.1f}%\n"
            f"• **7-Day Shift:** {latest.unavailability_change_7d_pp:+.1f} percentage points\n"
            f"• **30-Day Shift:** {latest.unavailability_change_30d_pp:+.1f} percentage points\n"
            f"• **Current ADR:** ₹{latest.adr:,.0f} (vs ₹{oldest.adr:,.0f} {days_span} days ago)\n"
            f"• **Observed RevPAR Proxy:** ₹{latest.revpar_proxy:,.0f} (vs ₹{oldest.revpar_proxy:,.0f} {days_span} days ago)\n"
            f"• **Observation Coverage:** {latest.coverage_rate*100:.1f}%\n\n"
            f"**Lease Model Viability Assessment:**\n"
            f"At ₹{latest.revpar_proxy:,.0f} RevPAR proxy, a typical property in {area} generates an estimated gross monthly revenue of approximately "
            f"**₹{latest.revpar_proxy * 30:,.0f}**. Subtracting standard lease rent and operating expenses yields the baseline margin for acquisition."
        )

        return {
            "query": f"Show {area}",
            "answer": answer,
            "metrics_used": latest.to_dict(),
            "sources": ["daily_market_metrics"],
        }

    def close(self):
        if self._owns_db:
            self.db.close()
