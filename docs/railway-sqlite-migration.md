# Moving a Telegram bot from Railway to a Linux VPS? Verify the SQLite snapshot

A bot can start successfully after migration and still be missing its latest records. In WAL mode, committed changes can still be in `bot.db-wal`. Copying only `bot.db` can give you a readable but stale database.

We tested this with synthetic polling updates in two local Linux containers. Both exports were 12,288 bytes and passed `PRAGMA integrity_check`.

| Export | Latest update | Next polling offset |
| --- | ---: | ---: |
| Main `.db` file alone | 40 | 41 |
| SQLite `.backup` snapshot | 41 | 42 |

The test used a single writer and stored the offset in SQLite. Check where your own bot saves its cursor. This lab did not run a Railway deployment or send messages through Telegram.

## Rehearse the export while the Railway service is accessible

1. Link the Railway CLI to the correct project, environment and service. Find the database path in the running service and identify whether it is on an attached volume. In `railway ssh`, set `umask 077` and make a consistent [SQLite `.backup` snapshot](https://www.sqlite.org/backup.html) in a new private directory. Use a supported SQLite build with the [WAL-reset fix](https://www.sqlite.org/wal.html).
2. Before downloading, create a private local directory with permissions `0700` outside repositories and synced folders. Set `umask 077` in the download shell and use a fresh destination there. If you saved the snapshot at `/data/migration/bot.sqlite3` on a volume mounted at `/data`, use `railway volume files download /migration/bot.sqlite3 /private-export/bot.sqlite3`. For a snapshot at `/app/migration/bot.sqlite3` in a running service filesystem, use `railway service files download /app/migration/bot.sqlite3 /private-export/bot.sqlite3`. Replace `/private-export` with your private local directory. If the deployment is inaccessible, check for an existing backup or restore official access before planning a cutover.
3. Restore the snapshot into a separate directory on the VPS. Check `PRAGMA integrity_check;`, a known recent record and the polling cursor or other application state. Use a separate test token if you run a test bot. Keep the original service available for the final export.

See [Railway volume files](https://docs.railway.com/volumes#manage-volume-files) and [Railway service files](https://docs.railway.com/services#manage-service-files) for the current CLI syntax.

## Switch with one poller

Pause the source worker and let its writes finish while the filesystem is still accessible. Rehearse how you will retain file access if stopping the worker also stops the container. Take and check a fresh snapshot, then confirm that the old poller is stopped and cannot restart before starting the new one. Test a response and check the resulting record on the VPS.

In the lab, update 43 existed only in the new container after the switch. If you need to return to the old server after the new worker writes or calls an external API, stop the new worker and reconcile current state first. Telegram may already have [confirmed consumed updates](https://core.telegram.org/bots/api#getupdates).

[Linux VPS setup for a Telegram bot](https://motsell.com/en/guides/vps-for-bots?utm_source=github&utm_medium=repository&utm_campaign=railway_sqlite_migration_20261121&utm_content=railway_walkthrough_en) · [Russian walkthrough and MOTSELL migration pilot](railway-sqlite-migration.ru.md)
