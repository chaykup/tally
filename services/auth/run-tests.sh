#!/bin/sh
# Run auth tests in a temporary database using the local Docker stack.
set -eu

cd "$(dirname "$0")/../.."
test_db="tally_auth_test_$(date +%s)_$$"

docker compose up -d --wait db
docker compose exec -T db createdb -U tally "$test_db"

cleanup() {
    docker compose exec -T db dropdb -U tally --if-exists --force "$test_db"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

docker compose exec -T db psql -X -U tally -d "$test_db" -v ON_ERROR_STOP=1 -q \
    -f /db/ddl.sql -f /db/local/seed.sql

docker compose run --rm --no-deps \
    -e "TEST_DATABASE_URL=postgresql://tally_auth:tally@db:5432/$test_db" \
    -e JWT_SECRET=local-auth-tests-secret-at-least-32-bytes \
    auth pytest "$@"
