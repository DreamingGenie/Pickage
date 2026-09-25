@echo off
REM U2 downloads reload: psql wrapper that disables seq scans for every session (PGOPTIONS), contract hash unchanged.
docker exec -i -e "PGOPTIONS=-c enable_seqscan=off" pickage-app-postgres-1 psql %*
