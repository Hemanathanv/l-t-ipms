"""
Seed script to create default admin user.
Run with: python -m auth.seed
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_prisma, close_prisma
from auth.utils import hash_password


async def seed_admin_user():
    """Create default admin user if it doesn't exist."""
    prisma = await get_prisma()
    
    admin_email = "admin@ltipms.com"
    admin_password = "l&tipms"
    
    # Check if admin already exists
    existing_user = await prisma.user.find_unique(
        where={"email": admin_email}
    )
    
    if existing_user:
        print(f"✅ Admin user already exists: {admin_email}")
        return existing_user
    
    # Create admin user
    password_hash = hash_password(admin_password)
    
    admin_user = await prisma.user.create(
        data={
            "name": "Admin",
            "email": admin_email,
            "passwordHash": password_hash,
            "systemRole": "ADMIN",
            "isActive": True,
        }
    )
    
    print(f"✅ Created admin user: {admin_email}")
    print(f"   Password: {admin_password}")
    
    return admin_user


async def main():
    try:
        await seed_admin_user()
    finally:
        await close_prisma()


if __name__ == "__main__":
    asyncio.run(main())
