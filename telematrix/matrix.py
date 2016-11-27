import urllib.parse as urlparse
import json
import re
from aiohttp import web

from telematrix import db


def create_response(code, obj):
    """
    Create an HTTP response with a JSON body.
    :param code: The status code of the response.
    :param obj: The object to serialize and include in the response.
    :return: A web.Response.
    """
    return web.Response(text=json.dumps(obj), status=code,
                        content_type='application/json', charset='utf-8')


class Matrix:
    ERR_FORBIDDEN = 'M_FORBIDDEN'
    ERR_UNAUTHORIZED = 'NL.SIJMENSCHOON.TELEMATRIX_UNAUTHORIZED'
    ERR_NOT_FOUND = 'NL.SIJMENSCHOON.TELEMATRIX_NOT_FOUND'

    RE_ALIAS = re.compile(r'^#(.*)_([\d-]*):(.*)$')

    def __init__(self, loop, config):
        self.app = web.Application(loop=loop)
        self.app.router.add_route('GET', '/rooms/{room_alias}', self.req_room)
        self.app.router.add_route('PUT', '/transactions/{transaction}',
                                  self.req_transaction)

        self.config = config

    def run(self, port):
        """
        Runs the telematrix app using the aiotg loop, also executing everything
        else on the loop.
        """
        web.run_app(self.app, port=port)

    def parse_alias(self, alias):
        """
        Parses a Matrix alias of the telmatrix format (#prefix_tgchat:host).

        :param alias: An alias of the telematrix format.
        :return: None if not a telematrix alias, (prefix, tgchat, host)
                 otherwise.
        """
        match = self.RE_ALIAS.match(alias)
        if not match:
            return None

        try:
            prefix = match.group(1)
            tg_chat = match.group(2)
            host = match.group(3)
        except IndexError:
            return None

        # Check if the alias is for telematrix
        if prefix != self.config.room_prefix:
            return None
        if host != self.config.matrix_host_bare:
            return None

        return prefix, tg_chat, host

    async def req_room(self, request):
        """
        Process a request to /room/{room_id}.

        Checks if the access token is correct and checks if the link already
        exists. If not, returns a 404.
        """
        room_alias = request.match_info['room_alias']
        args = urlparse.parse_qs(urlparse.urlparse(request.path_qs).query)

        # Check if the access token is supplied and valid
        try:
            if args['access_token'][0] != self.config.hs_token:
                return create_response(403, {'errcode': Matrix.ERR_FORBIDDEN})
        except KeyError:
            return create_response(401, {'errcode': Matrix.ERR_UNAUTHORIZED})

        # Retrieve the Telegram group ID from the alias
        parsed = self.RE_ALIAS.match(room_alias)
        if not parsed:
            return create_response(404, {'errcode': Matrix.ERR_NOT_FOUND})
        prefix, tgchat, _ = parsed
        room_alias = '{}_{}'.format(prefix, tgchat)

        # Look up the chat in the database
        link = db.session.query(db.ChatLink).filter_by(tg_room=tgchat).first()
        if link:
            await matrix_post('client', 'createRoom', None,
                              {'room_alias_name': room_alias})
            return create_response(200, {})
        else:
            return create_response(404, {'errcode': Matrix.ERR_NOT_FOUND})

    event_handlers = {
        'm.room.aliases': Matrix.handler_room_aliases,
        'm.room.message': None
    }

    async def req_transaction(self, request):
        """Handle a transaction sent by the homeserver."""
        body = await request.json()
        for event in body['events']:
            # Retrieve the handler for this event type
            try:
                handler = self.event_handlers[event['type']]
            except KeyError:
                print('Unknown event type', event['type'])

            await handler(event)

    async def handler_room_aliases(self, event):
        """Handle a m.room.aliases event."""
        aliases = event['content']['aliases']
        links = db.session.query(db.ChatLink)\
                  .filter_by(matrix_room=event['room_id']).all()

        for link in links:
            db.session.delete(link)

        for alias in aliases:
            # Check if the alias is for us
            parsed = self.parse_alias(alias)
            if not parsed:
                continue
            _, tg_chat, _ = parsed

            # Create a database entry for the alias
            link = db.ChatLink(event['room_id'], tg_chat, True)
            db.session.add(link)

        db.session.commit()
