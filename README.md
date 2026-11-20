# Telegram bot on a Linux VPS

Use Python 3.11+ with current security updates, or a Python version still
security-maintained by your Linux distribution, and systemd. No pip packages, public HTTP port, domain or certificate
are needed for this polling example. It echoes text in private chats only.

Russian guide: [VPS для Telegram-бота](https://motsell.com/ru/guides/vps-dlya-bota?utm_source=github&utm_medium=repository&utm_campaign=telegram_bot_example_20261119&utm_content=readme_ru).
English guide: [VPS for a Telegram bot](https://motsell.com/en/guides/vps-for-bots?utm_source=github&utm_medium=repository&utm_campaign=telegram_bot_example_20261119&utm_content=readme_en).

Need a server before installing? [Current VPS plans (EN)](https://motsell.com/en/vps-vds?utm_source=github&utm_medium=repository&utm_campaign=telegram_bot_example_20261119&utm_content=readme_plan_en#order) · [Тарифы VPS (RU)](https://motsell.com/ru/vps-vds?utm_source=github&utm_medium=repository&utm_campaign=telegram_bot_example_20261119&utm_content=readme_plan_ru#order). Choose a configuration for your own bot's requirements and check the required country and Telegram connectivity before deployment.

### Перенос уже работающего бота

Если у вас уже есть один Python-бот на Linux с long polling и локальной SQLite
(или без базы), [проверьте условия пилота переноса на VPS MOTSELL](https://motsell.com/ru/perenos-telegram-bota?utm_source=github&utm_medium=repository&utm_campaign=telegram_bot_example_20261119&utm_content=migration_pilot#request).
В пилоте до трёх подходящих проектов: разовый перенос, настройка автозапуска и
проверка после переключения. Возможность переноса подтверждаем до оплаты VPS;
вебхуки и доработка кода не входят. Не передавайте токен или данные бота в GitHub.

## Install on your own server

Use a separate test bot created with BotFather. An existing webhook is detected
and left untouched. Do not run two polling processes with the same token.
Install Python 3 using your distribution's supported packages if it is missing.

After extracting the archive, review bot.py and the service file. Check that the
example has not already been installed; these instructions must not replace a
working service or token file. Run this as one block; its subshell stops on the
first error and refuses existing paths, including symbolic links:

```sh
(
  set -eu
  for demo_path in /opt/motsell-bot-demo /etc/motsell-bot-demo.env /etc/systemd/system/motsell-bot-demo.service; do
    if sudo test -e "$demo_path" || sudo test -L "$demo_path"; then
      printf 'Refusing to replace existing path: %s\n' "$demo_path" >&2
      exit 1
    fi
  done
  sudo install -d -m 0755 /opt/motsell-bot-demo
  sudo install -m 0644 bot.py /opt/motsell-bot-demo/bot.py
  sudo install -m 0600 .env.example /etc/motsell-bot-demo.env
  sudo install -m 0644 motsell-bot-demo.service /etc/systemd/system/motsell-bot-demo.service
)
```

Continue only if that block succeeds. Set the token in the editor:

```sh
sudoedit /etc/motsell-bot-demo.env
```

In the editor, replace the placeholder with the token. Do not paste the token
into a shell command, chat, public screenshot or repository.

```sh
sudo systemd-analyze verify /etc/systemd/system/motsell-bot-demo.service
sudo systemctl daemon-reload
sudo systemctl enable --now motsell-bot-demo.service
sudo systemctl status motsell-bot-demo.service
```

Send a message to your test bot. Then restart the service and send another:

```sh
sudo systemctl restart motsell-bot-demo.service
sudo journalctl -u motsell-bot-demo.service -n 30 --no-pager
```

Restarting the process tests service recovery; only an actual controlled reboot
of your server tests startup after reboot. Do not reboot a server hosting other
applications just to try this example.

## What the example does

- Stores only the next update offset in /var/lib/motsell-bot-demo/offset.json.
- Uses an unprivileged dynamic service user; the token file is root-readable.
- Does not log tokens, Telegram request URLs, message text or chat IDs.
- Sends requests only to the Telegram HTTPS API without following redirects.
- Retries transient API/network errors with a delay and respects retry_after.
- Skips replies rejected with HTTP 400 or 403 so one invalid or unavailable chat does not block polling.
- Stops on invalid credentials or an active webhook instead of changing it.

This is a learning example, not a high-availability or payment-processing bot.
A crash after sending a reply but before persisting its offset can duplicate the
reply. The offset file is not a backup of your application's data. Back up actual
business data outside the VPS, and test its restoration separately.

The 128 MB service memory cap bounds this demo; it is not a measurement or sizing
promise for another bot. Choose CPU and RAM from the real workload.

## Verification scope

The accompanying repository checks use mocked Telegram responses: they test
restart offset recovery, API error handling and secret-safe error messages.
They do not send real Telegram messages or prove your server's network route.
Check actual Telegram connectivity and service startup on your own test server.

MOTSELL provides the VPS and its management. The customer maintains the
application, updates, secrets and backups unless separately agreed.

## License

MIT. See [LICENSE](LICENSE).

## Sources

- https://core.telegram.org/bots/api#getupdates
- https://core.telegram.org/bots/api#getwebhookinfo
- https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
