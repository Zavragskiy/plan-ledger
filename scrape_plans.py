"""Совместимость: `python scrape_plans.py` → `plan-scrape`. Логика в planlib.cli.scraper."""

from planlib.cli.scraper import main

if __name__ == "__main__":
    raise SystemExit(main())
