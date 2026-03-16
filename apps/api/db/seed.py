import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def run_seed():
    conn = await asyncpg.connect(dsn=os.environ["DATABASE_URL"])
    try:
        # Upsert org
        org = await conn.fetchrow(
            """
            INSERT INTO organizations (name, slug)
            VALUES ($1, $2)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
            RETURNING id, name, slug
            """,
            "Acme Events",
            "acme-events",
        )

        # Upsert organizer
        organizer = await conn.fetchrow(
            """
            INSERT INTO users (org_id, email, display_name, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING id, email, role
            """,
            org["id"],
            "organizer@acme.com",
            "Alex",
            "organizer",
        )

        # Upsert participant
        participant = await conn.fetchrow(
            """
            INSERT INTO users (org_id, email, display_name, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (email) DO UPDATE SET display_name = EXCLUDED.display_name
            RETURNING id, email, role
            """,
            org["id"],
            "participant@acme.com",
            "Jamie",
            "participant",
        )

        print(f"Org:         {org['name']} -> {org['id']}")
        print(f"Organizer:   {organizer['email']} ({organizer['role']}) -> {organizer['id']}")
        print(f"Participant: {participant['email']} ({participant['role']}) -> {participant['id']}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_seed())
