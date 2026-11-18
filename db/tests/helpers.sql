-- Assertion helpers shared by the test files. Include with \ir helpers.sql after BEGIN.
-- They are temporary functions (pg_temp), so they vanish when the session ends.

-- expect_error(label, statement, sqlstate): passes only if the statement fails with exactly that error.
--   23502 not_null_violation   23503 foreign_key_violation
--   23505 unique_violation     23514 check_violation   22P02 invalid_text_representation (bad enum)
--   42501 insufficient_privilege
CREATE FUNCTION pg_temp.expect_error(label text, stmt text, expected_state text) RETURNS void AS $$
BEGIN
    EXECUTE stmt;
    RAISE EXCEPTION 'FAIL [%]: statement succeeded but should have raised %', label, expected_state;
EXCEPTION
    WHEN OTHERS THEN
        IF SQLSTATE = 'P0001' AND SQLERRM LIKE 'FAIL [%' THEN
            RAISE;  -- re-raise our own "should have failed" error
        ELSIF SQLSTATE <> expected_state THEN
            RAISE EXCEPTION 'FAIL [%]: expected SQLSTATE %, got % (%)', label, expected_state, SQLSTATE, SQLERRM;
        END IF;
        RAISE NOTICE 'ok   %', label;
END;
$$ LANGUAGE plpgsql;

-- expect_ok(label, statement): passes only if the statement runs without error.
CREATE FUNCTION pg_temp.expect_ok(label text, stmt text) RETURNS void AS $$
BEGIN
    EXECUTE stmt;
    RAISE NOTICE 'ok   %', label;
EXCEPTION
    WHEN OTHERS THEN
        RAISE EXCEPTION 'FAIL [%]: expected success, got % (%)', label, SQLSTATE, SQLERRM;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION pg_temp.expect(label text, condition boolean) RETURNS void AS $$
BEGIN
    IF condition IS NOT TRUE THEN
        RAISE EXCEPTION 'FAIL [%]', label;
    END IF;
    RAISE NOTICE 'ok   %', label;
END;
$$ LANGUAGE plpgsql;
