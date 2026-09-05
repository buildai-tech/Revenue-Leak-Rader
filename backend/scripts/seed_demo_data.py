"""
Demo data seeder — seeds "GreenVista Realty Demo" with realistic data.

CRITICAL REQUIREMENT: This script seeds raw leads and lead_events and lets
the real detection/scoring/financial-engine pipeline run against them.
It does NOT hand-insert pre-computed leakage_events or financial_calculations.

A handful of leads are carried all the way through to CONFIRMED_RECOVERED_REVENUE
so the dashboard shows a non-zero confirmed recovery figure immediately.

Usage:
    cd backend
    python -m scripts.seed_demo_data
"""
from __future__ import annotations

import asyncio
import random
import uuid
import sys
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database import Base
from app.models import *  # Import all models

settings = get_settings()

DEMO_ORG_ID = uuid.UUID(settings.DEMO_ORG_ID)
NOW = datetime.now(timezone.utc)

# ── Seed Data ───────────────────────────────────────────────────────────

PROJECTS = [
    {"name": "Greenfield Heights", "city": "Bengaluru - Whitefield"},
    {"name": "Lakeview Residences", "city": "Bengaluru - Sarjapur Road"},
]

SALES_REPS = [
    {"name": "Priya Sharma", "email": "priya@greenvista.com", "phone": "9876543210", "is_active": True},
    {"name": "Rahul Mehta", "email": "rahul@greenvista.com", "phone": "9876543211", "is_active": True},
    {"name": "Anjali Desai", "email": "anjali@greenvista.com", "phone": "9876543212", "is_active": True},
    {"name": "Vikram Singh", "email": "vikram@greenvista.com", "phone": "9876543213", "is_active": True},
    {"name": "Sneha Patel", "email": "sneha@greenvista.com", "phone": "9876543214", "is_active": True},
    {"name": "Arjun Reddy", "email": "arjun@greenvista.com", "phone": "9876543215", "is_active": True},
    {"name": "Kavya Nair", "email": "kavya@greenvista.com", "phone": "9876543216", "is_active": True},
    {"name": "Rohan Gupta", "email": "rohan@greenvista.com", "phone": "9876543217", "is_active": True},
    {"name": "Divya Kumar", "email": "divya@greenvista.com", "phone": "9876543218", "is_active": True},
    {"name": "Arun Joshi", "email": "arun@greenvista.com", "phone": "9876543219", "is_active": True},
    {"name": "Meera Iyer", "email": "meera@greenvista.com", "phone": "9876543220", "is_active": True},
    {"name": "Sanjay Verma", "email": "sanjay@greenvista.com", "phone": "9876543221", "is_active": True},
    # Inactive reps (for assigned_to_inactive_rep rule)
    {"name": "Deepak Bhatt", "email": "deepak@greenvista.com", "phone": "9876543222", "is_active": False},
    {"name": "Nisha Rao", "email": "nisha@greenvista.com", "phone": "9876543223", "is_active": False},
    {"name": "Amit Kulkarni", "email": "amit@greenvista.com", "phone": "9876543224", "is_active": False},
]

FIRST_NAMES = [
    "Aarav", "Aditi", "Akash", "Ananya", "Arjun", "Bharathi", "Chandra", "Deepa",
    "Dhruv", "Esha", "Gaurav", "Harini", "Ishaan", "Jaya", "Karthik", "Lakshmi",
    "Manish", "Neha", "Om", "Pooja", "Rajesh", "Sakshi", "Tanvi", "Uday",
    "Varun", "Yamini", "Zara", "Nikhil", "Pallavi", "Suresh", "Ashwin", "Bhavya",
    "Chirag", "Durga", "Ganesh", "Himani", "Indira", "Jagdish", "Keerthana",
    "Lavanya", "Manoj", "Nandini", "Prabhu", "Radhika", "Srinivas", "Tulsi",
    "Umesh", "Vaishnavi", "Yogesh", "Aisha",
]

LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Kumar", "Reddy", "Nair", "Mehta", "Gupta",
    "Desai", "Iyer", "Joshi", "Verma", "Rao", "Kulkarni", "Bhatt", "Malhotra",
    "Agarwal", "Kapoor", "Menon", "Pillai", "Shah", "Bose", "Chatterjee",
    "Das", "Fernandes", "Gowda", "Hegde", "Iyengar", "Jain", "Khanna",
]

SOURCES = ["Website", "MagicBricks", "99acres", "Housing.com", "Walk-in",
           "Referral", "Facebook Ad", "Google Ad", "Instagram", "Broker"]

STATUSES = {
    "active": ["new", "contacted", "interested", "qualified", "followup", "in_progress", "negotiation"],
    "dead": ["dead", "closed", "lost", "not_interested"],
    "converted": ["converted"],
}

EVENT_TYPES_INBOUND = ["inbound_call", "inbound_message", "inbound_email", "site_visit", "walk_in"]
EVENT_TYPES_OUTBOUND = ["outbound_call", "outbound_message", "outbound_email", "followup"]


def random_phone() -> str:
    prefix = random.choice(["6", "7", "8", "9"])
    return prefix + "".join([str(random.randint(0, 9)) for _ in range(9)])


def random_budget() -> Decimal:
    """Bengaluru residential: ₹30L to ₹5Cr."""
    lakhs = random.choice([30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95,
                           100, 120, 150, 175, 200, 250, 300, 350, 400, 500])
    return Decimal(str(lakhs * 100000))


def random_date(days_back_min: int, days_back_max: int) -> datetime:
    days = random.randint(days_back_min, days_back_max)
    return NOW - timedelta(days=days, hours=random.randint(0, 23), minutes=random.randint(0, 59))


async def seed():
    engine_kwargs = {"echo": False}
    if "sqlite" not in settings.DATABASE_URL:
        engine_kwargs.update({"pool_pre_ping": True})
    engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # Check if already seeded
        from sqlalchemy import select, func
        result = await db.execute(
            select(func.count()).select_from(Organization).where(Organization.id == DEMO_ORG_ID)
        )
        if result.scalar() > 0:
            print("Demo data already seeded. To re-seed, drop and recreate the database.")
            print("  docker compose down -v && docker compose up -d")
            print("  alembic upgrade head")
            print("  python -m scripts.seed_demo_data")
            return

        print("🌱 Seeding demo data for GreenVista Realty Demo...")

        # 1. Organization
        org = Organization(
            id=DEMO_ORG_ID,
            name="GreenVista Realty Demo",
            is_demo=True,
        )
        db.add(org)
        await db.flush()
        print(f"  ✓ Organization: {org.name}")

        # 2. Projects
        project_ids = []
        for p in PROJECTS:
            project = Project(
                organization_id=DEMO_ORG_ID,
                name=p["name"],
                city=p["city"],
            )
            db.add(project)
            await db.flush()
            project_ids.append(project.id)
            print(f"  ✓ Project: {project.name} ({project.city})")

        # 3. Sales Reps
        rep_ids = {"active": [], "inactive": []}
        for r in SALES_REPS:
            rep = SalesRep(
                organization_id=DEMO_ORG_ID,
                name=r["name"],
                email=r["email"],
                phone=r["phone"],
                is_active=r["is_active"],
            )
            db.add(rep)
            await db.flush()
            if r["is_active"]:
                rep_ids["active"].append(rep.id)
            else:
                rep_ids["inactive"].append(rep.id)
        print(f"  ✓ Sales Reps: {len(SALES_REPS)} ({len(rep_ids['inactive'])} inactive)")

        # 4. Generate 2000+ Leads with realistic distributions
        all_lead_ids = []
        lead_objects = []
        duplicate_phones = {}  # phone → count, for identity resolution testing

        total_leads = 2100
        print(f"  ⏳ Generating {total_leads} leads...")

        for i in range(total_leads):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            name = f"{first} {last}"

            # ~5% duplicates (same phone, different spelling)
            if i > 50 and random.random() < 0.05 and duplicate_phones:
                phone = random.choice(list(duplicate_phones.keys()))
                # Slightly different name to exercise identity resolution
                name_variants = [f"{first} {last}", f"{first[0]}. {last}", f"{first} {last} "]
                name = random.choice(name_variants)
            else:
                phone = random_phone()
                if random.random() < 0.1:
                    duplicate_phones[phone] = True

            # Determine lead type distribution
            roll = random.random()
            if roll < 0.12:
                # Dead but recently engaged (for dead_but_recently_engaged rule)
                status = random.choice(["dead", "closed", "lost"])
                created_at = random_date(60, 180)
                category = "dead_engaged"
            elif roll < 0.20:
                # Assigned to inactive rep (for assigned_to_inactive_rep rule)
                status = random.choice(["new", "contacted", "interested"])
                created_at = random_date(10, 90)
                category = "inactive_rep"
            elif roll < 0.30:
                # No follow-up (for no_followup rule)
                status = random.choice(["new", "contacted"])
                created_at = random_date(8, 60)
                category = "no_followup"
            elif roll < 0.38:
                # High value, poor follow-up
                status = random.choice(["interested", "qualified", "contacted"])
                created_at = random_date(14, 90)
                category = "high_value"
            elif roll < 0.45:
                # Never contacted (for response leakage)
                status = "new"
                created_at = random_date(3, 45)
                category = "never_contacted"
            elif roll < 0.55:
                # Slow response (for response leakage)
                status = random.choice(["contacted", "interested", "followup"])
                created_at = random_date(14, 120)
                category = "slow_response"
            elif roll < 0.08 + 0.55:
                # Converted (success cases)
                status = "converted"
                created_at = random_date(30, 180)
                category = "converted"
            else:
                # Normal active leads
                status = random.choice(STATUSES["active"])
                created_at = random_date(1, 120)
                category = "normal"

            # Assign reps
            if category == "inactive_rep":
                sales_rep_id = random.choice(rep_ids["inactive"])
            else:
                sales_rep_id = random.choice(rep_ids["active"])

            # Budget — high for high_value category
            if category == "high_value":
                budget = Decimal(str(random.choice([5000000, 7500000, 10000000, 15000000, 20000000, 50000000])))
            else:
                budget = random_budget() if random.random() < 0.75 else None

            email = f"{first.lower()}.{last.lower()}{random.randint(1,99)}@gmail.com" if random.random() < 0.6 else None

            lead = Lead(
                organization_id=DEMO_ORG_ID,
                project_id=random.choice(project_ids),
                sales_rep_id=sales_rep_id,
                name=name,
                phone_normalized=phone,
                phone_raw=f"+91{phone}" if random.random() < 0.5 else f"0{phone}",
                email=email,
                status=status,
                status_raw=status,
                budget=budget,
                source=random.choice(SOURCES),
                created_at=created_at,
            )
            db.add(lead)
            await db.flush()
            all_lead_ids.append(lead.id)
            lead_objects.append((lead, category))

        print(f"  ✓ Leads created: {len(all_lead_ids)}")

        # 5. Generate Lead Events
        print("  ⏳ Generating lead events...")
        events_created = 0

        for lead, category in lead_objects:
            lead_created = lead.created_at

            # Always a "created" event
            db.add(LeadEvent(
                organization_id=DEMO_ORG_ID,
                lead_id=lead.id,
                event_type="created",
                event_payload={"source": lead.source},
                occurred_at=lead_created,
                source="seed",
            ))
            events_created += 1

            if category == "dead_engaged":
                # Mark as dead, then add recent inbound
                dead_time = lead_created + timedelta(days=random.randint(10, 30))
                db.add(LeadEvent(
                    organization_id=DEMO_ORG_ID, lead_id=lead.id,
                    event_type="status_change",
                    event_payload={"old_status": "contacted", "new_status": lead.status},
                    occurred_at=dead_time, source="seed",
                ))
                # Recent inbound engagement
                for _ in range(random.randint(1, 3)):
                    recent_time = NOW - timedelta(days=random.randint(1, 20))
                    db.add(LeadEvent(
                        organization_id=DEMO_ORG_ID, lead_id=lead.id,
                        event_type=random.choice(EVENT_TYPES_INBOUND),
                        event_payload={"note": "Customer re-engaged"},
                        occurred_at=recent_time, source="seed",
                    ))
                    events_created += 1

            elif category == "no_followup":
                # Only inbound, no outbound
                if random.random() < 0.5:
                    db.add(LeadEvent(
                        organization_id=DEMO_ORG_ID, lead_id=lead.id,
                        event_type=random.choice(EVENT_TYPES_INBOUND),
                        event_payload={"note": "Initial inquiry"},
                        occurred_at=lead_created + timedelta(hours=random.randint(1, 48)),
                        source="seed",
                    ))
                    events_created += 1

            elif category == "high_value":
                # Few outbound (< 3)
                for j in range(random.randint(0, 2)):
                    db.add(LeadEvent(
                        organization_id=DEMO_ORG_ID, lead_id=lead.id,
                        event_type=random.choice(EVENT_TYPES_OUTBOUND),
                        event_payload={"note": f"Follow-up attempt {j+1}"},
                        occurred_at=lead_created + timedelta(days=random.randint(1, 14)),
                        source="seed",
                    ))
                    events_created += 1
                # Inbound message (unresolved question)
                if random.random() < 0.6:
                    db.add(LeadEvent(
                        organization_id=DEMO_ORG_ID, lead_id=lead.id,
                        event_type="inbound_message",
                        event_payload={"note": "Customer asked about pricing"},
                        occurred_at=lead_created + timedelta(days=random.randint(3, 20)),
                        source="seed",
                    ))
                    events_created += 1

            elif category == "never_contacted":
                # No outbound events at all — only the created event
                pass

            elif category == "slow_response":
                # Outbound after delay
                delay_hours = random.choice([2, 4, 8, 24, 48, 72])
                db.add(LeadEvent(
                    organization_id=DEMO_ORG_ID, lead_id=lead.id,
                    event_type=random.choice(EVENT_TYPES_OUTBOUND),
                    event_payload={"note": "Delayed first contact"},
                    occurred_at=lead_created + timedelta(hours=delay_hours),
                    source="seed",
                ))
                events_created += 1
                # Some additional follow-ups
                for j in range(random.randint(1, 4)):
                    db.add(LeadEvent(
                        organization_id=DEMO_ORG_ID, lead_id=lead.id,
                        event_type=random.choice(EVENT_TYPES_OUTBOUND),
                        event_payload={"note": f"Follow-up {j+1}"},
                        occurred_at=lead_created + timedelta(days=random.randint(3, 30)),
                        source="seed",
                    ))
                    events_created += 1

            elif category == "converted":
                # Full journey: outbound + site visit + booking
                quick_response = lead_created + timedelta(minutes=random.randint(2, 30))
                db.add(LeadEvent(
                    organization_id=DEMO_ORG_ID, lead_id=lead.id,
                    event_type="outbound_call",
                    event_payload={"note": "Quick response"},
                    occurred_at=quick_response, source="seed",
                ))
                db.add(LeadEvent(
                    organization_id=DEMO_ORG_ID, lead_id=lead.id,
                    event_type="site_visit",
                    event_payload={"note": "Site visit completed"},
                    occurred_at=lead_created + timedelta(days=random.randint(3, 14)),
                    source="seed",
                ))
                db.add(LeadEvent(
                    organization_id=DEMO_ORG_ID, lead_id=lead.id,
                    event_type="status_change",
                    event_payload={"old_status": "qualified", "new_status": "converted"},
                    occurred_at=lead_created + timedelta(days=random.randint(14, 60)),
                    source="seed",
                ))
                events_created += 3

            else:
                # Normal — mixed events
                num_events = random.randint(1, 6)
                response_delay_min = random.choice([3, 5, 10, 15, 30, 60, 120, 240, 480])
                first_outbound = lead_created + timedelta(minutes=response_delay_min)
                db.add(LeadEvent(
                    organization_id=DEMO_ORG_ID, lead_id=lead.id,
                    event_type=random.choice(EVENT_TYPES_OUTBOUND),
                    event_payload={"note": "Initial contact"},
                    occurred_at=first_outbound, source="seed",
                ))
                events_created += 1
                for j in range(num_events - 1):
                    event_type = random.choice(EVENT_TYPES_INBOUND + EVENT_TYPES_OUTBOUND)
                    db.add(LeadEvent(
                        organization_id=DEMO_ORG_ID, lead_id=lead.id,
                        event_type=event_type,
                        event_payload={"note": f"Activity {j+1}"},
                        occurred_at=lead_created + timedelta(days=random.randint(1, 60)),
                        source="seed",
                    ))
                    events_created += 1

        await db.flush()
        print(f"  ✓ Lead events created: {events_created}")

        # 6. Commit raw data
        await db.commit()
        print("  ✓ Raw data committed")

    # 7. Run the real pipeline against the seeded data
    print("\n🔍 Running detection pipeline...")

    async with session_factory() as db:
        # Identity resolution
        from app.core.identity.resolver import resolve_identities
        merge_stats = await resolve_identities(db, DEMO_ORG_ID)
        print(f"  ✓ Identity resolution: {merge_stats}")
        await db.commit()

    async with session_factory() as db:
        # Leakage detection
        from app.services.leakage_service import detect_leakage_for_organization
        leakage_stats = await detect_leakage_for_organization(db, DEMO_ORG_ID)
        print(f"  ✓ Leakage detection: {leakage_stats}")
        await db.commit()

    # 8. Create some recommendations, interventions, and recovery outcomes
    print("\n📋 Creating sample recommendations and interventions...")

    async with session_factory() as db:
        from app.models.leakage_event import LeakageEvent
        from app.models.recommendation import Recommendation
        from app.models.intervention import Intervention
        from app.services.recovery_service import record_outcome

        # Get top leakage events
        from sqlalchemy import select
        result = await db.execute(
            select(LeakageEvent)
            .where(LeakageEvent.organization_id == DEMO_ORG_ID)
            .order_by(LeakageEvent.created_at.desc())
            .limit(30)
        )
        top_events = list(result.scalars().all())

        recommendations_created = 0
        interventions_created = 0

        for event in top_events[:20]:
            # Create recommendation
            from app.ai.recommendation_writer import generate_recommendation_copy
            lead = await db.get(Lead, event.source_entity_id)
            lead_context = {
                "lead_name": lead.name if lead else "Unknown",
                "status": lead.status or "unknown" if lead else "unknown",
                "budget": f"{float(lead.budget):,.0f}" if lead and lead.budget else "not disclosed",
                "project_name": "the project",
                "sales_rep_name": "the assigned representative",
            }

            playbook_key, title, copy = generate_recommendation_copy(event.category, lead_context)

            rec = Recommendation(
                organization_id=DEMO_ORG_ID,
                leakage_event_id=event.id,
                playbook_key=playbook_key,
                generated_copy=copy,
                generated_by="template",
            )
            db.add(rec)
            await db.flush()
            recommendations_created += 1

            # Create intervention for some
            if random.random() < 0.7:
                active_rep_name = random.choice([r["name"] for r in SALES_REPS if r["is_active"]])
                intervention = Intervention(
                    organization_id=DEMO_ORG_ID,
                    recommendation_id=rec.id,
                    assigned_rep_name=active_rep_name,
                    status=random.choice(["pending", "contacted", "in_progress", "contacted"]),
                )
                db.add(intervention)
                await db.flush()
                interventions_created += 1

                # Record outcomes for some closed interventions
                if random.random() < 0.3 and lead and lead.budget:
                    intervention.status = "closed"
                    await db.flush()

                    outcome_type = random.choice(["converted", "converted", "re_engaged", "not_interested"])
                    booking_amount = lead.budget if outcome_type == "converted" else None

                    await record_outcome(
                        db=db,
                        organization_id=DEMO_ORG_ID,
                        intervention_id=intervention.id,
                        outcome_type=outcome_type,
                        booking_amount_inr=booking_amount,
                        evidence={"source": "seed_script", "note": "Demo recovery outcome"},
                    )

        await db.commit()
        print(f"  ✓ Recommendations: {recommendations_created}")
        print(f"  ✓ Interventions: {interventions_created}")

    print("\n✅ Demo data seeding complete!")
    print("   Start the backend and frontend to see the dashboard.")

    await engine.dispose()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(seed())
