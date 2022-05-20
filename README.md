# mirror-bot

Simple fedi bot which mirrors posts from another fedi account.
It's designed for cases when you want to defederate an entire instance except one account.

## Installation

```
$ python -m venv .venv
$ . .venv/bin/activate
$ pip install -Ur requirements.txt
$ cp config.example.toml config.toml
$ # fill out config.toml as needed
$ ./mirror_bot.py
```

Every time you run mirror_bot.py, the timestamp of the last post on the original account
will be checked against the timestamp file. If newer, the last post will be mirrored.

This should therefore be run as often as the original bot posts (e.g. using cron),
because any less often and the bot will miss some posts.

## License

AGPL-3.0-only, see LICENSE.md.
