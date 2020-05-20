import re
import json
import requests
from pymongo import MongoClient
from bson.codec_options import CodecOptions
from bson.objectid import ObjectId
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pprint import pformat

with open('.mongourl') as fh:
    MONGO_URL = fh.read().strip()

# from https://github.com/BTDev/Berrymotes/blob/master/js/berrymotes.core.js
EMOTE_REGEX = r'\[([^\]]*)\]\(\/([\w:!#\/]+)([-\w!]*)([^)]*)\)'

def handle_usercolors(environ, start_response):
    response = requests.get('https://btc.berrytube.tv/wut/wutColors/usercolors.js')
    response.raise_for_status()

    data = json.loads(re.sub(r'^[^=]+=', '', response.text))
    
    start_response('200 OK', [('Content-Type', 'text/css')])
    return '\n'.join(
        f'tr[data-id="{nick}"] {{ --usercolor: {attrs["color"]}; }}'
        for nick, attrs in data.items()
        if attrs.get('color')
    )

SUFFIX = [
    { '$sort': OrderedDict([('count', -1), ('latest', -1)]) },
    { '$limit': 10 },
]

ACTIONS = {
    'videos': {
        'collection': 'forceVideoChange',
        'pipeline': [
            { '$group': {
                '_id': '$video.videotitle',
                'count': { '$sum': 1 },
                'latest': { '$max': '$_time' },
                'videoid': { '$first': '$video.videoid' },
                'videotype': { '$first': '$video.videotype' },
            } },
        ] + SUFFIX
    },
    'drinks': {
        'collection': 'chatMsg',
        'pipeline': [
            { '$match': { 'msg.emote': 'drink' } },
            { '$group': {
                '_id': { '$toLower': '$msg.msg' },
                'count': { '$sum': 1 },
                'latest': { '$max': '$_time' },
            } },
        ] + SUFFIX
    },
    'emotes': {
        'collection': 'chatMsg',
        'pipeline': [
            { '$project': {
                '_id': False,
                '_time': True,
                #'nick': '$msg.nick',
                'emotes': { '$regexFindAll': {
                    'input': '$msg.msg',
                    'regex': EMOTE_REGEX,
                    'options': 'i',
                } },
            } },
            { '$unwind': '$emotes' },
            { '$group': {
                '_id': { '$arrayElemAt': ['$emotes.captures', 1] },
                'count': { '$sum': 1 },
                'latest': { '$max': '$_time' },
                #'nicks': { '$push': '$nick' },
            } },
        #] + SUFFIX + [
            # emote most used by user:
            # { '$unwind': '$nicks' },
            # { '$group': {
            #     '_id': { 'emote': '$_id', 'nick': '$nicks' },
            #     'count': { '$first': '$count' },
            #     'latest': { '$first': '$count' },
            #     'userCount': { '$sum': 1 },
            # } },
            # { '$sort': OrderedDict([('count', -1), ('userCount', -1)]) },
            # { '$group': {
            #     '_id': '$_id.emote',
            #     'count': { '$first': '$count' },
            #     'latest': { '$first': '$latest' },
            #     'user': { '$first': '$_id.nick' },
            #     'userCount': { '$first': '$userCount' },
            # } },
            # emote alias resolving:
            # { '$sort': { 'count': -1 } },
            # { '$limit': 100 },
            # { '$lookup': {
            #     'from': 'berrymotes',
            #     'let': { 'name': '$_id' },
            #     'pipeline': [
            #         { '$match': { '$expr': { '$in': ['$$name', '$names'] } } },
            #         { '$limit': 1 },
            #     ],
            #     'as': 'berrymote'
            # } },
            # { '$set': {
            #     'berrymote': { '$arrayElemAt': ['$berrymote', 0] },
            # } },
            # { '$group': {
            #     '_id': { '$arrayElemAt': ['$berrymote.names', 0] },
            #     'count': { '$sum': '$count' },
            #     'latest': { '$max': '$latest' },
            # } },
        ] + SUFFIX
    },
    'chatters': {
        'collection': 'chatMsg',
        'pipeline': [
            { '$match': { 'msg.emote': False } },
            { '$group': {
                '_id': '$msg.nick',
                'count': { '$sum': 1 },
                'latest': { '$max': '$_time' },
                'characters': { '$sum': { '$strLenBytes': '$msg.msg' } },
                'emotes': { '$sum': { '$size': { '$regexFindAll': {
                    'input': '$msg.msg',
                    'regex': EMOTE_REGEX,
                    'options': 'i',
                } } } },
                # 'fav': { '$push': { '$regexFindAll': {
                #     'input': '$msg.msg',
                #     'regex': EMOTE_REGEX,
                #     'options': 'i',
                # } } },
            } },
        #] + SUFFIX + [
            # user's favorite emote:
            # { '$unwind': '$fav' },
            # { '$unwind': '$fav' },
            # { '$group': {
            #     '_id': {
            #         'nick': '$_id',
            #         'fav': { '$arrayElemAt': ['$fav.captures', 1] },
            #     },
            #     'count': { '$first': '$count' },
            #     'latest': { '$first': '$latest' },
            #     'characters': { '$first': '$characters' },
            #     'emotes': { '$first': '$emotes' },
            #     'favCount': { '$sum': 1 },
            # } },
            # { '$sort': OrderedDict([('_id.nick', 1), ('favCount', -1)]) },
            # { '$group': {
            #     '_id': '$_id.nick',
            #     'count': { '$first': '$count' },
            #     'latest': { '$first': '$latest' },
            #     'characters': { '$first': '$characters' },
            #     'emotes': { '$first': '$emotes' },
            #     'favCount': { '$first': '$favCount' },
            #     'fav': { '$first': '$_id.fav' },
            # } },
        ] + SUFFIX
    },
    'connected': {
        'collection': 'numConnected',
        'postprocess': lambda docs: [[doc['_id'], doc['count']] for doc in docs],
        'pipeline': [
            { '$group': {
                '_id': { '$dateToString': {
                    'date': {
                        '$dateFromParts': {
                            'year': { '$year': '$_time' },
                            'month': { '$month': '$_time' },
                            'day': { '$dayOfMonth': '$_time' },
                            'hour': { '$hour': '$_time' },
                            'minute': { '$subtract': [
                                { '$minute': '$_time' },
                                { '$mod': [{'$minute': '$_time'}, 5] }
                            ] },
                        }
                    },
                    'format': '%Y-%m-%dT%H:%MZ',
                } },
                'count': { '$max': '$num' },
            } },
            { '$sort': { '_id': 1 } },
        ] # no SUFFIX
    },
    'usercolors': {
        'handler': handle_usercolors,
    },
}

def json_serializer(val):
    if isinstance(val, datetime):
        return val.isoformat(timespec='seconds')
    if isinstance(val, ObjectId):
        return str(val)
    raise TypeError(f"can't JSON serialize a {type(val)}")

def application(environ, start_response):
    action = ACTIONS[environ['query']['action'][0]]

    handler = action.get('handler')
    if handler:
        return handler(environ, start_response)

    prefix = [
        { '$match': { '_time': { '$gte': datetime.now() - timedelta(days=7) } } },
    ]

    results = action.get('postprocess', list)(
        MongoClient(MONGO_URL)
            .btlogs
            .get_collection(action['collection'], codec_options=CodecOptions(tz_aware=True))
            .aggregate(prefix + action['pipeline'])
    )

    start_response('200 OK', [('Content-Type', 'application/json')])
    return json.dumps(
        results,
        default=json_serializer,
        ensure_ascii=False,
        check_circular=False,
        separators=(',', ':'),
    )
