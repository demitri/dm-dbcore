#!/usr/bin/env python
"""
Test script for dm-dbcore package.

This script demonstrates how to use dm-dbcore in a project:
1. Create a custom Connection module with database credentials (see templates directory).
2. Create a custom model classes file that defines all of the SQLAlchemy classes (again, see templates directory).
3. Load models and query the database.

Usage:
    python test_dm_dbcore.py

This script expects:
- A Connection module (e.g., myproject_connection.py) with database config
- Model classes defined based on dm-dbcore templates
"""

import sys
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_connection_module():
    """
    Test 1: Import and test custom connection module.

    This assumes you've created a connection module from TEMPLATE_Connection.py
    with your database credentials filled in.
    """
    print("=" * 70)
    print("TEST 1: Database Connection")
    print("=" * 70)

    try:
        # Import your custom connection module
        # Example: from myproject.database import connection
        # For this demo, we'll import dm_dbcore directly

        from dm_dbcore import DatabaseConnection

        # In a real project, you would use your connection module:
        # from myproject_connection import get_database_connection
        # db = get_database_connection()

        # For this demo, create connection directly
        # TODO: Update with your database credentials
        connection_string = 'postgresql+psycopg://user:password@localhost/testdb'
        # Or: connection_string = 'mysql://user:password@localhost/testdb'
        # Or: connection_string = 'sqlite:///test.db'

        print("\n[1.1] Creating database connection...")
        db = DatabaseConnection(
            database_connection_string=connection_string,
            cache_name='test_metadata.pkl'
        )
        print(f"    ✓ Connected to {db.database_type} database")

        return db

    except Exception as e:
        print(f"    ✗ Failed to create connection: {e}")
        print("\nTo fix this:")
        print("  1. Create a connection module using TEMPLATE_Connection.py")
        print("  2. Fill in your database credentials")
        print("  3. Import it in this script")
        return None


def test_metadata_loading(db):
    """
    Test 2: Check metadata reflection.

    dm-dbcore automatically reflects database schema.
    """
    print("\n" + "=" * 70)
    print("TEST 2: Metadata Loading")
    print("=" * 70)

    if not db:
        print("    ⊗ Skipped (no database connection)")
        return False

    try:
        print("\n[2.1] Checking reflected metadata...")
        if db.metadata and db.metadata.tables:
            print(f"    ✓ Metadata loaded: {len(db.metadata.tables)} tables found")

            print("\n[2.2] Sample tables:")
            for i, table_name in enumerate(list(db.metadata.tables.keys())[:5]):
                print(f"    - {table_name}")

            if len(db.metadata.tables) > 5:
                print(f"    ... and {len(db.metadata.tables) - 5} more")

            return True
        else:
            print("    ⊗ No tables found (empty database or no permissions)")
            return False

    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def test_model_classes(db):
    """
    Test 3: Load model classes.

    This assumes you've created model classes using TEMPLATE_ModelClasses*.py
    """
    print("\n" + "=" * 70)
    print("TEST 3: Model Classes")
    print("=" * 70)

    if not db:
        print("    ⊗ Skipped (no database connection)")
        return False

    try:
        # In a real project, you would import your model classes:
        # from myproject.database.models import User, Post
        # Model classes are configured automatically on import

        print("\n[3.1] Importing model classes...")
        print("    ⊗ No model classes defined yet")
        print("\nTo add model classes:")
        print("  1. Copy TEMPLATE_ModelClasses_PostgreSQL.py or TEMPLATE_ModelClasses_MySQL.py")
        print("  2. Update schema/database name and table definitions")
        print("  3. Import model classes - they configure automatically on import")

        return False

    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def test_session_scope(db):
    """
    Test 4: Test session_scope context manager.

    Demonstrates transactional database operations.
    """
    print("\n" + "=" * 70)
    print("TEST 4: Session Management")
    print("=" * 70)

    if not db:
        print("    ⊗ Skipped (no database connection)")
        return False

    try:
        from dm_dbcore import session_scope
        from sqlalchemy import text

        print("\n[4.1] Testing session_scope context manager...")
        with session_scope(db) as session:
            # Simple query to test connection
            if db.database_type == 'postgresql':
                result = session.execute(text("SELECT version()"))
            elif db.database_type == 'mysql':
                result = session.execute(text("SELECT VERSION()"))
            elif db.database_type == 'sqlite':
                result = session.execute(text("SELECT sqlite_version()"))
            else:
                result = None

            if result:
                version = result.scalar()
                print(f"    ✓ Session created and query executed")
                print(f"    Database version: {version}")

        print("    ✓ Session closed automatically")

        return True

    except Exception as e:
        print(f"    ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_management(db):
    """
    Test 5: Metadata cache management.

    Shows how metadata caching improves startup performance.
    """
    print("\n" + "=" * 70)
    print("TEST 5: Metadata Cache")
    print("=" * 70)

    if not db:
        print("    ⊗ Skipped (no database connection)")
        return False

    try:
        import pathlib

        cache_dir = pathlib.Path.home() / '.sqlalchemy_cache'
        cache_file = cache_dir / 'test_metadata.pkl'

        print(f"\n[5.1] Cache location: {cache_file}")
        if cache_file.exists():
            print(f"    ✓ Cache file exists")
            import datetime
            mtime = datetime.datetime.fromtimestamp(cache_file.stat().st_mtime)
            print(f"    Last modified: {mtime}")
        else:
            print(f"    ⊗ Cache file not created yet")
            print("    (Will be created on next startup)")

        return True

    except Exception as e:
        print(f"    ✗ Error: {e}")
        return False


def demonstrate_usage_patterns():
    """
    Show common usage patterns for dm-dbcore.
    """
    print("\n" + "=" * 70)
    print("USAGE PATTERNS")
    print("=" * 70)

    print("""
1. PROJECT STRUCTURE (Recommended):

    myproject/
    ├── database/
    │   ├── __init__.py
    │   ├── connection.py          # From TEMPLATE_Connection.py
    │   ├── schema1_models.py      # From TEMPLATE_ModelClasses_PostgreSQL.py
    │   └── schema2_models.py      # From TEMPLATE_ModelClasses_MySQL.py
    └── scripts/
        └── query_example.py

2. CONNECTION MODULE (database/connection.py):

    from dm_dbcore import DatabaseConnection, session_scope

    DB_HOST = 'localhost'
    DB_DATABASE = 'mydb'
    DB_USER = 'myuser'

    def get_database_connection():
        connection_string = f'postgresql+psycopg://{DB_USER}@{DB_HOST}/{DB_DATABASE}'
        return DatabaseConnection(
            database_connection_string=connection_string,
            cache_name='myproject_metadata.pkl'
        )

3. MODEL CLASSES (database/schema1_models.py):

    from sqlalchemy.orm import registry, relationship
    from sqlalchemy import Column, Integer, ForeignKey

    mapper_registry = registry()

    @mapper_registry.mapped
    class User:
        __tablename__ = 'users'
        __table_args__ = {'schema': 'myschema', 'autoload': True}

        id = Column(Integer, primary_key=True)

        posts = relationship('Post', back_populates='author')

4. USING IN APPLICATION:

    from database.connection import get_database_connection
    from database.schema1_models import User
    from dm_dbcore import session_scope

    # Initialize (model classes configure automatically on import)
    db = get_database_connection()

    # Query
    with session_scope(db) as session:
        users = session.query(User).all()
        for user in users:
            print(user)

5. TESTING YOUR SETUP:

    # Test connection
    from database.connection import test_connection
    info = test_connection()
    print(f"Connected: {info['connected']}")

    # Clear cache if schema changed
    from database.connection import clear_metadata_cache
    clear_metadata_cache()
""")


def main():
    """Run all tests."""

    print("\n" + "=" * 70)
    print("DMUNA-DBCORE PACKAGE TEST")
    print("=" * 70)
    print("\nThis script demonstrates how to use dm-dbcore in your project.")
    print("Each test shows a different aspect of the package.\n")

    # Run tests
    db = test_connection_module()
    test_metadata_loading(db)
    test_model_classes(db)
    test_session_scope(db)
    test_cache_management(db)

    # Show usage patterns
    demonstrate_usage_patterns()

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print("""
To use dm-dbcore in your project:

1. Install the package:
   pip install dm-dbcore

2. Copy templates from dm-dbcore/templates/:
   - TEMPLATE_Connection.py → your_connection.py
   - TEMPLATE_ModelClasses_PostgreSQL.py → your_models.py (or MySQL version)

3. Fill in your database credentials in your_connection.py

4. Define your model classes in your_models.py

5. Import and use (model classes configure automatically on import):
   from your_connection import get_database_connection
   from your_models import User
   from dm_dbcore import session_scope

   db = get_database_connection()

   with session_scope(db) as session:
       users = session.query(User).all()

For more details, see:
- dm-dbcore/README.md
- dm-dbcore/templates/README.md
""")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
