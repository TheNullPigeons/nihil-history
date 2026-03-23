# nihil-history

`nihil-history` is a standalone offensive engagement knowledge tool.

It stores and links:

- engagements
- credentials
- hosts
- access links (`credential -> host -> protocol -> status`)

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
nxh engagement init acme-internal
nxh creds add -u admin -p 'P@ssw0rd!' -d ACME.LOCAL
nxh creds set --id 1
nxh creds rm --id 2
nxh hosts add --ip 10.10.10.10 --hostname DC01 --domain ACME.LOCAL
nxh hosts set --id 1
nxh hosts rm --id 2
nxh access link --cred-id 1 --host-id 1 --protocol smb --status valid
nxh access matrix
nxh access rm --id 3
nxh hosts import-nmap -f scan.xml
nxh env print --shell bash
nxh tui
nxh export json -o report.json
nxh export markdown -o report.md
```

## Notes

- Database schema is managed via Alembic migrations (`alembic/versions`).
- Optional at-rest secret encryption is available with `NIHIL_HISTORY_ENCRYPTION=1`.
- Input validation is strict for IP/domain/protocol/status and returns actionable CLI errors.
