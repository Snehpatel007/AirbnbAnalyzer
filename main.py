import argparse
import sys
import uvicorn
from config.settings import settings
from src.scheduler.runner import market_scheduler
from src.pipeline.collector import MarketCollector
from src.reporting.daily_report import DailyReportGenerator
from src.pipeline.seed_history import seed_30_day_history
from src.models.database import init_db


def main():
    parser = argparse.ArgumentParser(description="Ahmedabad Airbnb Daily Market Tracker CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Command: run-server (default)
    server_parser = subparsers.add_parser("run-server", help="Run the FastAPI web dashboard")
    server_parser.add_argument("--host", default=settings.host, help="Host interface")
    server_parser.add_argument("--port", type=int, default=settings.port, help="Port")
    server_parser.add_argument("--no-scheduler", action="store_true", help="Disable 9 AM scheduler")

    # Command: run-collection
    collect_parser = subparsers.add_parser("run-collection", help="Run on-demand market collection")
    collect_parser.add_argument("--date", help="Observation date (YYYY-MM-DD)", default=None)
    collect_parser.add_argument("--provider", help="Provider override", default=None)
    collect_parser.add_argument("--fetch-calendars", action="store_true", help="Fetch 275 individual calendars (bypassed by default to protect IP)")

    # Command: generate-report
    report_parser = subparsers.add_parser("generate-report", help="Generate 9 AM daily intelligence report")
    report_parser.add_argument("--date", help="Observation date (YYYY-MM-DD)", default=None)

    # Command: seed-history
    seed_parser = subparsers.add_parser("seed-history", help="Seed 30 days of past daily observations")
    seed_parser.add_argument("--days", type=int, default=30, help="Days to seed")
    seed_parser.add_argument("--end-date", default="2026-10-04", help="End date (YYYY-MM-DD)")

    # Command: update-auth
    auth_parser = subparsers.add_parser("update-auth", help="Update Airbnb authentication/session tokens or auto-bootstrap")
    auth_parser.add_argument("--curl", help="Raw DevTools curl command string", default=None)
    auth_parser.add_argument("--bootstrap", action="store_true", help="Auto-bootstrap fresh guest session from Airbnb")

    args = parser.parse_args()

    init_db()

    command = args.command or "run-server"

    if command == "run-server":
        if getattr(args, "no_scheduler", False):
            settings.scheduler_enabled = False
        print(f"🚀 Starting Ahmedabad Airbnb Daily Market Tracker on http://{args.host}:{args.port}")
        uvicorn.run("src.web.app:app", host=args.host, port=args.port, reload=False)

    elif command == "run-collection":
        collector = MarketCollector(
            observation_date=args.date,
            provider_name=args.provider,
            fetch_individual_calendars=getattr(args, "fetch_calendars", False),
        )
        res = collector.run()
        print("✅ Daily Collection Result:")
        for k, v in res.items():
            print(f"  {k}: {v}")

    elif command == "generate-report":
        gen = DailyReportGenerator()
        rep = gen.generate_report(args.date)
        print(rep)

    elif command == "seed-history":
        seed_30_day_history(end_date_str=args.end_date, days=args.days)

    elif command == "update-auth":
        from src.providers.session_manager import session_manager
        if args.curl:
            res = session_manager.update_from_curl(args.curl)
            print(f"✅ Successfully updated Airbnb session from curl ({len(res.get('cookies', {}))} cookies extracted).")
        else:
            res = session_manager.bootstrap_guest_session()
            print(f"✅ Successfully bootstrapped guest session ({len(res.get('cookies', {}))} cookies extracted).")


if __name__ == "__main__":
    main()
