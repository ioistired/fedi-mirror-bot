# SPDX-License-Identifier: AGPL-3.0-only

import anyio
import itertools
import contextlib
from functools import wraps

def as_corofunc(f):
	@wraps(f)
	async def wrapped(*args, **kwargs):
		# can't decide if i want an `anyio.sleep(0)` here.
		return f(*args, **kwargs)
	return wrapped

def as_async_cm(cls):
	@wraps(cls, updated=())  # cls.__dict__ doesn't support .update()
	class wrapped(cls, contextlib.AbstractAsyncContextManager):
		__aenter__ = as_corofunc(cls.__enter__)
		__aexit__ = as_corofunc(cls.__exit__)
	return wrapped

suppress = as_async_cm(contextlib.suppress)

def loading_spinner():
	return itertools.cycle('\b' + x for x in [
		'⠋',
		'⠙',
		'⠹',
		'⠸',
		'⠼',
		'⠴',
		'⠦',
		'⠧',
		'⠇',
		'⠏',
	])
