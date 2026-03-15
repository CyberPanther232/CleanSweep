![repo-logo](https://github.com/CyberPanther232/CleanSweep/blob/master/images/cleansweep_logo.png)

# CleanSweep

Author: CyberPanther232

CleanSweep is a Discord moderation and housekeeping bot built to automate long-term message cleanup while preserving operational visibility. It can monitor selected channels, remove messages based on retention policy and message filters, back up deleted content, compress archived data, and restore important messages from backup storage when needed. This bot is intended for homelab enthusiasts and regular discord server admins that are looking for new ways to clean up their server chats.


Features

- Monitor one or more Discord channels for scheduled cleanup.
- Persist monitored services in `service.csv` so the bot can resume after restart.
- Delete messages based on retention age and configuration-driven filters.
- Back up deleted messages before removal.
- Search active and compressed backups.
- Restore deleted messages from backup storage.
- Compress backup and log archives once configured size thresholds are reached.
- Remove CleanSweep-authored messages with an admin-only cleanup command.

## Commands

- `!service #channel` starts monitoring the selected channel.
- `!stop` stops monitoring the current channel.
- `!pause-services` pauses the deletion sweep.
- `!resume-services` resumes the deletion sweep.
- `!list-services` shows currently monitored channels.
- `!list-config` shows the loaded configuration values.
- `!reload-config` reloads `cs.conf` without restarting the bot.
- `!set-config KEY VALUE` updates a loaded configuration value in memory.
- `!save-config` writes the current in-memory configuration back to `cs.conf`.
- `!search-backups <query>` searches backups and compressed archives.
- `!restore <message_id>` restores a deleted message from backup storage.
- `!remove-bot-messages` removes CleanSweep-authored messages from the current channel.
- `!cleansweep-help` shows the bot help text.

## Configuration

Configuration is stored in `cs.conf`.

Important settings include:

- `MESSAGE_RETENTION_DAYS`: age threshold before a message is eligible for deletion.
- `MESSAGE_CHECK_INTERVAL`: seconds between sweep cycles.
- `LOGGING_ENABLED`: enables runtime log file persistence.
- `LOG_FILE_PATH`: file path or folder path for logs.
- `LOG_COMPRESS_THRESHOLD_MB`: compresses logs into `.gz` archives when the active log exceeds the configured size.
- `MESSAGE_BACKUP_ENABLED`: enables backup before deletion.
- `BACKUP_FILE_PATH`: file path or folder path for backups.
- `BACKUP_COMPRESS_THRESHOLD_MB`: compresses backups into `.gz` archives when the active backup exceeds the configured size.
- `DELETE_RATE_LIMIT_SECONDS`: delay between deletion operations.

Folder-style paths are supported. For example:

- `LOG_FILE_PATH = "logs/"`
- `BACKUP_FILE_PATH = "backups/"`
- `LOG_FILE_PATH = "/app/logs/"`
- `BACKUP_FILE_PATH = "/app/backups/"`

## Local Setup

### Requirements

- Python 3.13 or compatible runtime
- A Discord bot token with the required gateway intents and channel permissions

### Install

```bash
pip install -r requirements.txt
```

### Environment

Create a `.env` file with your bot token:

```env
DISCORD_TOKEN=your_token_here
```

### Run

```bash
python main.py
```

## Docker Setup

This project already includes a Dockerfile.

### Build

```bash
docker build -t cleansweep .
```

### Run

```bash
docker run --env-file .env --name cleansweep-bot cleansweep
```

### Optional Volume Mounts

If you want logs, backups, or service state to persist outside the container, mount local folders into `/app`:

```bash
docker run \
	--env-file .env \
	-v ./logs:/app/logs \
	-v ./backups:/app/backups \
	-v ./service.csv:/app/service.csv \
	--name cleansweep-bot \
	cleansweep
```

## Project Layout

```text
CleanSweep/
├── Dockerfile
├── ReadMe.md
├── cs.conf
├── main.py
├── requirements.txt
├── service.csv
├── logs/
└── backups/
```

## Notes

- The bot relies on Discord permissions to read history, delete messages, and post responses.
- Message restoration reposts a preserved copy of the deleted content, not the original Discord message object.
- Compressed backups and logs are stored as `.gz` archives in the same directory as their active files.
