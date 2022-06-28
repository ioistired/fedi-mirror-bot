#!/usr/bin/env python
# SPDX-License-Identifer: AGPL-3.0-only

import io
import sys
import anyio
import cursor
import aiohttp
import pleroma
import argparse
import platform
import pendulum
import aiosqlite
import contextlib
import qtoml as toml
from utils import suppress, loading_spinner
from pleroma import Pleroma
from functools import partial

USER_AGENT = (
	'mirror-bot; '
	f'{aiohttp.__version__}; '
	f'{platform.python_implementation()}/{platform.python_version()}'
)

UTC = pendulum.timezone('UTC')
JSON_CONTENT_TYPE = 'application/json'
ACTIVITYPUB_CONTENT_TYPE = 'application/activity+json'

class PostMirror:
	def __init__(self, *, config):
		self.config = config

	async def __aenter__(self):
		stack = contextlib.AsyncExitStack()
		self._fedi = await stack.enter_async_context(
			Pleroma(api_base_url=self.config['site'], access_token=self.config['access_token']),
		)
		self._http = await stack.enter_async_context(
			aiohttp.ClientSession(
				headers={
					'User-Agent': USER_AGENT,
					'Accept': ', '.join([JSON_CONTENT_TYPE, ACTIVITYPUB_CONTENT_TYPE]),
				},
				trust_env=True,
				raise_for_status=True,
			),
		)
		self._ctx_stack = stack
		return self

	async def __aexit__(self, *excinfo):
		return await self._ctx_stack.__aexit__(*excinfo)

	async def mirror_posts(self):
		spinner = loading_spinner()
		outbox = await self.fetch_outbox(self.config['account'])

		try:
			with open(self.config['timestamp_path']) as f:
				last_mirrored_at = pendulum.from_timestamp(float(f.read()))
		except FileNotFoundError:
			last_mirrored_at = pendulum.from_timestamp(0.0)

		page_url = outbox['first']
		posts = []
		print('Fetching posts to mirror...', end=' ')
		cursor.hide()
		done = False
		while not done:
			async with self._http.get(page_url) as resp: page = await resp.json()
			try:
				page_url = page['next']
			except KeyError:
				done = True

			print(next(spinner), end='', flush=True)

			for item in page['orderedItems']:
				post = item['object']
				published_at = pendulum.parse(post['published'])
				if published_at < last_mirrored_at:
					done = True
					break
				posts.append(post)

		print()
		cursor.show()

		if not posts:
			print('Nothing to do')
			return

		print('Mirroring posts...', end=' ')
		cursor.hide()
		for post in reversed(posts):  # oldest to newest
			# we use for ... await instead of a task group in order to ensure order is preserved
			# TODO mirror all attachments (from all posts) in parallel
			await self._mirror_post(post)
			print(next(spinner), end='', flush=True)

		print()
		cursor.show()

		with open(self.config['timestamp_path'], 'w') as f:
			f.write(str(pendulum.now('UTC').timestamp()))

	async def _mirror_post(self, post):
		attachments = [None] * len(post['attachment'])
		async with anyio.create_task_group() as tg:
			for i, attachment in enumerate(post['attachment']):
				tg.start_soon(self._mirror_attachment, i, attachments, attachment)

		assert None not in attachments

		await self._fedi.post(
			post['source'],
			cw=post['summary'],
			visibility='unlisted',
			media_ids=attachments,
		)

	async def _mirror_attachment(self, i, out_attachments, attachment):
		async with self._http.get(attachment['url']) as resp:
			data = await resp.read()
		out_attachments[i] = (await self._fedi.post_media(
			io.BytesIO(data),
			attachment['mediaType'],
			filename=attachment['name'],
			# TODO support descriptions
		))['id']

	async def fetch_outbox(self, handle):
		"""
		finger handle, a fully-qualified ActivityPub actor name,
		returning their outbox info
		"""
		# it's fucking incredible how overengineered ActivityPub is btw
		print('Fingering ', handle, '...', sep='')

		username, at, instance = handle.lstrip('@').partition('@')
		assert at == '@'

		# i was planning on doing /.well-known/host-meta to find the webfinger URL, but
		# 1) honk does not support host-meta
		# 2) WebFinger is always located at the same location anyway

		profile_url = await self._finger_actor(username, instance)

		try:
			async with self._http.get(profile_url) as resp: profile = await resp.json()
		except aiohttp.ContentTypeError:
			# we didn't get JSON, so just guess the outbox URL
			outbox_url = profile_url + '/outbox'
		else:
			outbox_url = profile['outbox']

		async with self._http.get(outbox_url) as resp: outbox = await resp.json()
		assert outbox['type'] == 'OrderedCollection'
		return outbox

	async def _finger_actor(self, username, instance):
		# despite HTTP being a direct violation of the WebFinger spec, assume e.g. Tor instances do not support
		# HTTPS-over-onion
		finger_url = f'http://{instance}/.well-known/webfinger?resource=acct:{username}@{instance}'
		async with self._http.get(finger_url) as resp: finger_result = await resp.json()
		return (profile_url := self._parse_webfinger_result(username, instance, finger_result))

	def _parse_webfinger_result(self, username, instance, finger_result):
		"""given webfinger data, return profile URL for handle"""
		def check_content_type(type, ct): return ct == type or ct.startswith(type+';')
		check_ap = partial(check_content_type, ACTIVITYPUB_CONTENT_TYPE)

		try:
			# note: the server might decide to return multiple links
			# so we need to decide how to prefer one.
			# i'd put "and yarl.URL(template).host == instance" here,
			# but some instances have no subdomain for the handle yet use a subdomain for the canonical URL.
			# Additionally, an instance could theoretically serve profile pages over I2P and the clearnet,
			# for example.
			return (profile_url := next(
				link['href']
				for link in finger_result['links']
				if link['rel'] == 'self' and check_ap(link['type'])
			))
		except StopIteration:
			# this should never happen either
			raise RuntimeError(f'fatal: while fingering {username}@{instance}, failed to find a profile URL')

async def amain():
	parser = argparse.ArgumentParser(description='Mirror posts from another fediverse account')
	parser.add_argument(
		'-c', '--cfg', dest='cfg', default='config.toml', nargs='?',
		help='Specify a custom location for the config file.'
	)
	args = parser.parse_args()
	with open(args.cfg) as f:
		config = toml.load(f)
	async with PostMirror(config=config) as pm: await pm.mirror_posts()

def main():
	try:
		anyio.run(amain)
	except KeyboardInterrupt:
		cursor.show()
		sys.exit(1)

if __name__ == '__main__':
	main()
