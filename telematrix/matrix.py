from aiohttp import web
import urllib.parse as urlparse
import json


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

    def __init__(self, loop, config):
        self.app = web.Application(loop=loop)
        self.app.router.add_route('GET', '/rooms/{room_alias}', self.req_room)
        self.app.router.add_route('PUT', '/transactions/{transaction}',
                                  self.req_transaction)

        self.config = config

    def run(self, port):
        web.run_app(self.app, port=port)

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
            if args['access_token'][0] != config.hs_token:
                return create_response(403, {'errcode': Matrix.ERR_FORBIDDEN})
        except KeyError:
            return create_response(401, {'errcode': Matrix.ERR_UNAUTHORIZED})

        # Retrieve the Telegram group ID from the alias
        match = re.match(r'^#.*_([\d-]*):(.*)$')
        if not match:
            return create_response(404, {'errcode': Matrix.ERR_NOT_FOUND})

        try:
            chat = match.group(1)
            room_alias = match.group(2)
        except IndexError:
            return create_response(404, {'errcode': Matrix.ERR_NOT_FOUND})

        # Look up the chat in the database
        link = db.session.query(db.ChatLink).filter_by(tg_room=chat).first()
        if link:
            await matrix_post('client', 'createRoom', None, {'room_alias_name'})
            return create_response(200, {})
        else:
            return create_response(404, {'errccode': Matrix.ERR_NOT_FOUND})

