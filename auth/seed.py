"""
Seed script to create default admin user.
Run with: python -m auth.seed
"""
import asyncio
import uuid
from db import get_prisma, close_prisma
from auth.utils import hash_password
from datetime import datetime


async def seed_admin_user():
    """Create default admin user if it doesn't exist."""
    prisma = await get_prisma()
    
    admin_email = "admin@ltipms.com"
    admin_password = "l&tipms"
    
    # Check if admin already exists
    try:
        existing_user = await prisma.user.find_unique(
            where={"email": admin_email}
        )
        if existing_user:
            print(f"✅ Admin user already exists: {admin_email}")
            return existing_user
    except Exception as e:
        print(f"Note: Could not check for existing user: {e}")
    
    # Create admin user
    password_hash = hash_password(admin_password)
    user_id = str(uuid.uuid4())
    
    try:
        user = await prisma.user.create(
            data={
                "id": user_id,
                "name": "Admin",
                "email": admin_email,
                "passwordHash": password_hash,
                "systemRole": "ADMIN",
                "isActive": True,
                "createdAt": datetime.utcnow(),
                "updatedAt": datetime.utcnow()
            }
        )
        print(f"✅ Created admin user: {admin_email}")
        print(f"   Password: {admin_password}")
        return user
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        raise


async def main():
    try:
        await seed_admin_user()
    finally:
        await close_prisma()


if __name__ == "__main__":
    asyncio.run(main())
# #     asyncio.run(main())
