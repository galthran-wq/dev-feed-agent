#!/usr/bin/env python3
"""
Script to create registered users.
Usage: python scripts/create_user.py <email> <password>
"""

import asyncio
import sys
import os

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
    from src.core.auth import get_password_hash
except ImportError:
    sys.path.insert(0, '/app')
    from src.core.database import postgres_engine, AsyncSessionLocal
    from src.repositories.users import UserRepository
    from src.core.auth import get_password_hash


async def create_user(email: str, password: str):
    """Create a new registered user"""
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        
        try:
            # Validate password length
            if len(password) < 6:
                print(f"❌ Error: Password must be at least 6 characters long")
                return False
            
            # Hash the password
            password_hash = get_password_hash(password)
            
            # Create the user
            user = await user_repo.create_registered_user(email, password_hash)
            
            print(f"✅ Successfully created user:")
            print(f"   Email: {user.email}")
            print(f"   UUID: {user.id}")
            print(f"   Verified: {'Yes' if user.is_verified else 'No'}")
            print(f"   Superuser: {'Yes' if user.is_superuser else 'No'}")
            
            return True
            
        except ValueError as e:
            if "Email already registered" in str(e):
                print(f"❌ Error: User with email '{email}' already exists")
            else:
                print(f"❌ Error: {str(e)}")
            return False
        except Exception as e:
            print(f"❌ Error creating user: {str(e)}")
            return False


async def list_users():
    """List all users in the database"""
    async with AsyncSessionLocal() as session:
        user_repo = UserRepository(session)
        
        try:
            # Get all users
            from sqlalchemy import select
            from src.models.postgres.models import UserModel
            
            result = await session.execute(select(UserModel))
            users = result.scalars().all()
            
            if not users:
                print("No users found in the database.")
                return
            
            print(f"Found {len(users)} user(s):")
            print()
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
    print("  python scripts/create_user.py <email> <password>  - Create a new registered user")
    print("  python scripts/create_user.py --list              - List all users")
    print("  python scripts/create_user.py --help              - Show this help")
    print("\nExamples:")
    print("  python scripts/create_user.py user@example.com mypassword123")
    print("  python scripts/create_user.py admin@company.com securepass456")
    print("  python scripts/create_user.py --list")
    print("\nNote:")
    print("  - Password must be at least 6 characters long")
    print("  - New users get 100 tokens as a welcome bonus")
    print("  - Users are created as registered (not superuser)")


async def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    if sys.argv[1] in ['--help', '-h']:
        print_usage()
        sys.exit(0)
    elif sys.argv[1] in ['--list', '-l']:
        await list_users()
        sys.exit(0)
    elif len(sys.argv) != 3:
        print("❌ Error: Both email and password are required")
        print()
        print_usage()
        sys.exit(1)
    else:
        email = sys.argv[1]
        password = sys.argv[2]
        success = await create_user(email, password)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())