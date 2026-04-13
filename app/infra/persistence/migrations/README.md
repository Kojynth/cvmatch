# Persistence Migrations

This directory is reserved for tracked schema migrations. The legacy
`create_all + ALTER TABLE` path remains in place as a compatibility shim during
the transition, but new schema changes should land here.
