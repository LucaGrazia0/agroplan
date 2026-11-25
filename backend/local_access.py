"""Passwordless desktop mode, restricted to the local launcher and origin."""
import ipaddress
import os
from urllib.parse import urlsplit

from fastapi import Request
from storage import connect


def enabled():
    return os.getenv('AGROPLAN_LOCAL_MODE') == '1' and os.getenv('RENDER') != 'true'


def request_allowed(request: Request):
    if not enabled() or request.client is None:
        return False
    try:
        if not ipaddress.ip_address(request.client.host).is_loopback:
            return False
    except ValueError:
        return False
    if request.url.hostname not in {'localhost', '127.0.0.1', '::1'}:
        return False
    if request.headers.get('sec-fetch-site') == 'cross-site':
        return False
    origin = request.headers.get('origin')
    if origin:
        source = urlsplit(origin)
        if (source.scheme, source.netloc) != (request.url.scheme, request.url.netloc):
            return False
    return True


def prepare_local_farm():
    """Keep an existing single farm; preserve existing accounts for later use."""
    configured = os.getenv('AGROPLAN_LOCAL_FARM_ID')
    with connect() as db:
        farms = {r[0] for r in db.execute("SELECT farm_id FROM auth_users UNION SELECT farm_id FROM agr_parcels WHERE farm_id!='__legacy__'")}
        farm = configured or (next(iter(farms)) if len(farms) == 1 else 'azienda-locale')
        db.execute("UPDATE agr_parcels SET farm_id=?,revision=0 WHERE farm_id='__legacy__'", (farm,))
    os.environ['AGROPLAN_LOCAL_FARM_ID'] = farm
    return farm
