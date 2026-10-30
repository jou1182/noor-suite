# مصدر اللقطة

source_label: nmis-full-snapshot
tree_sha256: 09e6f53d04892fc7c946997ec46b3f22d298bb5d15cb362cfb362c734589438c
copied_at: 2026-10-30T21:02:00.136256+00:00
file_count: 109

## الملفات المضمَّنة
- *.py
- **/*.py
- templates/**
- static/**
- tests/**
- requirements*.txt

## الملفات المستبعدة
- deploy.py
- server_ssh.py
- server_autonomous_sync.py
- *.bat
- **/*.bat
- security_vault*
- **/security_vault*
- security_vault*/**
- **/security_vault*/**
- course_scripts/**
- archive/**
- Prepare_Mock_Data.py
- Simulate_Scenarios.py
- *_backup.py
- *_restore.py
- fix_schema.py
- new_tenant.py
- onboarding_wizard.py
- provision_instance.py
- pull_db_from_server.py
- sync_engineers*.py
- sync_provided_excel.py
- sync_server_to_local.py
- update_n8n*.py
- update_server_session.py
- health_check_now.py
- *.db
- *.sqlite*
- **/*.db
- **/*.sqlite*

Hard-coded forbidden families (FR-007) are always removed.

## التعرضات المغلقة
- none

## الفحص
- secrets_paths_ids: findings_resolved (version 2.0.0)
- forbidden_identities: clean (version 2.0.0)
- asset_metadata: clean (version 2.0.0)

The real source reference is kept by the owner outside the repository (decision 8).
