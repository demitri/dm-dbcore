# dm-dbcore Templates

This directory contains templates for building database applications using the `dm-dbcore` package. These templates provide starting points for common database patterns and help you quickly set up SQLAlchemy ORM models and connections.

## Available Templates

### 1. `TEMPLATE_Connection.py`
**Purpose**: Database connection module for your project

**Use this to**: Create a centralized database connection manager that handles connection strings, password management, and model loading.

**Key Features**:
- Connection string builder for PostgreSQL, MySQL, SQLite
- Password management options (environment variables, password files, hardcoded)
- Metadata caching configuration
- Session factory functions
- Model class loading orchestration
- Connection testing utilities

**When to use**: Start with this template for every new project that uses dm-dbcore.

**Quick start**:
```bash
cp TEMPLATE_Connection.py myproject/database/connection.py
# Edit TODO items in the file
# Test with: python connection.py
```

---

### 2. `TEMPLATE_ModelClasses.py`
**Purpose**: Generic SQLAlchemy model classes template (database-agnostic)

**Use this to**: Define ORM model classes for your database tables with examples of common relationship patterns.

**Key Features**:
- Model class structure with autoload
- One-to-one relationships
- One-to-many relationships
- Many-to-many relationships with association tables
- Relationship loading strategies (lazy, select, joined, etc.)
- Cascade options for deletions
- Model validation and testing

**When to use**: Use for simple single-schema projects or as a learning reference. For production projects, prefer the database-specific templates below.

**Quick start**:
```bash
cp TEMPLATE_ModelClasses.py myproject/database/models.py
# Update schema name, table names, relationships
# Test with: python models.py
```

---

### 3. `TEMPLATE_ModelClasses_PostgreSQL.py`
**Purpose**: PostgreSQL-specific model classes with schema support

**Use this to**: Define models for PostgreSQL databases that use schemas to organize tables.

**Key Features**:
- PostgreSQL schema support (`schema='myschema'`)
- Examples of PostgreSQL-specific types (Point, Polygon, UUID, JSONB, ARRAY)
- Schema information utilities
- Cross-schema relationship guidance
- Full-text search support
- PostgreSQL table comments

**When to use**: Use this for **PostgreSQL projects** where you need to work with explicit schemas (not just the `public` schema).

**PostgreSQL concepts**:
```
Server → Database → Schema → Table
Example: localhost:5432 → mydb → myschema → users
```

**Quick start**:
```bash
cp TEMPLATE_ModelClasses_PostgreSQL.py myproject/database/myschema_models.py
# Update SCHEMA_NAME = 'myschema'
# Update table names and relationships
# Test with: python myschema_models.py
```

---

### 4. `TEMPLATE_ModelClasses_MySQL.py`
**Purpose**: MySQL-specific model classes (no schema support)

**Use this to**: Define models for MySQL databases, which don't use PostgreSQL-style schemas.

**Key Features**:
- MySQL database structure (no schemas!)
- Storage engine specification (InnoDB, MyISAM)
- Character set configuration (utf8mb4)
- MySQL ENUM types
- Timestamp with auto-update
- Full-text indexes
- Cross-database relationships

**When to use**: Use this for **MySQL/MariaDB projects**. MySQL uses databases where PostgreSQL uses schemas.

**MySQL concepts**:
```
Server → Database → Table
Example: localhost:3306 → mydb → users
(NO schemas - each database IS like a schema)
```

**Important**: Remove `'schema': 'xxx'` from `__table_args__` - MySQL doesn't use it!

**Quick start**:
```bash
cp TEMPLATE_ModelClasses_MySQL.py myproject/database/models.py
# Remove any 'schema' references
# Update table names and relationships
# Connection string MUST include database name
# Test with: python models.py
```

---

### 5. `TEMPLATE_CrossSchemaRelationships.py`
**Purpose**: Define relationships between tables in different schemas (PostgreSQL) or databases (MySQL)

**Use this to**: Create foreign key relationships that cross schema/database boundaries.

**Key Features**:
- Cross-schema foreign keys (PostgreSQL)
- Cross-database foreign keys (MySQL)
- Multiple mapper registries
- search_path handling for PostgreSQL
- Cross-schema many-to-many relationships
- Common pitfalls and solutions
- Model loading order management

**When to use**: Use when you have relationships between tables in:
- Different PostgreSQL schemas (`schema1.users` → `schema2.posts`)
- Different MySQL databases (`db1.users` → `db2.posts`)

**Critical requirement**: Always use fully-qualified names in `ForeignKey()`:
```python
# PostgreSQL
ForeignKey('schema1.users.id')  # ✓ CORRECT
ForeignKey('users.id')          # ✗ WRONG

# MySQL
ForeignKey('database1.users.id')  # ✓ CORRECT
ForeignKey('users.id')            # ✗ WRONG
```

**Quick start**:
```bash
cp TEMPLATE_CrossSchemaRelationships.py myproject/database/cross_schema.py
# Update schema/database names
# Define cross-boundary relationships
# Import both sets of models
# Test with: python cross_schema.py
```

---

## Usage Workflow

### For a New Project

**1. Start with the Connection template**:
```bash
mkdir -p myproject/database
cd myproject/database
cp /path/to/templates/TEMPLATE_Connection.py connection.py
```

Edit `connection.py`:
- Update database connection parameters
- Choose password method
- Set metadata cache filename

**2. Choose the right ModelClasses template**:

**PostgreSQL with schemas**:
```bash
cp /path/to/templates/TEMPLATE_ModelClasses_PostgreSQL.py myschema_models.py
```

**MySQL**:
```bash
cp /path/to/templates/TEMPLATE_ModelClasses_MySQL.py models.py
```

**3. Define your models**:
- Update schema/database names
- Add your table definitions
- Define relationships between tables
- Test: `python myschema_models.py`

**4. Use in your application**:
```python
from myproject.database.connection import get_database_connection
from myproject.database.myschema_models import User, Post  # Models configured on import
from dm_dbcore import session_scope

# Get database connection
db = get_database_connection()

# Query (models are already configured)
with session_scope(db) as session:
    users = session.query(User).all()
```

**Note**: Model classes are automatically configured when imported via the `@mapper_registry.mapped` decorator and `configure_mappers()` call in the model file. No explicit loading function is needed.

---

## Template Checklist

Each template has a TODO checklist at the top. Always complete these items:

### Common TODO items:
- [ ] Replace placeholder names (MYPROJECT, MYSCHEMA, etc.)
- [ ] Update database connection parameters
- [ ] Set metadata cache filename
- [ ] Define model classes for your tables
- [ ] Add relationships between models
- [ ] Test with the `if __name__ == '__main__'` section
- [ ] Remove example code and comments for production

---

## Database-Specific Notes

### PostgreSQL

**Schemas**: PostgreSQL uses schemas to organize tables within a database. Always specify:
```python
__table_args__ = {'schema': 'myschema', 'autoload': True}
```

**search_path**: dm-dbcore automatically clears the PostgreSQL `search_path` to avoid ambiguity. Always use fully-qualified names in foreign keys:
```python
ForeignKey('schema1.users.id')  # Always include schema name
```

**Custom types**: PostgreSQL supports Point, Polygon, UUID, JSONB, ARRAY. See examples in `TEMPLATE_ModelClasses_PostgreSQL.py`.

**Metadata staleness detection**: Automatic cache invalidation works out-of-the-box using `information_schema.columns` (no manual setup required).

### MySQL

**No schemas**: MySQL doesn't use schemas like PostgreSQL. The database name in the connection string IS the schema.

**Connection string**: Must include database name:
```python
'mysql+pymysql://user:pass@localhost:3306/mydatabase'
```

**Character sets**: Always use `utf8mb4` for full Unicode support:
```python
__table_args__ = {
    'autoload': True,
    'mysql_charset': 'utf8mb4',
    'mysql_collate': 'utf8mb4_unicode_ci'
}
```

**No schema parameter**: Never use `'schema': 'xxx'` in `__table_args__` for MySQL!

**Storage engines**: Specify InnoDB for foreign key support:
```python
__table_args__ = {'autoload': True, 'mysql_engine': 'InnoDB'}
```

**Metadata staleness detection**: dm-dbcore automatically tracks schema changes using `information_schema.TABLES`.

### SQLite

**File-based**: SQLite uses a file, not a server:
```python
'sqlite:///path/to/database.db'
```

**No schemas**: SQLite has limited schema support. Use attached databases for cross-database relationships.

**No cache staleness detection**: SQLite caches are always considered stale.

---

## Relationship Patterns

### One-to-One

**Use case**: User ↔ UserProfile

```python
# Parent side (User)
profile = relationship('UserProfile', back_populates='user', uselist=False)

# Child side (UserProfile)
user_id = Column(Integer, ForeignKey('users.id'), unique=True)
user = relationship('User', back_populates='profile')
```

### One-to-Many

**Use case**: User → Posts

```python
# Parent side (User) - "one"
posts = relationship('Post', back_populates='author')

# Child side (Post) - "many"
author_id = Column(Integer, ForeignKey('users.id'))
author = relationship('User', back_populates='posts')
```

### Many-to-Many

**Use case**: Posts ↔ Tags

```python
# Association table
post_tags = Table('post_tags', metadata,
    Column('post_id', ForeignKey('posts.id'), primary_key=True),
    Column('tag_id', ForeignKey('tags.id'), primary_key=True)
)

# Both sides use secondary
posts = relationship('Post', secondary=post_tags, back_populates='tags')
tags = relationship('Tag', secondary=post_tags, back_populates='posts')
```

---

## Common Pitfalls

### 1. Forgetting schema names (PostgreSQL)
```python
# ✗ WRONG
ForeignKey('users.id')

# ✓ CORRECT
ForeignKey('myschema.users.id')
```

### 2. Using 'schema' in MySQL
```python
# ✗ WRONG (MySQL doesn't have schemas)
__table_args__ = {'schema': 'mydb', 'autoload': True}

# ✓ CORRECT
__table_args__ = {'autoload': True}
```

### 3. Not calling configure_mappers()
```python
# Always call this after defining relationships
configure_mappers()
```

### 4. Circular imports
```python
# Use string-based references or import inside functions
relationship('User')  # String reference (lazy import)
```

### 5. Missing back_populates
```python
# Both sides need back_populates for bidirectional relationships
# User side
posts = relationship('Post', back_populates='author')

# Post side
author = relationship('User', back_populates='posts')
```

---

## Testing Your Models

Each template includes a `if __name__ == '__main__'` section for testing. Run it:

```bash
python myschema_models.py
```

This will:
1. Connect to the database
2. Load model classes
3. Validate relationships
4. Run test queries
5. Report success or errors

**Always test before using in production!**

---

## Advanced Topics

### Multiple Schemas/Databases

If your project uses multiple schemas (PostgreSQL) or databases (MySQL), create separate model files:

```
myproject/database/
├── connection.py
├── schema1_models.py
├── schema2_models.py
└── cross_schema_relationships.py
```

Import them in your application:
```python
# Models are configured automatically on import
from myproject.database.schema1_models import User, Profile
from myproject.database.schema2_models import Post, Comment
from myproject.database.cross_schema_relationships import *  # If you have cross-schema relationships

# Use the models directly
with session_scope(db) as session:
    users = session.query(User).all()
```

**Note**: All model classes are configured when their modules are imported. The `configure_mappers()` call in each model file ensures relationships are validated.

### Custom Types

PostgreSQL custom types (Point, Polygon) are automatically registered by dm-dbcore:

```python
from dm_dbcore.adapters.postgresql.pggeometry import PGPoint, PGPolygon

location = Column(PGPoint)
boundary = Column(PGPolygon)
```

### Migration from Other ORMs

If migrating from Django ORM, Flask-SQLAlchemy, or raw SQL:
1. Start with the Connection template
2. Use ModelClasses template and set `autoload=True`
3. Let SQLAlchemy reflect your existing schema
4. Add relationships manually
5. Test thoroughly before modifying database

---

## Getting Help

- dm-dbcore documentation: See main README.md
- SQLAlchemy docs: https://docs.sqlalchemy.org/
- PostgreSQL schemas: https://www.postgresql.org/docs/current/ddl-schemas.html
- MySQL databases: https://dev.mysql.com/doc/refman/8.0/en/creating-database.html

---

## Contributing

Found a bug or want to improve these templates? Please open an issue or submit a pull request!

---

*Last updated: 2025*
