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

Every time you run mirror_bot.py, all posts since the last run will be mirrored.

## License

AGPL-3.0-only, see LICENSE.md.
