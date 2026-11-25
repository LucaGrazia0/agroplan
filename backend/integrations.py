"""Authenticated live checks: connectivity is measured, never assumed."""
import asyncio
from datetime import datetime, timezone
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from auth import CurrentUser


class CheckRequest(BaseModel):
    latitude: float=Field(default=44.65,ge=35,le=48)
    longitude: float=Field(default=11.18,ge=6,le=19)


def register_integration_routes(app,checkers):
    router=APIRouter(prefix='/integrations',tags=['Collegamenti'])
    cache={}
    lock=asyncio.Lock()

    @router.post('/status')
    async def check_integrations(req:CheckRequest,user:CurrentUser):
        key=(round(req.latitude,4),round(req.longitude,4))
        async with lock:
            cached=cache.get(key)
            if cached and time.monotonic()-cached[0]<60:
                return cached[1]
            async def check(name,checker):
                try:
                    result=await asyncio.wait_for(checker(req),timeout=50)
                    return {'id':name,**result}
                except Exception as exc:
                    detail=getattr(exc,'detail','')
                    message=('Configura le credenziali Copernicus sul server.'
                             if 'credentials missing' in str(detail)
                             else 'Collegamento non riuscito. Riprova o verifica il servizio sul server.')
                    return {'id':name,'status':'unavailable','message':message}
            services=await asyncio.gather(*(check(name,checker) for name,checker in checkers.items()))
            result={'checked_at':datetime.now(timezone.utc).isoformat(),'services':services,
                    'all_available':all(s['status']=='ok' for s in services)}
            if len(cache)>=32:
                cache.pop(next(iter(cache)))
            cache[key]=(time.monotonic(),result)
            return result
    app.include_router(router)
