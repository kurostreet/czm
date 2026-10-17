"""Versioned account settings; game commands and credentials are not accepted."""
import json
import math
import re
from pathlib import Path
from . import accounts
from .db import now

SCHEMA=json.loads(Path(__file__).with_name('settings_schema.json').read_text())
KEYS=set(SCHEMA['cvars'])
COMMANDS=set(SCHEMA['commands'])

def valid_value(key,value):
    if not isinstance(value,str) or len(value)>128 or re.search(r'[\x00-\x1f";\\]',value):
        return False
    if key=='cl_crosshair_color':
        return bool(re.fullmatch(r'\d{1,3} \d{1,3} \d{1,3}',value)) and all(int(x)<=255 for x in value.split())
    if key=='cl_crosshair_size': return value in ('auto','small','medium','large','0','1','2','3')
    if key=='czm_lang': return value in ('','ru','en')
    if key=='cl_logofile': return bool(re.fullmatch(r'[A-Za-z0-9_-]{1,32}',value))  # the chosen spray
    try: return math.isfinite(float(value)) and abs(float(value))<=1000000
    except ValueError: return False

def validate(payload):
    if not isinstance(payload,dict) or payload.get('schema')!=1 or set(payload)-{'schema','cvars','layouts'}:
        raise accounts.AuthError('settings')
    if len(json.dumps(payload).encode())>131072: raise accounts.AuthError('settings')
    cvars=payload.get('cvars');layouts=payload.get('layouts')
    if not isinstance(cvars,dict) or not cvars or set(cvars)-KEYS or not isinstance(layouts,dict) or set(layouts)-{'1','2','3'}:
        raise accounts.AuthError('settings')
    if any(not valid_value(k,v) for k,v in cvars.items()): raise accounts.AuthError('settings')
    for buttons in layouts.values():
        if not isinstance(buttons,list) or not 1<=len(buttons)<=80: raise accounts.AuthError('settings')
        seen=set()
        for b in buttons:
            if not isinstance(b,list) or len(b)!=12 or not all(isinstance(x,str) for x in b[:3]): raise accounts.AuthError('settings')
            name,texture,command=b[:3]
            if not re.fullmatch(r'[A-Za-z0-9_+#.-]{1,64}',name) or name in seen: raise accounts.AuthError('settings')
            seen.add(name)
            if len(texture)>128 or '..' in texture or re.search(r'[\x00-\x1f";\\]',texture) or texture.startswith('/'):
                raise accounts.AuthError('settings')
            if command not in COMMANDS and not re.fullmatch(r'say(?:_team)? [^";\\\x00-\x1f]{1,96}',command):
                raise accounts.AuthError('settings')
            if any(type(x) not in (int,float) or not math.isfinite(x) for x in b[3:]):raise accounts.AuthError('settings')
            x1,y1,x2,y2=b[3:7]
            if not (0<=x1<x2<=1 and 0<=y1<y2<=1) or any(not 0<=x<=255 or int(x)!=x for x in b[7:11]) or int(b[11])!=b[11] or not 0<=b[11]<=65535:
                raise accounts.AuthError('settings')
    return payload

def load(conn,token):
    player=accounts.authenticated(conn,token)
    row=conn.execute('SELECT revision,payload,updated FROM player_settings WHERE player=?',(player['id'],)).fetchone()
    return {'revision':row['revision'],'payload':json.loads(row['payload']),'updated':row['updated']} if row else {'revision':0,'payload':None,'updated':0}

def save(conn,token,revision,payload):
    player=accounts.authenticated(conn,token)
    accounts.rate(conn,'settings',str(player['id']),90,600)
    validate(payload)
    current=conn.execute('SELECT revision FROM player_settings WHERE player=?',(player['id'],)).fetchone()
    current=current['revision'] if current else 0
    if revision!=current:raise accounts.AuthError('settings_conflict',409)
    encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'));t=now()
    conn.execute('INSERT INTO player_settings VALUES(?,?,?,?) ON CONFLICT(player) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,updated=excluded.updated',(player['id'],current+1,encoded,t))
    conn.execute('INSERT INTO settings_history VALUES(?,?,?,?)',(player['id'],current+1,encoded,t))
    conn.execute('DELETE FROM settings_history WHERE player=? AND revision<?',(player['id'],current-1))
    return {'revision':current+1,'updated':t}
