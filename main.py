import discord
import os
import gzip
import shutil
from dotenv import load_dotenv
from datetime import datetime, timezone
import json
import asyncio

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

RUNTIME_LOG_SETTINGS = {
    "enabled": True,
    "path": "clean_sweep.log",
    "compress_threshold_mb": 0.0,
}

DEFAULT_LOG_FILENAME = "clean_sweep.log"
DEFAULT_BACKUP_FILENAME = "message_backup.json"

def get_current_time():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d %H:%M:%S UTC")

def ensure_parent_directory(file_path):
    directory = os.path.dirname(os.path.abspath(file_path))
    if directory:
        os.makedirs(directory, exist_ok=True)

def resolve_storage_path(configured_path, default_filename):
    raw_path = (configured_path or "").strip()
    if not raw_path:
        raw_path = default_filename

    normalized_path = raw_path.replace('\\', os.sep).replace('/', os.sep)
    looks_like_directory = (
        normalized_path.endswith(os.sep)
        or os.path.isdir(normalized_path)
        or os.path.splitext(os.path.basename(normalized_path))[1] == ""
    )

    if looks_like_directory:
        directory_path = normalized_path.rstrip(os.sep) or normalized_path
        absolute_directory = os.path.abspath(directory_path)
        os.makedirs(absolute_directory, exist_ok=True)
        return os.path.join(absolute_directory, default_filename)

    return os.path.abspath(normalized_path)

def update_runtime_log_settings(config):
    global RUNTIME_LOG_SETTINGS

    threshold_raw = config.get("LOG_COMPRESS_THRESHOLD_MB", "0")
    try:
        threshold = float(threshold_raw)
    except (TypeError, ValueError):
        threshold = 0.0

    RUNTIME_LOG_SETTINGS = {
        "enabled": str(config.get("LOGGING_ENABLED", "True")).lower() == "true",
        "path": resolve_storage_path(config.get("LOG_FILE_PATH", DEFAULT_LOG_FILENAME), DEFAULT_LOG_FILENAME),
        "compress_threshold_mb": max(threshold, 0.0),
    }

def compress_log_if_needed(log_path, threshold_mb):
    try:
        if threshold_mb <= 0 or not os.path.exists(log_path):
            return

        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        if size_mb < threshold_mb:
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base, ext = os.path.splitext(log_path)
        archive_path = f"{base}_{timestamp}{ext}.gz"

        with open(log_path, 'rb') as log_file:
            with gzip.open(archive_path, 'wb') as archive_file:
                shutil.copyfileobj(log_file, archive_file)

        with open(log_path, 'w', encoding='utf-8') as log_file:
            log_file.write("")

        print(
            f"[{get_current_time()}] CleanSweep: Log file compressed to {archive_path} "
            f"({size_mb:.2f} MB). Active log file reset."
        )
    except Exception as error:
        print(f"[{get_current_time()}] CleanSweep: Error compressing log file: {error}")

def generate_log_message(message):
    timestamp = get_current_time()
    log_message = f"[{timestamp}] CleanSweep: {message}"
    print(log_message)

    if RUNTIME_LOG_SETTINGS["enabled"]:
        try:
            log_path = RUNTIME_LOG_SETTINGS["path"]
            ensure_parent_directory(log_path)
            with open(log_path, 'a', encoding='utf-8') as log_file:
                log_file.write(log_message + "\n")
            compress_log_if_needed(log_path, RUNTIME_LOG_SETTINGS["compress_threshold_mb"])
        except Exception as error:
            print(f"[{get_current_time()}] CleanSweep: Error writing log file: {error}")

    return log_message

def load_configuration():
    config = {}
    try:
        with open('cs.conf', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    if "#" in value:
                        value = value.split('#', 1)[0].strip()
                    config[key.strip()] = value.replace('"', '').replace("'", "").strip()
        update_runtime_log_settings(config)
        generate_log_message("Configuration loaded successfully.")
    except Exception as e:
        generate_log_message(f"Error loading configuration: {e}")
    return config

def compress_backup_if_needed(backup_path, threshold_mb):
    """Compress the backup JSON into a timestamped .gz archive if it exceeds threshold_mb."""
    try:
        backup_path = resolve_storage_path(backup_path, DEFAULT_BACKUP_FILENAME)
        if not os.path.exists(backup_path):
            return
        size_mb = os.path.getsize(backup_path) / (1024 * 1024)
        if size_mb < threshold_mb:
            return
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base, _ = os.path.splitext(backup_path)
        archive_path = f"{base}_{timestamp}.gz"
        with open(backup_path, 'rb') as f_in:
            with gzip.open(archive_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        # Reset the active backup file
        with open(backup_path, 'w') as f:
            json.dump([], f)
        generate_log_message(
            f"Backup compressed to {archive_path} ({size_mb:.2f} MB). Active backup file reset."
        )
    except Exception as e:
        generate_log_message(f"Error compressing backup file: {e}")


def search_backups(query, backup_path="message_backup.json"):
    """Search the active backup file and all .gz archives for records matching query.
    Matches against message content, author, message_id, and channel_id."""
    results = []
    query_lower = query.lower()

    def matches(record):
        return (
            query_lower in record.get("content", "").lower()
            or query_lower in record.get("author", "").lower()
            or query == record.get("message_id", "")
            or query == record.get("channel_id", "")
        )

    backup_abs = resolve_storage_path(backup_path, DEFAULT_BACKUP_FILENAME)
    backup_dir = os.path.dirname(backup_abs)
    base_name = os.path.splitext(os.path.basename(backup_abs))[0]

    # Search active backup file
    try:
        if os.path.exists(backup_abs) and os.path.getsize(backup_abs) > 0:
            with open(backup_abs, 'r') as f:
                for record in json.load(f):
                    if matches(record):
                        results.append(record)
    except Exception as e:
        generate_log_message(f"Error searching active backup: {e}")

    # Search all compressed archives with the same base name
    try:
        for filename in sorted(os.listdir(backup_dir)):
            if filename.startswith(base_name + "_") and filename.endswith(".gz"):
                archive_path = os.path.join(backup_dir, filename)
                try:
                    with gzip.open(archive_path, 'rt', encoding='utf-8') as f:
                        for record in json.load(f):
                            if matches(record):
                                results.append(record)
                except Exception as e:
                    generate_log_message(f"Error searching archive {filename}: {e}")
    except Exception as e:
        generate_log_message(f"Error listing backup directory for search: {e}")

    generate_log_message(f"Backup search for '{query}' returned {len(results)} result(s).")
    return results


def build_restore_embed(record):
    """Build a Discord embed representing a backed-up deleted message."""
    content = record.get("content") or "*[no text content]*"
    if len(content) > 2000:
        content = content[:1997] + "..."
    embed = discord.Embed(
        title="\U0001f5c3\ufe0f Restored Deleted Message",
        color=discord.Color.orange(),
        description=content
    )
    embed.add_field(name="Original Author", value=record.get("author", "Unknown"), inline=True)
    embed.add_field(name="Message ID", value=record.get("message_id", "Unknown"), inline=True)
    embed.add_field(name="Channel ID", value=record.get("channel_id", "Unknown"), inline=True)
    embed.add_field(name="Deleted On", value=record.get("deleted_on", "Unknown"), inline=True)
    attachments = record.get("attachments", [])
    if attachments:
        attachment_list = "\n".join(attachments[:5])
        if len(attachments) > 5:
            attachment_list += f"\n*({len(attachments) - 5} more not shown)*"
        embed.add_field(name=f"Attachments ({len(attachments)})", value=attachment_list, inline=False)
    embed.set_footer(text="Restored from CleanSweep backup \u2014 this is a copy, not the original message.")
    return embed


def generate_backup_storage(backup_path="message_backups.json"):
    
    # Message Backup Structure:
    # messages[0]{channel_id, message_id, deleted_on, content, author, attachments, embeds}
    
    try:
        backup_path = resolve_storage_path(backup_path, DEFAULT_BACKUP_FILENAME)
        if not os.path.exists(backup_path):
            ensure_parent_directory(backup_path)
            with open(backup_path, 'w') as f:
                json.dump([], f)
            generate_log_message(f"Backup storage created at {backup_path}.")
        else:
            generate_log_message(f"Backup storage already exists at {backup_path}.")
    
    except Exception as e:
        generate_log_message(f"Error creating backup storage: {e}")

def backup_message(message, backup_path="message_backups.json", threshold_mb=0):
    try:
        backup_path = resolve_storage_path(backup_path, DEFAULT_BACKUP_FILENAME)
        backup_data = {
            "channel_id": str(message.channel.id),
            "message_id": str(message.id),
            "deleted_on": get_current_time(),
            "content": message.content,
            "author": str(message.author),
            "attachments": [str(attachment.url) for attachment in message.attachments],
            "embeds": [str(embed.to_dict()) for embed in message.embeds]
        }

        existing = []
        if os.path.exists(backup_path) and os.path.getsize(backup_path) > 0:
            with open(backup_path, 'r') as f:
                existing = json.load(f)

        existing.append(backup_data)

        ensure_parent_directory(backup_path)
        with open(backup_path, 'w') as f:
            json.dump(existing, f, indent=2)

        generate_log_message(f"Message {message.id} backed up successfully.")

        if threshold_mb > 0:
            compress_backup_if_needed(backup_path, threshold_mb)
    except Exception as e:
        generate_log_message(f"Error backing up message {message.id}: {e}")

def generate_service_storage():
    try:
        if not os.path.exists('service.csv'):
            with open('service.csv', 'w') as f:
                f.write("channel_id,channel_name,started_on\n")
            generate_log_message("Service storage created at service.csv.")
        else:
            generate_log_message("Service storage already exists at service.csv.")
    except Exception as e:
        generate_log_message(f"Error creating service storage: {e}")

def update_service_storage(channel):
    try:
        
        # Read existing entries to avoid duplicates
        existing_ids = set()
        if os.path.exists('service.csv'):
            with open('service.csv', 'r') as f:
                next(f)  # Skip header
                for line in f:
                    parts = line.strip().split(',')
                    if parts:
                        existing_ids.add(parts[0])
        
        if str(channel.id) not in existing_ids:
            with open('service.csv', 'a') as f:
                f.write(f"{channel.id},{channel.name},{get_current_time()}\n")
            generate_log_message(f"Service storage updated for channel {channel.id}.")
    except Exception as e:
        generate_log_message(f"Error updating service storage: {e}")

def remove_service_storage(channel):
    try:
        if not os.path.exists('service.csv'):
            generate_log_message("Service storage file does not exist. Cannot remove entry.")
            return
        
        with open('service.csv', 'r') as f:
            lines = f.readlines()
        
        with open('service.csv', 'w') as f:
            for line in lines:
                if not line.startswith(str(channel.id) + ","):
                    f.write(line)
        
        generate_log_message(f"Service storage entry removed for channel {channel.id}.")
    except Exception as e:
        generate_log_message(f"Error removing service storage entry: {e}")

def check_service_storage():
    try:
        if not os.path.exists('service.csv'):
            generate_log_message("Service storage file does not exist. No active services.")
            return []
        
        channels = []
        
        with open('service.csv', 'r') as f:
            content = f.readlines()
            for line in content[1:]:  # Skip header
                parts = line.strip().split(',')
                generate_log_message(f"Active service found: Channel ID {parts[0]}, Name {parts[1]}, Started On {parts[2]}")
                channels.append(parts[0])
            channels = list({int(c) for c in channels})  # deduplicate and convert to int
        generate_log_message(f"Checked service storage: {len(channels)} active service(s) found.")
        return channels
    except Exception as e:
        generate_log_message(f"Error checking service storage: {e}")
        return []

def log_deletion(message, log_path):
    try:
        preview = message.content[:80].replace('\n', ' ') if message.content else "[no content]"
        log_entry = (
            f"[{get_current_time()}] Deleted | Channel: #{message.channel.name} | "
            f"Author: {message.author} | MsgID: {message.id} | Content: {preview}\n"
        )
        with open(log_path, 'a') as f:
            f.write(log_entry)
    except Exception as e:
        generate_log_message(f"Error writing to log file: {e}")


def should_delete(message, client_user, config):
    retention_days = int(config.get("MESSAGE_RETENTION_DAYS", "7"))
    age = datetime.now(timezone.utc) - message.created_at
    if age.days < retention_days:
        return False

    if message.pinned and config.get("DELETE_PINNED_MESSAGES", "false").lower() != "true":
        return False

    if message.author == client_user:
        if config.get("DELETE_CS_MESSAGES", "true").lower() != "true":
            return False
    elif message.author.bot:
        if config.get("DELETE_MESSAGES_FROM_BOTS", "true").lower() != "true":
            return False
    else:
        if config.get("DELETE_MESSAGES_FROM_USERS", "true").lower() != "true":
            return False

    if message.attachments and config.get("DELETE_MESSAGES_WITH_ATTACHMENTS", "true").lower() != "true":
        return False

    return True


def main():

    generate_log_message("Starting CleanSweep Bot...")
    
    generate_log_message("Loading configuration...")
    config = load_configuration()

    print(config)  # Debug: Print the loaded configuration
    
    generate_service_storage()
    
    
    if config["MESSAGE_BACKUP_ENABLED"].lower() == "true":
        generate_log_message("Message backup is enabled. Setting up backup storage...")
        generate_backup_storage(config["BACKUP_FILE_PATH"])
    else:
        generate_log_message("Message backup is disabled. Skipping backup storage setup.")

    generate_log_message("Initializing Discord client...")


    global monitored_channels
    monitored_channels = check_service_storage()
    global service_started
    
    if monitored_channels:
        generate_log_message(f"Resuming monitoring for {len(monitored_channels)} channel(s) from service storage.")
        service_started = True
    else:
        generate_log_message("No active services found in storage. CleanSweep will wait for commands to start monitoring channels.")
        service_started = False
    
    service_paused = False

    bot_intents = discord.Intents.default()
    bot_intents.message_content = True

    client = discord.Client(intents=bot_intents)

    sweep_task = None

    async def deletion_sweep():
        await client.wait_until_ready()
        while not client.is_closed():
            check_interval = int(config.get("MESSAGE_CHECK_INTERVAL", "60"))
            await asyncio.sleep(check_interval)
            if not monitored_channels or service_paused:
                continue
            generate_log_message("Running deletion sweep...")
            for channel_id in list(monitored_channels):
                if service_paused:
                    generate_log_message("Deletion sweep paused mid-run.")
                    break
                channel = client.get_channel(channel_id)
                if channel is None:
                    continue
                try:
                    deleted_count = 0
                    rate_limit = float(config.get("DELETE_RATE_LIMIT_SECONDS", "1.0"))
                    async for message in channel.history(limit=None, oldest_first=True):
                        if service_paused:
                            generate_log_message(f"Deletion sweep paused mid-sweep in #{channel.name}.")
                            break
                        if should_delete(message, client.user, config):
                            if config.get("MESSAGE_BACKUP_ENABLED", "false").lower() == "true":
                                backup_message(
                                    message,
                                    config.get("BACKUP_FILE_PATH", "message_backup.json"),
                                    float(config.get("BACKUP_COMPRESS_THRESHOLD_MB", "0"))
                                )
                            if config.get("LOGGING_ENABLED", "false").lower() == "true":
                                log_deletion(message, config.get("LOG_FILE_PATH", "clean_sweep.log"))
                            await message.delete()
                            deleted_count += 1
                            await asyncio.sleep(rate_limit)
                    if deleted_count:
                        generate_log_message(f"Sweep complete for #{channel.name}: {deleted_count} message(s) deleted.")
                    else:
                        generate_log_message(f"Sweep complete for #{channel.name}: no messages to delete.")
                except discord.Forbidden:
                    generate_log_message(f"Missing permissions to delete messages in #{channel.name}.")
                except discord.NotFound:
                    pass  # Message already deleted (e.g. by !remove-bot-messages running concurrently)
                except Exception as e:
                    generate_log_message(f"Error during sweep of channel {channel_id}: {e}")

    async def enumerate_guilds():
        try:
            guilds = client.guilds
            generate_log_message(f"Enumerated {len(guilds)} guild(s).")
            for guild in guilds:
                generate_log_message(f"Guild: {guild.name} (ID: {guild.id})")
            return guilds
        except Exception as e:
            generate_log_message(f"Error enumerating guilds: {e}")
            return []
        
    @client.event
    async def on_ready():
        nonlocal sweep_task

        generate_log_message(f'Logged in as {client.user}')

        if sweep_task is None or sweep_task.done():
            sweep_task = asyncio.ensure_future(deletion_sweep())
            generate_log_message("Deletion sweep task started.")

        while True:
            guilds = await enumerate_guilds()

            if guilds:
                channels = guilds[0].text_channels
            else:
                channels = []

            if not service_started:

                message = (
                    "CleanSweep needs to know what channels to run the cleaning service on.\n"
                    "Please use the command `!service #channel-name` in the desired channels.\n\n"
                    "Example: `!service #general`\n\n"
                    "Channels available in this server:\n"
                )

                message += "\n".join(
                    f"- {channel.name} (ID: {channel.id})" for channel in channels
                )

                for channel in channels:
                    try:
                        await channel.send(message)
                        break  # send only once to the first available channel
                    except:
                        continue

                await asyncio.sleep(300)

            else:
                await asyncio.sleep(3600)

    @client.event
    async def on_message(message):

        global service_started
        nonlocal service_paused

        if message.author == client.user:
            return

        if message.content.startswith('!cleansweep-help'):
            help_message = (
                "🧹 **CleanSweep Bot Help** 🧹\n\n"
                "**Commands:**\n"
                "`!service #channel` - Start cleaning service on the specified channel.\n"
                "`!stop` - Stop cleaning service on the current channel.\n\n"
                "`!pause-services` - Pause the cleaning service.\n"
                "`!resume-services` - Resume the cleaning service.\n\n"
                "`!list-services` - List all channels currently monitored by CleanSweep.\n\n"
                "`!list-config` - List the current configuration settings.\n"
                "`!reload-config` - Reload configuration from cs.conf file.\n"
                "`!set-config KEY VALUE` - Update a specific configuration setting.\n"
                "`!save-config` - Save the current configuration to cs.conf file.\n\n"
                "`!search-backups <query>` - Search deleted message backups by content, author, or ID.\n"
                "`!restore <message_id>` - Restore a deleted message by its original message ID.\n\n"
                "`!cleansweep` - Get a link to the CleanSweep GitHub repository.\n\n"
                "`!cleansweep-help` - Show this help message.\n\n"
                "`!remove-bot-messages` - Remove all messages sent by CleanSweep in the current channel (admin only).\n\n"
                "**Note:**\n"
                "CleanSweep will automatically delete messages in monitored channels based on the configured retention policy. "
                "Use the above commands to manage which channels are monitored."
            )
            await message.channel.send(help_message)
            return
        
        if message.content.startswith('!list-services'):
            if not monitored_channels:
                await message.channel.send("CleanSweep is not currently monitoring any channels.")
                return
            
            channel_mentions = []
            for channel_id in monitored_channels:
                channel = client.get_channel(channel_id)
                if channel:
                    channel_mentions.append(f"{channel.mention} (ID: {channel.id})")
                else:
                    channel_mentions.append(f"Unknown Channel (ID: {channel_id})")

            await message.channel.send(
                "🧹 **CleanSweep is currently monitoring the following channels:**\n" +
                "\n".join(channel_mentions)
            )
            return
        
        if message.content.startswith('!pause-services'):
            if not service_started:
                await message.channel.send("CleanSweep has no active cleaning service to pause.")
                return
            if service_paused:
                await message.channel.send("CleanSweep is already paused. Use `!resume-services` to resume.")
                return

            service_paused = True
            await message.channel.send("\u23f8\ufe0f CleanSweep has paused the cleaning service. Use `!resume-services` to resume.")
            generate_log_message("Cleaning service paused by user command.")
            return
        
        if message.content.startswith('!resume-services'):
            if not service_started:
                await message.channel.send("CleanSweep has no active cleaning service to resume.")
                return
            if not service_paused:
                await message.channel.send("CleanSweep is not paused. Use `!stop` to stop monitoring a channel.")
                return

            service_paused = False
            await message.channel.send("\u25b6\ufe0f CleanSweep has resumed the cleaning service.")
            generate_log_message("Cleaning service resumed by user command.")
            return
        
        if message.content.startswith('!list-config'):
            await message.channel.send(
                "🧹 **Current CleanSweep Configuration:** 🧹\n\n" +
                "\n".join(f"- {key}: {value}" for key, value in config.items())
            )
            return

        if message.content.startswith('!reload-config'):
            new_config = load_configuration()
            if new_config:
                config.update(new_config)
                update_runtime_log_settings(config)
                await message.channel.send("🔄 Configuration reloaded successfully.")
                generate_log_message("Configuration reloaded by user command.")
            else:
                await message.channel.send("⚠️ Failed to reload configuration. Check logs for details.")
            return
        
        if message.content.startswith('!set-config'):
            parts = message.content.split(' ', 2)
            if len(parts) != 3:
                await message.channel.send("Usage: `!set-config KEY VALUE`")
                return
            
            key, value = parts[1], parts[2]
            if key not in config:
                await message.channel.send(f"Invalid configuration key. Available keys: {', '.join(config.keys())}")
                return
            
            config[key] = value
            update_runtime_log_settings(config)
            await message.channel.send(f"✅ Configuration updated: {key} set to {value}")
            generate_log_message(f"Configuration updated by user command: {key} set to {value}")
            return

        if message.content.startswith('!save-config'):
            try:
                with open('cs.conf', 'w') as f:
                    for key, value in config.items():
                        f.write(f"{key}={value}\n")
                await message.channel.send("💾 Configuration saved to cs.conf successfully.")
                generate_log_message("Configuration saved to cs.conf by user command.")
            except Exception as e:
                await message.channel.send(f"⚠️ Failed to save configuration: {e}")
                generate_log_message(f"Error saving configuration to cs.conf: {e}")
            return

        if message.content.startswith('!search-backups'):
            parts = message.content.split(' ', 1)
            if len(parts) < 2 or not parts[1].strip():
                await message.channel.send(
                    "Usage: `!search-backups <query>`\n"
                    "Searches message content, author name, message ID, and channel ID across all backups and archives."
                )
                return

            query = parts[1].strip()
            backup_path = config.get("BACKUP_FILE_PATH", "message_backup.json")
            results = search_backups(query, backup_path)

            if not results:
                await message.channel.send(f"\U0001f50d No backup records found matching **{discord.utils.escape_markdown(query)}**.")
                return

            total = len(results)
            display = results[:10]

            embed = discord.Embed(
                title="\U0001f50d Backup Search Results",
                color=discord.Color.blurple(),
                description=(
                    f"Query: **{discord.utils.escape_markdown(query)}** \u2014 "
                    f"Found **{total}** record(s){'.' if total <= 10 else ', showing first 10.'}"
                )
            )
            for i, record in enumerate(display, 1):
                raw_content = record.get("content") or "[no content]"
                preview = raw_content[:120] + ("..." if len(raw_content) > 120 else "")
                embed.add_field(
                    name=f"#{i} \u2014 {record.get('author', 'Unknown')} | {record.get('deleted_on', 'Unknown')}",
                    value=f"**MsgID:** `{record.get('message_id', 'N/A')}`\n{discord.utils.escape_markdown(preview)}",
                    inline=False
                )
            if total > 10:
                embed.set_footer(text=f"{total - 10} more result(s) not shown. Refine your search or use !restore <message_id> to retrieve a specific message.")

            await message.channel.send(embed=embed)
            return

        if message.content.startswith('!restore'):
            parts = message.content.split(' ', 1)
            if len(parts) < 2 or not parts[1].strip():
                await message.channel.send("Usage: `!restore <message_id>`")
                return

            msg_id = parts[1].strip()
            backup_path = config.get("BACKUP_FILE_PATH", "message_backup.json")
            results = search_backups(msg_id, backup_path)
            exact = [r for r in results if r.get("message_id") == msg_id]

            if not exact:
                await message.channel.send(f"\u26a0\ufe0f No backup found for message ID `{discord.utils.escape_markdown(msg_id)}`.")
                return

            embed = build_restore_embed(exact[0])
            await message.channel.send(embed=embed)
            generate_log_message(f"Message {msg_id} restored to #{message.channel.name} by {message.author}.")
            return

        if message.content.startswith('!service'):

            if not message.channel_mentions:
                await message.channel.send("Usage: `!service #channel`")
                return

            channel = message.channel_mentions[0]

            if channel.id not in monitored_channels:
                monitored_channels.append(channel.id)

            service_started = True

            await message.channel.send(
                f"🧹 CleanSweep is now running cleaning service on {channel.mention}!\n"
                "If you want to stop the service, use `!stop` in the same channel."
            )
            
            generate_log_message(f"Started monitoring channel: {channel.name} (ID: {channel.id})")
            update_service_storage(channel)
            
        if message.content.startswith('!stop'):
            if message.channel.id in monitored_channels:
                monitored_channels.remove(message.channel.id)
                await message.channel.send(
                    f"🛑 CleanSweep has stopped cleaning service on {message.channel.mention}."
                )
                generate_log_message(f"Stopped monitoring channel: {message.channel.name} (ID: {message.channel.id})")
                remove_service_storage(message.channel)
            else:
                await message.channel.send("CleanSweep is not currently monitoring this channel.")

        if message.content.startswith('!remove-bot-messages'):
            if not message.channel.permissions_for(message.author).manage_messages:
                await message.channel.send("⛔ You need the **Manage Messages** permission to use this command.")
                return

            target_channel = message.channel
            requester = message.author
            rate_limit = float(config.get("DELETE_RATE_LIMIT_SECONDS", "1.0"))

            await target_channel.send("🧹 Removing CleanSweep messages in the background...")

            async def _do_remove():
                deleted_count = 0
                try:
                    async for msg in target_channel.history(limit=None, oldest_first=True):
                        if msg.author == client.user:
                            try:
                                await msg.delete()
                                deleted_count += 1
                            except discord.NotFound:
                                pass  # Already deleted by concurrent sweep
                            except discord.Forbidden:
                                break
                            await asyncio.sleep(rate_limit)

                    try:
                        await target_channel.send(
                            f"✅ Removed **{deleted_count}** CleanSweep message(s) from {target_channel.mention}."
                        )
                    except discord.Forbidden:
                        pass
                    generate_log_message(
                        f"Removed {deleted_count} bot message(s) from #{target_channel.name} "
                        f"by request of {requester}."
                    )
                except discord.Forbidden:
                    await target_channel.send("⛔ CleanSweep does not have permission to delete messages in this channel.")
                except Exception as e:
                    generate_log_message(f"Error during !remove-bot-messages in #{target_channel.name}: {e}")

            asyncio.create_task(_do_remove())
    
    @client.event
    async def on_message_delete(message):
        if message.channel.id not in monitored_channels:
            return
        if config.get("MESSAGE_BACKUP_ENABLED", "false").lower() == "true":
            backup_message(
                message,
                config.get("BACKUP_FILE_PATH", "message_backup.json"),
                float(config.get("BACKUP_COMPRESS_THRESHOLD_MB", "0"))
            )
        await asyncio.sleep(5)  # Slows down the backup process to avoid hitting rate limits during mass deletions


    client.run(TOKEN)

if __name__ == "__main__":
    main()