#!/bin/bash
# Fix ownership of /data (may be owned by root from pre-cactus-user builds)
chown -R cactus:cactus /data 2>/dev/null || true
exec gosu cactus "$@"
