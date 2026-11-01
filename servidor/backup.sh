#!/bin/sh
# Backup diário da pasta de dados (agende no cron: 0 3 * * * /caminho/servidor/backup.sh)
cd "$(dirname "$0")" || exit 1
mkdir -p backups
tar czf "backups/pato_$(date +%Y%m%d).tar.gz" dados
ls -1t backups/pato_*.tar.gz | tail -n +31 | xargs -r rm -f   # guarda 30 dias
