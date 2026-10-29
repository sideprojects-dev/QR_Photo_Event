-- Apply only after reviewing the production schema and duplicate-active check
-- documented in README.md. This migration never changes existing event rows.
BEGIN;

DO $check_existing_active_events$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.events
        WHERE status = 'active' AND location_id IS NOT NULL
        GROUP BY location_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Multiple active events exist for a location; review data before migration';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.events GROUP BY slug HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate event slugs exist; review data before migration';
    END IF;
END;
$check_existing_active_events$;

CREATE UNIQUE INDEX events_one_active_per_location_idx
    ON public.events (location_id)
    WHERE status = 'active';

CREATE FUNCTION public.activate_event_atomic(
    p_event_slug text,
    p_location_slug text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ''
AS $function$
DECLARE
    v_event public.events%ROWTYPE;
    v_locked_event public.events%ROWTYPE;
    v_location public.locations%ROWTYPE;
BEGIN
    -- The first lookup locates the row to lock. Re-read it after locking the
    -- location so concurrent activation observes the latest committed state.
    SELECT * INTO v_event
    FROM public.events
    WHERE slug = p_event_slug;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('result', 'event_not_found');
    END IF;
    IF v_event.location_id IS NULL THEN
        RETURN pg_catalog.jsonb_build_object('result', 'event_unbound');
    END IF;

    SELECT * INTO v_location
    FROM public.locations
    WHERE id = v_event.location_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('result', 'location_not_found');
    END IF;
    IF p_location_slug IS NOT NULL AND v_location.slug <> p_location_slug THEN
        RETURN pg_catalog.jsonb_build_object('result', 'location_mismatch');
    END IF;

    SELECT * INTO v_locked_event
    FROM public.events
    WHERE id = v_event.id AND location_id = v_location.id
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN pg_catalog.jsonb_build_object('result', 'location_mismatch');
    END IF;
    IF v_locked_event.status = 'active' THEN
        RETURN pg_catalog.jsonb_build_object('result', 'already_active');
    END IF;

    UPDATE public.events
    SET status = 'archived'
    WHERE location_id = v_location.id AND status = 'active';

    UPDATE public.events
    SET status = 'active'
    WHERE id = v_locked_event.id AND location_id = v_location.id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Target event disappeared during activation';
    END IF;

    RETURN pg_catalog.jsonb_build_object('result', 'activated');
END;
$function$;

REVOKE ALL ON FUNCTION public.activate_event_atomic(text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.activate_event_atomic(text, text)
    TO service_role;

COMMIT;
