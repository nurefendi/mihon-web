#!/usr/bin/env python3
"""Provision only mihon_web DB/user on the existing MariaDB; never prints secrets.
Run on the deployment host with access to docker. Credentials remain in private
/home/mazaya/mihon-web-deploy/database.env and are preserved across retries.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess

ROOT = Path(os.environ.get('MIHON_DEPLOY_DIR', '/home/mazaya/mihon-web-deploy'))
ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
ROOT.chmod(0o700)
path = ROOT / 'database.env'
if path.exists():
    entries = dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)
    password = entries['DB_PASSWORD']
else:
    password = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(f'DB_PASSWORD={password}\nMYSQL_DSN=mihon_web:{password}@tcp(mariadb-quiz:3306)/mihon_web?parseTime=true&charset=utf8mb4\n')
if not password or any(c not in '0123456789abcdef' for c in password):
    raise SystemExit('Unexpected password format; refusing to interpolate SQL')

def sql(query):
    proc = subprocess.run(['docker', 'exec', '-i', 'mariadb-quiz', 'sh', '-c',
        'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb --batch --skip-column-names -uroot'],
        input=query, text=True, capture_output=True, check=True)
    return proc.stdout.strip()

existing_db = sql("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='mihon_web';")
existing_user = sql("SELECT COUNT(*) FROM mysql.user WHERE User='mihon_web';")
if existing_db == '0':
    sql('CREATE DATABASE mihon_web CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
if existing_user == '0':
    sql(f"CREATE USER 'mihon_web'@'%' IDENTIFIED BY '{password}';")
sql("GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON mihon_web.* TO 'mihon_web'@'%';")
assert sql("SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='mihon_web';") == '1'
assert sql("SELECT COUNT(*) FROM mysql.user WHERE User='mihon_web';") == '1'
# Privilege metadata contains no authentication material.
print(sql("SELECT TABLE_SCHEMA, PRIVILEGE_TYPE FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE=\"'mihon_web'@'%'\" ORDER BY PRIVILEGE_TYPE;"))
print('Dedicated schema/user verified. Private credentials preserved at', path)
