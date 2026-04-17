-- PostgreSQL initialisation script
-- Runs once when the container is first created.
-- SQLAlchemy's create_all() handles the actual schema;
-- this script only sets up extensions and sane defaults.

-- Enable UUID generation (used as primary keys)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Ensure the database uses UTC
SET timezone = 'UTC';
