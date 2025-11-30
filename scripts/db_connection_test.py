#!/usr/bin/env python
"""
Simple database connection test for dm-dbcore.

Tests that your environment is set up correctly to access the database.
If this runs without exceptions, the connection is working.

Prerequisites:
- dm-dbcore installed: pip install dm-dbcore
- A connection module created from TEMPLATE_Connection.py with your credentials
- Model classes defined from TEMPLATE_ModelClasses*.py

Usage:
    python db_connection_test.py
"""

import sys

# Import your custom connection module and model classes
# Replace these with your actual imports
try:
    from myproject_connection import get_database_connection
    from myproject_models import User
except ImportError as e:
    print("=" * 70)
    print("ERROR: Connection or model classes not found")
    print("=" * 70)
    print(f"\nImport error: {e}\n")
    print("To use this test script, you need to:")
    print("  1. Create a connection module using TEMPLATE_Connection.py")
    print("     - Copy templates/TEMPLATE_Connection.py to myproject_connection.py")
    print("     - Fill in your database credentials")
    print("     - Update the module name in this script if different\n")
    print("  2. Create model classes using TEMPLATE_ModelClasses_*.py")
    print("     - Copy templates/TEMPLATE_ModelClasses_PostgreSQL.py (or MySQL)")
    print("       to myproject_models.py")
    print("     - Define your model classes (e.g., User)")
    print("     - Model classes are configured automatically on import\n")
    print("Or use dm-dbcore directly for testing:")
    print("  from dm_dbcore import DatabaseConnection, session_scope")
    print("  db = DatabaseConnection('postgresql://user:pass@localhost/mydb')")
    print("  # Then use session_scope(db) for queries\n")
    sys.exit(1)

# Get database connection
db = get_database_connection()

# Get a session (model classes are already configured from import)
session = db.Session()

# Simple query - get first 10 records
users = session.query(User).limit(10).all()

# Print results
for user in users:
    print(user)

# Close session
session.close()
