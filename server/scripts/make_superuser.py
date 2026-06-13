#!/usr/bin/env python3
"""
Script to promote users to superuser status.
Usage: python scripts/make_superuser.py <email_or_uuid>
"""

import asyncio
import sys
import os
from uuid import UUID

# Add the src directory to Python path - handle both local and Docker environments
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
src_path = os.path.join(project_root, 'src')

# Add both possible paths
sys.path.insert(0, src_path)
sys.path.insert(0, project_root)

# Also try current working directory structure
if os.path.exists('/app/src'):
    sys.path.insert(0, '/app')
    sys.path.insert(0, '/app/src')

try:
    from src.core.database import postgres_engine, AsyncSessionLocal
    from src.repositories.users import UserRepository
except ImportError:
    sys.path.insert(0, '/app')
    from src.core.database import postgres_engine, AsyncSessionLocal
    from src.repositories.users import UserRepository


async def make_superuser(user_identifier: str):
    """Make a user a superuser by email or UUID"""
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        
        try:
            # Try to parse as UUID first, then treat as email
            user = None
            try:
                uuid_identifier = UUID(user_identifier)
                user = await user_repo.get_user(uuid_identifier)
                identifier_type = "UUID"
            except ValueError:
                # It's an email
                user = await user_repo.get_user_by_email(user_identifier)
                identifier_type = "email"
            
            if not user:
                print(f"❌ User not found with {identifier_type}: {user_identifier}")
                return False
            
            if user.is_superuser:
                print(f"✅ User {user.email or user.id} is already a superuser")
                return True
            
            # Update user to superuser
            from sqlalchemy import update
            from src.models.postgres.models import UserModel
            
            await session.execute(
                update(UserModel)
                .where(UserModel.id == user.id)
                .values(is_superuser=True)
            )
            
            await session.commit()
            
            print(f"✅ Successfully promoted user {user.email or user.id} to superuser")
            return True
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error promoting user: {str(e)}")
            return False


async def list_users():
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        
        try:
            from sqlalchemy.future import select
            from src.models.postgres.models import UserModel
            
            result = await session.execute(select(UserModel))
            users = result.scalars().all()
            
            if not users:
                print("No users found in the system")
                return
            
            print("📋 Users in the system:")
            print("-" * 80)
            print(f"{'Email':<30} {'UUID':<36} {'Verified':<10} {'Superuser':<10}")
            print("-" * 80)
            
            for user in users:
                email = user.email or "N/A"
                registered = "Yes" if user.is_verified else "No"
                superuser = "Yes" if user.is_superuser else "No"
                print(f"{email:<30} {str(user.id):<36} {registered:<10} {superuser:<10}")
                
        except Exception as e:
            print(f"❌ Error listing users: {str(e)}")


def print_usage():
    """Print usage instructions"""
    print("Usage:")
    print("  python scripts/make_superuser.py <email_or_uuid>  - Promote user to superuser")
    print("  python scripts/make_superuser.py --list           - List all users")
    print("  python scripts/make_superuser.py --help           - Show this help")
    print("\nExamples:")
    print("  python scripts/make_superuser.py user@example.com")
    print("  python scripts/make_superuser.py 123e4567-e89b-12d3-a456-426614174000")
    print("  python scripts/make_superuser.py --list")


async def main():
    if len(sys.argv) != 2:
        print_usage()
        sys.exit(1)
    
    arg = sys.argv[1]
    
    if arg in ['--help', '-h']:
        print_usage()
        sys.exit(0)
    elif arg in ['--list', '-l']:
        await list_users()
        sys.exit(0)
    else:
        success = await make_superuser(arg)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main()) 