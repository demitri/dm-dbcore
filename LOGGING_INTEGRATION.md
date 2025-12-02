# dm-dbcore Logging Integration

## Current State

The `dm-dbcore` module has logging configured in `DatabaseConnection.py`:

```python
import logging

logger = logging.getLogger("DatabaseConnection logger")
```

This logger is **automatically configured** when you set up logging in your application.

## How It Works

1. Your application calls `logging.basicConfig()` or configures logging manually
2. The dm-dbcore logger inherits this configuration
3. All log messages from `dm-dbcore` are sent to your configured handlers

## Logger Name

The main logger is named **"DatabaseConnection logger"** for historical reasons. You can configure it specifically:

```python
import logging

# Configure the dm-dbcore logger
dm_dbcore_logger = logging.getLogger('DatabaseConnection logger')
dm_dbcore_logger.setLevel(logging.INFO)
```

## What Gets Logged

### INFO Level
- Metadata cache hits/misses
- Database connection status
- Schema change detection

### DEBUG Level
- Detailed cache operations
- Table listings
- Connection details (sanitized)

### WARNING Level
- Cache validation failures
- Connection issues (non-fatal)
- Deprecated features

### ERROR Level
- Database connection failures
- Cache corruption
- Invalid configuration

## Integration Examples

### Basic Console Logging

```python
import logging

# Configure logging before importing dm-dbcore
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Now import and use dm-dbcore
from dm_dbcore import DatabaseConnection

db = DatabaseConnection(database_connection_string="mysql://...")
# Logging will work!
```

### Flask Integration

```python
# In your Flask app's logging_config.py

import logging

# Configure dm-dbcore logger
dm_dbcore_logger = logging.getLogger('DatabaseConnection logger')
dm_dbcore_logger.setLevel(logging.INFO)
dm_dbcore_logger.addHandler(console_handler)
dm_dbcore_logger.addHandler(file_handler)
```

### Django Integration

```python
# In Django settings.py

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'DatabaseConnection logger': {
            'handlers': ['console'],
            'level': 'INFO',
        },
    },
}
```

### Standalone Script

```python
import logging
import sys

# Set up colored logging (optional)
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'
    }

    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname_colored = f"{self.COLORS[levelname]}{levelname:8s}{self.COLORS['RESET']}"
            record.name_colored = f"\033[34m{record.name}\033[0m"  # Blue
        return super().format(record)

# Configure root logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColoredFormatter(
    fmt='%(levelname_colored)s [%(name_colored)s] %(message)s'
))
logger.addHandler(handler)

# Now use dm-dbcore
from dm_dbcore import DatabaseConnection

db = DatabaseConnection(...)
```

## Example Output

When connecting to a database:

```
INFO     [DatabaseConnection logger] Metadata cache is current.
INFO     [DatabaseConnection logger] Connected to MySQL database: ascl_db_v4
```

In debug mode:

```
DEBUG    [DatabaseConnection logger] Loading metadata from cache
DEBUG    [DatabaseConnection logger]     - ascldb.codes
DEBUG    [DatabaseConnection logger]     - ascldb.keywords
DEBUG    [DatabaseConnection logger]     - ascldb.citations
INFO     [DatabaseConnection logger] Metadata cache loaded: 14 tables
```

## Best Practices

### 1. Use Appropriate Log Levels

```python
# DEBUG: Detailed diagnostic info
logger.debug(f"Loading metadata from cache: {cache_path}")

# INFO: Normal operations
logger.info(f"Connected to {database_type} database: {database_name}")

# WARNING: Unexpected but handled
logger.warning(f"Cache stale, will reload from database")

# ERROR: Errors needing attention
logger.error(f"Failed to connect to database: {error}")

# CRITICAL: Severe errors
logger.critical(f"Database unavailable, cannot continue")
```

### 2. Include Context

```python
# Good
logger.info(f"Loaded {len(tables)} tables from database in {elapsed:.2f}s")

# Not as good
logger.info("Loaded tables")
```

### 3. Don't Log Sensitive Data

```python
# Bad - exposes password
logger.debug(f"Connection string: {connection_string}")

# Good - hides password
logger.debug(f"Connecting to {host}:{port}/{database} as {user}")
```

### 4. Configure Early

```python
# Configure logging BEFORE importing dm-dbcore
import logging
logging.basicConfig(level=logging.INFO)

# Now import
from dm_dbcore import DatabaseConnection
```

## Existing Log Statements in dm-dbcore

The module already includes logging for:

- Database connection validation
- Metadata cache operations (load, save, validate)
- Schema change detection (PostgreSQL, MySQL)
- Connection string parsing
- Session management

You don't need to add any logging - just configure the logger and it will work!

## Disabling dm-dbcore Logging

If you want to silence dm-dbcore logs:

```python
import logging

# Disable dm-dbcore logging
logging.getLogger('DatabaseConnection logger').setLevel(logging.CRITICAL)

# Or disable all logging
logging.getLogger('DatabaseConnection logger').disabled = True
```

## Summary

- ✅ Logging is already built into `dm-dbcore`
- ✅ Just configure logging in your app before importing
- ✅ Use logger name: "DatabaseConnection logger"
- ✅ Supports all standard Python logging configurations
- ✅ No additional setup needed for basic usage
