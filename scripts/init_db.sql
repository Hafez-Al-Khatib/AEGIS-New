-- AEGIS PostgreSQL Initialization Script
-- This script is automatically run when the PostgreSQL Docker container starts

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Note: Tables are created automatically by SQLAlchemy on first run
-- This file is for any additional PostgreSQL-specific setup

-- Grant permissions (for Docker environment)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO current_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO current_user;
