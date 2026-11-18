#!/bin/sh
# Builds db/ddl.sql in a fresh scratch database and runs every db/tests/*_test.sql against it,
# then drops the scratch database. Your dev database and its seed data are never touched.
#
#   Locally:  docker compose exec db sh /db/run-tests.sh
#   In CI:    sh db/run-tests.sh   (connection settings come from PGHOST, PGUSER, ...)
#
# Must connect as a superuser (the tests switch into each service role).
set -eu
cd "$(dirname "$0")"

export PGUSER="${PGUSER:-tally}"
TEST_DB="${TEST_DB:-tally_test}"
PSQL="psql -X -q -v ON_ERROR_STOP=1"

$PSQL -d postgres -c "DROP DATABASE IF EXISTS $TEST_DB" -c "CREATE DATABASE $TEST_DB"
trap '$PSQL -d postgres -c "DROP DATABASE IF EXISTS $TEST_DB"' EXIT

$PSQL -d "$TEST_DB" -f ddl.sql
for test in tests/*_test.sql; do
    echo "== $test"
    $PSQL -d "$TEST_DB" -f "$test" || { echo "FAILED: $test"; exit 1; }
done
echo "All database tests passed."
