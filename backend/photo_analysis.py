"""Photo checks and optional LOCAL model inference. No image leaves AgroPlan.

The corpus/model are research assets. They never grant a diagnostic certainty.
"""
import base64
import binascii
from io import BytesIO
import json
import hashlib
from pathlib import Path
import threading
import warnings
import zipfile
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from starlette.concurrency import run_in_threadpool
from PIL import Image, ImageOps, ImageStat, ImageFilter, UnidentifiedImageError
from auth import CurrentUser, require_parcel

# Opt out BEFORE the native runtime is imported/initialised. The process-wide
# switch also disables its uploader and persistent device identifier.
os.environ['ORT_DISABLE_TELEMETRY']='1'

router=APIRouter(prefix='/analysis-center',tags=['Centro analisi'])
LIMIT=6_000_000
MODEL=Path(__file__).with_name('vision_bundle')
_inference_lock=threading.Lock()
_runtime=None

LABELS={'brown_rust':'Ruggine bruna','yellow_rust':'Ruggine gialla','septoria':'Septoria',
        'powdery_mildew':'Oidio','healthy':'Aspetto simile ai riferimenti etichettati sani'}


class PhotoRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    parcel_id:str=Field(min_length=1,max_length=128)
    image_base64:str=Field(min_length=10,max_length=5_500_000)
    wheat_leaf_confirmed:bool=False


def clean_photo(encoded):
    try:
        raw=base64.b64decode(encoded,validate=True)
        if len(raw)>4_000_000: raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as original:
                if original.format not in {'JPEG','PNG','WEBP'} or original.width*original.height>16_000_000:
                    raise ValueError()
                original.load()
                image=ImageOps.exif_transpose(original).convert('RGB')
        if min(image.size)<128: raise ValueError()
    except (binascii.Error, ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise HTTPException(422,'Usa una foto JPEG, PNG o WebP leggibile, almeno 128 pixel per lato e di dimensione contenuta.')
    image.thumbnail((1280,1280))
    gray=image.convert('L').resize((256,256))
    brightness=ImageStat.Stat(gray).mean[0]
    contrast=ImageStat.Stat(gray).stddev[0]
    edges=ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES).crop((2,2,254,254))).mean[0]
    issues=[]
    if brightness<35:issues.append('Foto molto scura: ripeti con luce diffusa.')
    if brightness>225:issues.append('Foto molto chiara: evita riflessi e zone bruciate.')
    if contrast<12:issues.append('Poco contrasto: avvicinati alla foglia e separala dallo sfondo.')
    if edges<3:issues.append('Pochi dettagli rilevati: controlla la messa a fuoco.')
    preview=image.copy();preview.thumbnail((256,256));buffer=BytesIO();preview.save(buffer,'JPEG',quality=80)
    return image,dict(width=image.width,height=image.height,issues=issues,
                      sha256=hashlib.sha256(image.tobytes()).hexdigest(),
                      preview_base64=base64.b64encode(buffer.getvalue()).decode(),
                      note='Controlli tecnici orientativi: non verificano diagnosi, specie o presenza effettiva della foglia.')


def model_info():
    try:
        metadata=json.loads((MODEL/'metadata.json').read_text())
    except (OSError,ValueError):return {'available':False,'message':'Il modello interno è ancora in preparazione; puoi usare foto e segni confermati nel percorso guidato.'}
    return {'available':(MODEL/'bundle.zip').is_file(),'version':metadata['version'],
            'classes':metadata['classes'],'experimental':True,'validated_on_italian_fields':False,
            'source':metadata['source'],'reports':metadata['reports'],
            'message':'Prototipo locale per foglie di frumento; le proposte richiedono verifica in campo.'}


def predict(image, quality):
    global _runtime
    if quality['issues']:
        return {'status':'retake','candidates':[],'message':'Migliora la foto prima del confronto.'}
    if not model_info()['available']:
        return {'status':'not_ready','candidates':[],'message':model_info()['message']}
    if not _inference_lock.acquire(blocking=False):
        raise HTTPException(429,'Un altro confronto foto è in corso: riprova tra poco.')
    try:
        import numpy as np
        import onnxruntime as ort
        ort.disable_telemetry_events()
        if _runtime is None:
            metadata=json.loads((MODEL/'metadata.json').read_text())
            bundle=(MODEL/'bundle.zip').read_bytes()
            if hashlib.sha256(bundle).hexdigest()!=metadata['bundle_sha256']:
                raise ValueError('bundle integrity')
            with zipfile.ZipFile(BytesIO(bundle)) as archive:
                model=archive.read('wheat.onnx');bank=json.loads(archive.read('reference-bank.json'))
            if hashlib.sha256(model).hexdigest()!=metadata['model_sha256']:
                raise ValueError('model integrity')
            options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
            session=ort.InferenceSession(model,sess_options=options,providers=['CPUExecutionProvider'])
            _runtime=(session,metadata,bank)
        session,metadata,bank=_runtime
        scale=256/min(image.size)
        resized=image.resize((int(image.width*scale),int(image.height*scale)),Image.Resampling.BILINEAR)
        left=round((resized.width-224)/2);top=round((resized.height-224)/2)
        pixels=np.asarray(resized.crop((left,top,left+224,top+224)),dtype=np.float32)/255
        pixels=(pixels-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)
        logits,embedding=session.run(None,{'pixels':pixels.transpose(2,0,1)[None]})
        logits=logits[0];prob=np.exp(logits-logits.max());prob/=prob.sum()
        order=np.argsort(prob)[::-1]
        accepted=bool(prob[order[0]]>=.85 and prob[order[0]]-prob[order[1]]>=.25)
        candidates=[]
        for index in order[:3]:
            label=metadata['classes'][int(index)]
            vectors=np.asarray([r['embedding'] for r in bank if r['label']==label],dtype=np.float32)
            refs=[r for r in bank if r['label']==label]
            similarities=(vectors@embedding[0])/(np.linalg.norm(vectors,axis=1)*np.linalg.norm(embedding[0])+1e-8)
            nearest=refs[int(similarities.argmax())]
            candidates.append({'label':label,'title':LABELS[label],'model_score':round(float(prob[index]),4),
                               'reference_id':nearest['id'],'reference_source':metadata['source']})
        return {'status':'experimental_match' if accepted else 'uncertain','candidates':candidates,
                'model_version':metadata['version'],'experimental':True,
                'message':'Somiglianza da verificare con segni e dati del campo.' if accepted else 'Confronto incerto: non restringo le cause da questa foto.',
                'limitations':['I punteggi sono uscite del modello, non probabilità diagnostiche.',
                               'Solo cinque etichette e foglie di frumento: altre malattie possono somigliare a queste.',
                               'Non validato su aziende italiane; un riferimento sano non certifica salute.',
                               'Le foto non vengono usate automaticamente per addestrare il modello.']}
    except HTTPException:raise
    except (ImportError,OSError,ValueError,RuntimeError):
        raise HTTPException(503,'Confronto foto interno temporaneamente non disponibile; usa le verifiche guidate.')
    finally:_inference_lock.release()


@router.get('/schema')
def get_schema(user:CurrentUser):
    from diagnostic_schema import schema
    return dict(schema(),vision=model_info())


@router.post('/photo')
async def inspect_photo(request:Request,user:CurrentUser):
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>LIMIT:raise HTTPException(413,'Foto troppo grande: scegli un dettaglio più piccolo.')
    try:item=PhotoRequest.model_validate_json(body)
    except ValidationError:raise HTTPException(422,'Foto o richiesta non valida.')
    require_parcel(item.parcel_id,user)
    from agronomy_engine import crop_context
    crop=crop_context(item.parcel_id,None)
    image,quality=await run_in_threadpool(clean_photo,item.image_base64)
    if not item.wheat_leaf_confirmed or not crop or crop.get('crop') not in {'frumento_tenero','frumento_duro'}:
        result={'status':'unsupported','candidates':[],'message':'Conferma una foglia di frumento e registra il ciclo colturale. Altre colture e organi non sono supportati da questo primo modello.'}
    else:result=await run_in_threadpool(predict,image,quality)
    return {'quality':quality,'recognition':result,'privacy':'Elaborazione nel server AgroPlan, senza API AI esterne. La foto completa non viene conservata.'}


@router.get('/references/{reference_id}')
def reference(reference_id:str,user:CurrentUser):
    # Public training images, protected with the same session as analysis.
    from fastapi.responses import Response
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,70}',reference_id):raise HTTPException(404)
    try:
        with zipfile.ZipFile(MODEL/'bundle.zip') as archive:image=archive.read(f'references/{reference_id}.jpg')
    except (OSError,KeyError,zipfile.BadZipFile):raise HTTPException(404)
    return Response(image,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=86400'})
