# APK Site Config Guide

All runtime config is centralized in:

- `config/settings.json` (active settings)
- `config/settings.example.json` (baseline template)
- `.env` / system environment variables (highest priority)

## Priority

1. Environment variables (`.env` and system env)
2. `config/settings.json`
3. `config/settings.example.json`
4. Built-in defaults in `config.py`

## Key defaults

- `apk.dir`: `data/apk`
- `jenkins.instances_dir`: `data/jenkins_instances`
- `jenkins.builds_dir`: `data/jenkins_instances/default/jobs/Android/builds`
- `jenkins.image`: `jenkins/jenkins:lts-jdk17`
- `jenkins.container_name`: `apk-site-jenkins`
- `portal.mode`: `all`
- `portal.admin_port`: `5003`
- `portal.player_port`: `5004`
- `portal.forum_port`: `5005`

## Split deployment notes

When building split bundles (`admin-backend`, `forum-backend`, `player-static`):

- each backend bundle rewrites settings to local bundle paths
- Jenkins instance data is isolated under bundle-local `data/jenkins_instances`
- portal mode is rewritten per bundle (`admin` or `forum`)
- Jenkins bootstrap scripts are generated only for `admin-backend`

## Security-sensitive values

Keep secrets in `.env` (or external secret manager), not in JSON config:

- `JENKINS_TOKEN`
- database passwords
- webhook credentials
