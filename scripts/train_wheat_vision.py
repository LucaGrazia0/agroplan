"""Research baseline: local MobileNetV3 features, grouped holdout, five wheat labels.

Run in a separate research environment with torch, torchvision, onnx and Pillow.
Neither the training corpus nor PyTorch is included in the phone packages.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import time

import numpy as np
import torch
from PIL import Image
from torch import nn
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights


class WheatModel(nn.Module):
    def __init__(self, features, mean, scale, head):
        super().__init__()
        self.features=features
        self.register_buffer('mean',mean)
        self.register_buffer('scale',scale)
        self.head=head

    def forward(self, pixels):
        vector=self.features(pixels).mean(dim=(2,3))
        return self.head((vector-self.mean)/self.scale), vector


def evaluate(logits, labels, classes):
    pred=logits.argmax(1)
    confusion=torch.zeros((classes,classes),dtype=torch.int64)
    for true,guess in zip(labels,pred): confusion[true,guess]+=1
    recall=confusion.diag()/confusion.sum(1).clamp(min=1)
    return {'accuracy':float((pred==labels).float().mean()),
            'balanced_accuracy':float(recall.mean()), 'recall_by_class':recall.tolist(),
            'confusion_matrix':confusion.tolist(), 'count':len(labels)}


def train(dataset, output):
    random.seed(20261125);np.random.seed(20261125);torch.manual_seed(20261125)
    torch.set_num_threads(4)
    manifest=json.loads((dataset/'manifest.json').read_text())
    rows=[r for r in manifest['rows'] if r['split']!='quarantine']
    classes=sorted({r['label'] for r in rows});class_index={label:i for i,label in enumerate(classes)}
    weights=MobileNet_V3_Small_Weights.IMAGENET1K_V1
    backbone=mobilenet_v3_small(weights=weights).features.eval()
    transform=weights.transforms()
    vectors=[]
    start=time.time()
    with torch.inference_mode():
        for begin in range(0,len(rows),24):
            batch=[]
            for row in rows[begin:begin+24]:
                with Image.open(dataset/row['path']) as image: batch.append(transform(image.convert('RGB')))
            vectors.append(backbone(torch.stack(batch)).mean(dim=(2,3)))
            if begin%120==0: print(f'Caratteristiche estratte: {min(begin+24,len(rows))}/{len(rows)}',flush=True)
    features=torch.cat(vectors)
    labels=torch.tensor([class_index[r['label']] for r in rows])
    indices={split:torch.tensor([i for i,r in enumerate(rows) if r['split']==split]) for split in ['train','validation','test']}
    assert all(len(i)>0 for i in indices.values())
    assert not (set(rows[i]['group_id'] for i in indices['train']) & set(rows[i]['group_id'] for i in indices['test']))
    mean=features[indices['train']].mean(0)
    scale=features[indices['train']].std(0).clamp(min=.01)
    x=(features-mean)/scale
    head=nn.Linear(x.shape[1],len(classes))
    optimizer=torch.optim.AdamW(head.parameters(),lr=.005,weight_decay=.03)
    frequencies=torch.bincount(labels[indices['train']],minlength=len(classes))
    loss_fn=nn.CrossEntropyLoss(weight=(1/frequencies.float())/(1/frequencies.float()).mean())
    best=-1;best_head=None;selected_epoch=None
    for epoch in range(150):
        head.train();optimizer.zero_grad()
        loss=loss_fn(head(x[indices['train']]),labels[indices['train']]);loss.backward();optimizer.step()
        head.eval()
        with torch.no_grad(): metric=evaluate(head(x[indices['validation']]),labels[indices['validation']],len(classes))
        if metric['balanced_accuracy']>best:
            best=metric['balanced_accuracy'];best_head=copy.deepcopy(head.state_dict());selected_epoch=epoch+1
    head.load_state_dict(best_head);head.eval()
    reports={}
    with torch.no_grad():
        for split in indices:
            logits=head(x[indices[split]])
            report=evaluate(logits,labels[indices[split]],len(classes))
            probabilities=logits.softmax(1);values,top=probabilities.topk(2,dim=1)
            accepted=(values[:,0]>=.85)&((values[:,0]-values[:,1])>=.25)
            report['selective_policy']={'minimum_model_score':.85,'minimum_margin':.25,
                'accepted_count':int(accepted.sum()),'coverage':float(accepted.float().mean()),
                'accuracy_on_accepted':float((top[accepted,0]==labels[indices[split]][accepted]).float().mean()) if accepted.any() else None}
            reports[split]=report
    output.mkdir(parents=True,exist_ok=True)
    model=WheatModel(backbone,mean,scale,head).eval()
    sample=torch.zeros((1,3,224,224))
    torch.onnx.export(model,sample,str(output/'wheat.onnx'),input_names=['pixels'],output_names=['logits','embedding'],
                      opset_version=17,dynamo=False)
    # Nearest references are exclusively TRAIN images. Never use holdout images
    # to populate the reference bank or to select epochs/thresholds.
    bank=[]
    for label in classes:
        examples=[i for i,r in enumerate(rows) if r['label']==label and r['split']=='train'][:12]
        for i in examples:
            row=rows[i];target=output/'references'/f"{row['id']}.jpg";target.parent.mkdir(exist_ok=True)
            with Image.open(dataset/row['path']) as image:
                image.thumbnail((256,256));image.convert('RGB').save(target,'JPEG',quality=80)
            bank.append(dict(id=row['id'],label=label,path=str(target.relative_to(output)),embedding=features[i].tolist(),source=manifest['doi']))
    metadata=dict(version='wheat-vision-research-2026.11.25',classes=classes,
                  backbone='torchvision MobileNetV3 Small IMAGENET1K_V1, frozen',
                  source=manifest['source'],license=manifest['license'],creators=manifest['creators'],
                  dataset_manifest_sha256=hashlib.sha256((dataset/'manifest.json').read_bytes()).hexdigest(),
                  model_sha256=hashlib.sha256((output/'wheat.onnx').read_bytes()).hexdigest(),
                  preprocessing={'resize_short_edge':256,'center_crop':224,'rescale':255,
                                 'mean':[.485,.456,.406],'std':[.229,.224,.225]},
                  selected_epoch=selected_epoch,selection_metric='validation balanced accuracy',reports=reports,
                  experimental=True,validated_on_italian_fields=False,
                  limitations=manifest['limitations']+[
                      'Reported results are an internal grouped holdout, not independent clinical/field validation.',
                      'Scores are uncalibrated model outputs, not disease probabilities.',
                      'Score and margin thresholds are application rejection gates; unknown diseases can still obtain a high score.',
                      'Only wheat leaves and these five labels are in scope; no prediction for other crops or organs.'],
                  training_seconds=round(time.time()-start,2))
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2))
    (output/'reference-bank.json').write_text(json.dumps(bank,separators=(',',':')))
    (output/'ATTRIBUTION.txt').write_text((dataset/'ATTRIBUTION.txt').read_text()+'\nFeature extractor: torchvision MobileNetV3 Small, ImageNet1K V1; https://pytorch.org/vision/; torchvision BSD-3-Clause. Research baseline, not independently validated.\n')
    print(json.dumps({'classes':classes,'reports':reports,'selected_epoch':selected_epoch,'seconds':metadata['training_seconds']},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();train(args.dataset,args.output)
