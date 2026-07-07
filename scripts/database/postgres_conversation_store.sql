-- PostgreSQL schema for durable Legal QA conversation storage.
-- Apply manually to a managed PostgreSQL database before selecting
-- LEGAL_QA_CONVERSATION_STORE=postgres.

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    owner_id TEXT NULL,
    title TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    owner_id TEXT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
    ON conversations (updated_at DESC, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated_at
    ON conversations (owner_id, updated_at DESC)
    WHERE owner_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_created_at
    ON conversation_messages (conversation_id, created_at ASC, id ASC);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_owner_created_at
    ON conversation_messages (owner_id, created_at DESC)
    WHERE owner_id IS NOT NULL;
