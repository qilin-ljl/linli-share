"""Replenish future handover times for seeded local-demo listings."""

import os
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)

from sqlmodel import Session, select  # noqa: E402

from database import engine  # noqa: E402
from models import Community  # noqa: E402
from seed import ensure_future_demo_slots  # noqa: E402


def main() -> None:
    with Session(engine) as session:
        community = session.exec(select(Community).where(Community.name == "绿荫花园小区")).first()
        if community:
            added = ensure_future_demo_slots(session, community)
            print(f"Demo handover times refreshed: {added} added.")


if __name__ == "__main__":
    main()
