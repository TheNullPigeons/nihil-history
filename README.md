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
nhi engagement init acme-internal
nhi creds add -u admin -p 'P@ssw0rd!' -d ACME.LOCAL --type password --format ntlm
nhi creds set --id 1
nhi creds rm --id 2
nhi hosts add --ip 10.10.10.10 --hostname DC01 --domain ACME.LOCAL
nhi hosts set --id 1
nhi hosts rm --id 2
nhi access link --cred-id 1 --host-id 1 --protocol smb --status valid
nhi access matrix
nhi access rm --id 3
nhi hosts import-nmap -f scan.xml
nhi env print --shell bash
nhi tui
nhi export json -o report.json
nhi export markdown -o report.md
```

## Notes

- Database schema is managed via Alembic migrations (`alembic/versions`).
- Optional at-rest secret encryption is available with `NIHIL_HISTORY_ENCRYPTION=1`.
- Input validation is strict for IP/domain/protocol/status and returns actionable CLI errors.
- Preferred short command is `nhi` (`nxh` remains as compatibility alias).
- In TUI, press `h` to display allowed `cred_type`, protocol, status, and aliases.
- Credentials now support both `--type` and `--format` (for example `--type hash --format rc4`).
