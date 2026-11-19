#!/bin/sh
# LOCAL DOCKER ONLY. Rebuilds the tally_demo database: the current schema plus about six
# months of demo data (demo_data.sql), for building dashboards. The tally database and its
# seed data are never touched, so the services' tests are unaffected.
#
#   docker compose exec db sh /db/local/load-demo.sh
#
# Rerun it any time to start fresh, for example after db/ddl.sql changes.
# Must connect as a superuser.
set -eu
cd "$(dirname "$0")/.."

export PGUSER="${PGUSER:-tally}"
DEMO_DB="${DEMO_DB:-tally_demo}"
PSQL="psql -X -q -v ON_ERROR_STOP=1"

$PSQL -d postgres -c "DROP DATABASE IF EXISTS $DEMO_DB WITH (FORCE)" -c "CREATE DATABASE $DEMO_DB"
$PSQL -d "$DEMO_DB" -o /dev/null -f ddl.sql -f local/demo_data.sql

$PSQL -d "$DEMO_DB" -At -c "
    SELECT format('Loaded $DEMO_DB: %s orders, %s order lines, %s stock movements, %s to %s',
                  (SELECT count(*) FROM sales.orders),
                  (SELECT count(*) FROM sales.order_lines),
                  (SELECT count(*) FROM inventory.stock_movements),
                  (SELECT min(order_date)::date FROM sales.orders),
                  (SELECT max(order_date)::date FROM sales.orders))"
