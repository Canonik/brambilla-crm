CREATE TABLE IF NOT EXISTS objects (
    id BIGINT PRIMARY KEY,
    object_type TEXT NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived BOOLEAN NOT NULL DEFAULT false,
    archived_at TIMESTAMPTZ
);
CREATE SEQUENCE IF NOT EXISTS objects_id_seq START 1;
CREATE INDEX IF NOT EXISTS objects_type_id_idx ON objects (object_type, id) WHERE NOT archived;
DROP INDEX IF EXISTS objects_props_gin_idx;
CREATE INDEX IF NOT EXISTS objects_id_legacy_idx ON objects ((properties->>'id_legacy'));
CREATE UNIQUE INDEX IF NOT EXISTS objects_contact_email_uq ON objects ((properties->>'email')) WHERE object_type = 'contacts' AND NOT archived AND properties ? 'email';
CREATE UNIQUE INDEX IF NOT EXISTS objects_company_piva_uq ON objects ((properties->>'partita_iva')) WHERE object_type = 'companies' AND NOT archived AND properties ? 'partita_iva';
CREATE INDEX IF NOT EXISTS objects_company_domain_idx ON objects ((properties->>'domain')) WHERE object_type = 'companies';
CREATE INDEX IF NOT EXISTS objects_sku_idx ON objects ((properties->>'hs_sku')) WHERE object_type = 'products';
CREATE INDEX IF NOT EXISTS objects_name_lower_idx ON objects (object_type, lower(properties->>'name'));
CREATE INDEX IF NOT EXISTS objects_dealname_lower_idx ON objects (lower(properties->>'dealname')) WHERE object_type = 'deals';

CREATE TABLE IF NOT EXISTS associations (
    from_id BIGINT NOT NULL,
    to_id BIGINT NOT NULL,
    type_id INTEGER NOT NULL,
    from_type TEXT NOT NULL,
    to_type TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'HUBSPOT_DEFINED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_id, to_id, type_id)
);
CREATE INDEX IF NOT EXISTS associations_from_totype_idx ON associations (from_id, to_type);
CREATE INDEX IF NOT EXISTS associations_to_idx ON associations (to_id);

CREATE TABLE IF NOT EXISTS association_labels (
    type_id INTEGER PRIMARY KEY,
    from_type TEXT NOT NULL,
    to_type TEXT NOT NULL,
    label TEXT,
    name TEXT,
    category TEXT NOT NULL DEFAULT 'USER_DEFINED',
    inverse_type_id INTEGER
);

CREATE TABLE IF NOT EXISTS properties (
    object_type TEXT NOT NULL,
    name TEXT NOT NULL,
    definition JSONB NOT NULL,
    PRIMARY KEY (object_type, name)
);

CREATE TABLE IF NOT EXISTS property_groups (
    object_type TEXT NOT NULL,
    name TEXT NOT NULL,
    definition JSONB NOT NULL,
    PRIMARY KEY (object_type, name)
);

CREATE TABLE IF NOT EXISTS pipelines (
    object_type TEXT NOT NULL,
    id TEXT NOT NULL,
    definition JSONB NOT NULL,
    PRIMARY KEY (object_type, id)
);

CREATE TABLE IF NOT EXISTS lists (
    list_id BIGINT PRIMARY KEY,
    definition JSONB NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS lists_id_seq START 1;

CREATE TABLE IF NOT EXISTS list_memberships (
    list_id BIGINT NOT NULL,
    record_id BIGINT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (list_id, record_id)
);

CREATE TABLE IF NOT EXISTS company_domains (
    domain TEXT NOT NULL,
    company_id BIGINT NOT NULL,
    PRIMARY KEY (domain, company_id)
);
CREATE INDEX IF NOT EXISTS company_domains_company_idx ON company_domains (company_id);

CREATE TABLE IF NOT EXISTS automation_flags (
    object_id BIGINT NOT NULL,
    rule TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (object_id, rule)
);

CREATE TABLE IF NOT EXISTS crm_users (
    id TEXT PRIMARY KEY,
    firstname TEXT,
    lastname TEXT,
    email TEXT,
    role TEXT,
    manager_id TEXT,
    active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS export_tasks (
    id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    token TEXT NOT NULL,
    request JSONB NOT NULL,
    content BYTEA,
    filename TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE SEQUENCE IF NOT EXISTS export_id_seq START 1;

CREATE TABLE IF NOT EXISTS import_tasks (
    id BIGINT PRIMARY KEY,
    definition JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE SEQUENCE IF NOT EXISTS import_id_seq START 1;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);
