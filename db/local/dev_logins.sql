-- LOCAL DOCKER ONLY. Never run this against Supabase.
-- One database login per service, each a member of its service role from ddl.sql, so the
-- local database enforces the same permissions production will. Password for all: tally
-- (In Supabase, create these logins by hand with strong passwords; see the top of ddl.sql.)

CREATE ROLE tally_auth         LOGIN PASSWORD 'tally' IN ROLE auth_service;
CREATE ROLE tally_inventory    LOGIN PASSWORD 'tally' IN ROLE inventory_service;
CREATE ROLE tally_transactions LOGIN PASSWORD 'tally' IN ROLE sales_service;
CREATE ROLE tally_analytics    LOGIN PASSWORD 'tally' IN ROLE analytics_reader;
