"""Live integration smoke test. No credentials or tokens are written to output."""
import argparse
import asyncio
from datetime import date,timedelta,datetime,timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import main
from integration_checks import provider_checks
from integrations import CheckRequest


async def check(full):
    request=CheckRequest()
    async def one(name,fn):
        try:
            result=await asyncio.wait_for(fn(request),timeout=60)
            return {'id':name,**result}
        except Exception as exc:
            return {'id':name,'status':'unavailable','error':type(exc).__name__}
    services=await asyncio.gather(*(one(name,fn) for name,fn in provider_checks(main).items()))
    if full:
        geometry={'type':'Polygon','coordinates':[[[11.18,44.65],[11.181,44.65],[11.181,44.651],[11.18,44.651],[11.18,44.65]]]}
        try:
            catalog=await main.scenes(main.ScenesRequest(geometry=geometry,start_date=date.today()-timedelta(days=90),end_date=date.today(),limit=100))
            usable=[s for s in catalog['scenes'] if isinstance(s.get('cloud_cover'),(int,float)) and s['cloud_cover']<=30]
            if not usable:
                raise ValueError('Nessuna acquisizione utilizzabile nel periodo')
            scene=min(usable,key=lambda s:s['cloud_cover'])
            day=date.fromisoformat(scene['datetime'][:10])
            for index in ['ndvi','dvi']:
                req=main.ParcelTimeSeriesRequest(geometry=geometry,dates=[day],index=index)
                stats=await main.parcel_stats_for_date(req,day)
                image=await main.overlay(main.OverlayRequest(geometry=geometry,date=day,index=index,width=128,height=128))
                services.append({'id':'sentinel_'+index,'status':'ok' if stats['status']=='ok' and image.body else 'unavailable',
                                 'acquisition':day.isoformat(),'statistics':stats['status'],'image_bytes':len(image.body)})
        except Exception as exc:
            services.append({'id':'sentinel_data','status':'unavailable','error':type(exc).__name__})
    return {'checked_at':datetime.now(timezone.utc).isoformat(),'services':services,
            'all_available':all(s['status']=='ok' for s in services)}


def cli():
    parser=argparse.ArgumentParser()
    parser.add_argument('--full',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=asyncio.run(check(args.full))
    payload=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    print(payload)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(payload)
    return 0 if result['all_available'] else 1


if __name__=='__main__':
    raise SystemExit(cli())
