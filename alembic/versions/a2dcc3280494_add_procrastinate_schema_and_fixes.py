"""add procrastinate schema and constraint/index fixes

Revision ID: a2dcc3280494
Revises: 401fc1001837
Create Date: 2026-02-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a2dcc3280494"
down_revision: Union[str, None] = "401fc1001837"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Procrastinate schema ---
    op.execute("""
        CREATE TYPE procrastinate_job_status AS ENUM (
            'todo', 'doing', 'succeeded', 'failed', 'cancelled', 'aborting', 'aborted'
        );

        CREATE TYPE procrastinate_job_event_type AS ENUM (
            'deferred', 'started', 'deferred_for_retry', 'failed', 'succeeded',
            'cancelled', 'abort_requested', 'aborted', 'scheduled', 'retried'
        );

        CREATE TYPE procrastinate_job_to_defer_v1 AS (
            queue_name character varying,
            task_name character varying,
            priority integer,
            lock text,
            queueing_lock text,
            args jsonb,
            scheduled_at timestamp with time zone
        );

        CREATE TABLE procrastinate_workers(
            id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
            last_heartbeat timestamp with time zone NOT NULL DEFAULT NOW()
        );

        CREATE TABLE procrastinate_jobs (
            id bigserial PRIMARY KEY,
            queue_name character varying(128) NOT NULL,
            task_name character varying(128) NOT NULL,
            priority integer DEFAULT 0 NOT NULL,
            lock text,
            queueing_lock text,
            args jsonb DEFAULT '{}' NOT NULL,
            status procrastinate_job_status DEFAULT 'todo'::procrastinate_job_status NOT NULL,
            scheduled_at timestamp with time zone NULL,
            attempts integer DEFAULT 0 NOT NULL,
            abort_requested boolean DEFAULT false NOT NULL,
            worker_id bigint REFERENCES procrastinate_workers(id) ON DELETE SET NULL,
            CONSTRAINT check_not_todo_abort_requested
                CHECK (NOT (status = 'todo' AND abort_requested = true))
        );

        CREATE TABLE procrastinate_periodic_defers (
            id bigserial PRIMARY KEY,
            task_name character varying(128) NOT NULL,
            defer_timestamp bigint,
            job_id bigint REFERENCES procrastinate_jobs(id) NULL,
            periodic_id character varying(128) NOT NULL DEFAULT '',
            CONSTRAINT procrastinate_periodic_defers_unique
                UNIQUE (task_name, periodic_id, defer_timestamp)
        );

        CREATE TABLE procrastinate_events (
            id bigserial PRIMARY KEY,
            job_id bigint NOT NULL REFERENCES procrastinate_jobs ON DELETE CASCADE,
            type procrastinate_job_event_type,
            at timestamp with time zone DEFAULT NOW() NULL
        );
    """)

    # Procrastinate indexes
    op.execute("""
        CREATE INDEX ON procrastinate_jobs(queue_name);
        CREATE INDEX ON procrastinate_jobs(status);
        CREATE INDEX ON procrastinate_events(job_id);
    """)

    # Procrastinate functions
    op.execute("""
        CREATE FUNCTION procrastinate_defer_job_v1(
            queue_name character varying,
            task_name character varying,
            priority integer,
            lock text,
            queueing_lock text,
            args jsonb,
            scheduled_at timestamp with time zone
        ) RETURNS bigint
        LANGUAGE plpgsql
        AS $$
        DECLARE
            job_id bigint;
        BEGIN
            INSERT INTO procrastinate_jobs (queue_name, task_name, priority, lock, queueing_lock, args, scheduled_at)
            VALUES (queue_name, task_name, priority, lock, queueing_lock, args, scheduled_at)
            RETURNING id INTO job_id;
            RETURN job_id;
        END;
        $$;

        CREATE FUNCTION procrastinate_fetch_job_v1(target_queue_names character varying[])
        RETURNS procrastinate_jobs
        LANGUAGE plpgsql
        AS $$
        DECLARE
            found_jobs procrastinate_jobs;
        BEGIN
            SELECT INTO found_jobs *
            FROM procrastinate_jobs
            WHERE status = 'todo'::procrastinate_job_status
                AND (target_queue_names IS NULL OR queue_name = ANY(target_queue_names))
                AND (scheduled_at IS NULL OR scheduled_at <= now())
                AND (lock IS NULL OR lock NOT IN (
                    SELECT lock FROM procrastinate_jobs
                    WHERE status = 'doing' AND lock IS NOT NULL
                ))
            ORDER BY priority DESC, id ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1;

            IF found_jobs.id IS NOT NULL THEN
                UPDATE procrastinate_jobs
                SET status = 'doing'::procrastinate_job_status,
                    attempts = attempts + 1
                WHERE id = found_jobs.id;
            END IF;

            RETURN found_jobs;
        END;
        $$;

        CREATE FUNCTION procrastinate_finish_job_v1(job_id bigint, end_status procrastinate_job_status, delete_job boolean)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF delete_job THEN
                DELETE FROM procrastinate_jobs WHERE id = job_id;
            ELSE
                UPDATE procrastinate_jobs
                SET status = end_status
                WHERE id = job_id;
            END IF;
        END;
        $$;

        CREATE FUNCTION procrastinate_notify_queue_job_inserted_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            payload TEXT;
        BEGIN
            SELECT json_build_object('type', 'job_inserted', 'job_id', NEW.id)::text INTO payload;
            PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
            PERFORM pg_notify('procrastinate_any_queue_v1', payload);
            RETURN NEW;
        END;
        $$;

        CREATE FUNCTION procrastinate_notify_queue_abort_job_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            payload TEXT;
        BEGIN
            SELECT json_build_object('type', 'abort_job_requested', 'job_id', NEW.id)::text INTO payload;
            PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
            PERFORM pg_notify('procrastinate_any_queue_v1', payload);
            RETURN NEW;
        END;
        $$;

        CREATE FUNCTION procrastinate_trigger_function_status_events_insert_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO procrastinate_events(job_id, type)
                VALUES (NEW.id, 'deferred'::procrastinate_job_event_type);
            RETURN NEW;
        END;
        $$;

        CREATE FUNCTION procrastinate_trigger_function_status_events_update_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            WITH t AS (
                SELECT CASE
                    WHEN OLD.status = 'todo'::procrastinate_job_status
                        AND NEW.status = 'doing'::procrastinate_job_status
                        THEN 'started'::procrastinate_job_event_type
                    WHEN OLD.status = 'doing'::procrastinate_job_status
                        AND NEW.status = 'todo'::procrastinate_job_status
                        THEN 'deferred_for_retry'::procrastinate_job_event_type
                    WHEN OLD.status = 'doing'::procrastinate_job_status
                        AND NEW.status = 'failed'::procrastinate_job_status
                        THEN 'failed'::procrastinate_job_event_type
                    WHEN OLD.status = 'doing'::procrastinate_job_status
                        AND NEW.status = 'succeeded'::procrastinate_job_status
                        THEN 'succeeded'::procrastinate_job_event_type
                    WHEN OLD.status = 'todo'::procrastinate_job_status
                        AND (
                            NEW.status = 'cancelled'::procrastinate_job_status
                            OR NEW.status = 'failed'::procrastinate_job_status
                            OR NEW.status = 'succeeded'::procrastinate_job_status
                        )
                        THEN 'cancelled'::procrastinate_job_event_type
                    WHEN OLD.status = 'doing'::procrastinate_job_status
                        AND NEW.status = 'aborted'::procrastinate_job_status
                        THEN 'aborted'::procrastinate_job_event_type
                    WHEN OLD.status = 'failed'::procrastinate_job_status
                        AND NEW.status = 'todo'::procrastinate_job_status
                        THEN 'retried'::procrastinate_job_event_type
                    ELSE NULL
                END as event_type
            )
            INSERT INTO procrastinate_events(job_id, type)
                SELECT NEW.id, t.event_type
                FROM t
                WHERE t.event_type IS NOT NULL;
            RETURN NEW;
        END;
        $$;

        CREATE FUNCTION procrastinate_trigger_function_scheduled_events_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO procrastinate_events(job_id, type, at)
                VALUES (NEW.id, 'scheduled'::procrastinate_job_event_type, NEW.scheduled_at);
            RETURN NEW;
        END;
        $$;

        CREATE FUNCTION procrastinate_trigger_abort_requested_events_procedure_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            INSERT INTO procrastinate_events(job_id, type)
                VALUES (NEW.id, 'abort_requested'::procrastinate_job_event_type);
            RETURN NEW;
        END;
        $$;

        CREATE FUNCTION procrastinate_unlink_periodic_defers_v1()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            UPDATE procrastinate_periodic_defers
            SET job_id = NULL
            WHERE job_id = OLD.id;
            RETURN OLD;
        END;
        $$;

        CREATE FUNCTION procrastinate_register_worker_v1()
        RETURNS TABLE(worker_id bigint)
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RETURN QUERY
            INSERT INTO procrastinate_workers DEFAULT VALUES
            RETURNING procrastinate_workers.id;
        END;
        $$;

        CREATE FUNCTION procrastinate_unregister_worker_v1(worker_id bigint)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            DELETE FROM procrastinate_workers WHERE id = worker_id;
        END;
        $$;

        CREATE FUNCTION procrastinate_update_heartbeat_v1(worker_id bigint)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            UPDATE procrastinate_workers
            SET last_heartbeat = NOW()
            WHERE id = worker_id;
        END;
        $$;

        CREATE FUNCTION procrastinate_prune_stalled_workers_v1(seconds_since_heartbeat float)
        RETURNS TABLE(worker_id bigint)
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RETURN QUERY
            DELETE FROM procrastinate_workers
            WHERE last_heartbeat < NOW() - (seconds_since_heartbeat || 'SECOND')::INTERVAL
            RETURNING procrastinate_workers.id;
        END;
        $$;
    """)

    # Procrastinate triggers
    op.execute("""
        CREATE TRIGGER procrastinate_jobs_notify_queue_job_inserted_v1
            AFTER INSERT ON procrastinate_jobs
            FOR EACH ROW WHEN ((new.status = 'todo'::procrastinate_job_status))
            EXECUTE PROCEDURE procrastinate_notify_queue_job_inserted_v1();

        CREATE TRIGGER procrastinate_jobs_notify_queue_job_aborted_v1
            AFTER UPDATE OF abort_requested ON procrastinate_jobs
            FOR EACH ROW WHEN ((old.abort_requested = false AND new.abort_requested = true AND new.status = 'doing'::procrastinate_job_status))
            EXECUTE PROCEDURE procrastinate_notify_queue_abort_job_v1();

        CREATE TRIGGER procrastinate_trigger_status_events_update_v1
            AFTER UPDATE OF status ON procrastinate_jobs
            FOR EACH ROW
            EXECUTE PROCEDURE procrastinate_trigger_function_status_events_update_v1();

        CREATE TRIGGER procrastinate_trigger_status_events_insert_v1
            AFTER INSERT ON procrastinate_jobs
            FOR EACH ROW WHEN ((new.status = 'todo'::procrastinate_job_status))
            EXECUTE PROCEDURE procrastinate_trigger_function_status_events_insert_v1();

        CREATE TRIGGER procrastinate_trigger_scheduled_events_v1
            AFTER UPDATE OR INSERT ON procrastinate_jobs
            FOR EACH ROW WHEN ((new.scheduled_at IS NOT NULL AND new.status = 'todo'::procrastinate_job_status))
            EXECUTE PROCEDURE procrastinate_trigger_function_scheduled_events_v1();

        CREATE TRIGGER procrastinate_trigger_abort_requested_events_v1
            AFTER UPDATE OF abort_requested ON procrastinate_jobs
            FOR EACH ROW WHEN ((new.abort_requested = true))
            EXECUTE PROCEDURE procrastinate_trigger_abort_requested_events_procedure_v1();

        CREATE TRIGGER procrastinate_trigger_delete_jobs_v1
            BEFORE DELETE ON procrastinate_jobs
            FOR EACH ROW EXECUTE PROCEDURE procrastinate_unlink_periodic_defers_v1();
    """)

    # --- Fix: UniqueConstraint on connection_vlans ---
    op.create_unique_constraint(
        "uq_connection_vlans_conn_vlan",
        "connection_vlans",
        ["connection_id", "vlan_id"],
    )

    # --- Fix: Indexes on events for query performance ---
    op.create_index(
        op.f("ix_events_resource_type"),
        "events",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_events_resource_id"),
        "events",
        ["resource_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_events_created_at"),
        "events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    # Indexes
    op.drop_index(op.f("ix_events_created_at"), table_name="events")
    op.drop_index(op.f("ix_events_resource_id"), table_name="events")
    op.drop_index(op.f("ix_events_resource_type"), table_name="events")

    # Constraint
    op.drop_constraint("uq_connection_vlans_conn_vlan", "connection_vlans", type_="unique")

    # Procrastinate triggers
    op.execute("DROP TRIGGER IF EXISTS procrastinate_trigger_delete_jobs_v1 ON procrastinate_jobs")
    op.execute("DROP TRIGGER IF EXISTS procrastinate_trigger_abort_requested_events_v1 ON procrastinate_jobs")
    op.execute("DROP TRIGGER IF EXISTS procrastinate_trigger_scheduled_events_v1 ON procrastinate_jobs")
    op.execute("DROP TRIGGER IF EXISTS procrastinate_trigger_status_events_insert_v1 ON procrastinate_jobs")
    op.execute("DROP TRIGGER IF EXISTS procrastinate_trigger_status_events_update_v1 ON procrastinate_jobs")
    op.execute("DROP TRIGGER IF EXISTS procrastinate_jobs_notify_queue_job_aborted_v1 ON procrastinate_jobs")
    op.execute("DROP TRIGGER IF EXISTS procrastinate_jobs_notify_queue_job_inserted_v1 ON procrastinate_jobs")

    # Procrastinate functions
    op.execute("DROP FUNCTION IF EXISTS procrastinate_prune_stalled_workers_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_update_heartbeat_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_unregister_worker_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_register_worker_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_unlink_periodic_defers_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_trigger_abort_requested_events_procedure_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_trigger_function_scheduled_events_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_trigger_function_status_events_update_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_trigger_function_status_events_insert_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_notify_queue_abort_job_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_notify_queue_job_inserted_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_finish_job_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_fetch_job_v1")
    op.execute("DROP FUNCTION IF EXISTS procrastinate_defer_job_v1")

    # Procrastinate tables
    op.execute("DROP TABLE IF EXISTS procrastinate_events")
    op.execute("DROP TABLE IF EXISTS procrastinate_periodic_defers")
    op.execute("DROP TABLE IF EXISTS procrastinate_jobs")
    op.execute("DROP TABLE IF EXISTS procrastinate_workers")

    # Procrastinate types
    op.execute("DROP TYPE IF EXISTS procrastinate_job_to_defer_v1")
    op.execute("DROP TYPE IF EXISTS procrastinate_job_event_type")
    op.execute("DROP TYPE IF EXISTS procrastinate_job_status")
