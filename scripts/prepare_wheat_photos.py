"""Prepare the JIC labelled wheat collection without leaking duplicates across splits.

Download the source archive from https://doi.org/10.5281/zenodo.7573133 first.
Outputs are research data, never app assets. Requires Pillow (already in backend).
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import zipfile

from PIL import Image, ImageOps, ImageDraw

CLASSES = {'BrownRust': 'brown_rust', 'YellowRust': 'yellow_rust',
           'Septoria': 'septoria', 'Mildew': 'powdery_mildew', 'Healthy': 'healthy'}
LABELS = {'brown_rust': 'Ruggine bruna', 'yellow_rust': 'Ruggine gialla',
          'septoria': 'Septoria', 'powdery_mildew': 'Oidio', 'healthy': 'Foglia sana (etichetta originale)'}


def dhash(image):
    pixels = list(image.convert('L').resize((9, 8)).getdata())
    return sum(int(pixels[y * 9 + x] > pixels[y * 9 + x + 1]) << (y * 8 + x)
               for y in range(8) for x in range(8))


def prepare(source, destination):
    checksum = hashlib.md5()
    with source.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): checksum.update(block)
    if checksum.hexdigest() != '1f8a7c660c2da137b957fb4edee3dd7d':
        raise ValueError('Source checksum mismatch')
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    with zipfile.ZipFile(source) as archive:
        assert archive.testzip() is None
        for member in archive.infolist():
            if member.is_dir(): continue
            name = Path(member.filename).name
            label = next((v for k, v in CLASSES.items() if name.startswith(k)), None)
            if not label or member.file_size > 30_000_000:
                raise ValueError('Unexpected image or size in source')
            with archive.open(member) as stream, Image.open(stream) as original:
                image = ImageOps.exif_transpose(original).convert('RGB')
                original_size = list(image.size)
                image.thumbnail((640, 640))
                pixel_sha = hashlib.sha256(image.tobytes() + str(image.size).encode()).hexdigest()
                folder = destination / 'images' / label
                folder.mkdir(parents=True, exist_ok=True)
                output = folder / (Path(name).stem + '.jpg')
                image.save(output, 'JPEG', quality=88, optimize=True)
                rows.append(dict(id=Path(name).stem, label=label, original_name=name,
                                 original_size=original_size, path=str(output.relative_to(destination)),
                                 pixel_sha256=pixel_sha, dhash=f'{dhash(image):016x}',
                                 sha256=hashlib.sha256(output.read_bytes()).hexdigest()))
    # Conservative, reproducible near-duplicate groups. Labels never change.
    parent = list(range(len(rows)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i, row in enumerate(rows):
        for j in range(i):
            if (row['pixel_sha256'] == rows[j]['pixel_sha256']
                    or (int(row['dhash'], 16) ^ int(rows[j]['dhash'], 16)).bit_count() <= 4):
                parent[root(i)] = root(j)
    groups = {}
    for i, row in enumerate(rows): groups.setdefault(root(i), []).append(row)
    buckets = {label: [] for label in CLASSES.values()}
    quarantined = []
    for group in groups.values():
        identifier = min(r['id'] for r in group)
        for row in group: row['group_id'] = identifier
        if len({r['label'] for r in group}) > 1:
            for row in group: row['split'] = 'quarantine'
            quarantined.extend(group)
        else: buckets[group[0]['label']].append(group)
    rng = random.Random(20261125)
    for label, grouped in buckets.items():
        rng.shuffle(grouped)
        targets = {'train': .7, 'validation': .15, 'test': .15}
        counts = Counter()
        total = sum(len(g) for g in grouped)
        for group in sorted(grouped, key=len, reverse=True):
            split = min(targets, key=lambda k: counts[k] / (total * targets[k]))
            for row in group: row['split'] = split
            counts[split] += len(group)
    manifest = dict(dataset='JIC wheat disease images, small dataset (2023)',
                    doi='10.5281/zenodo.7573133', source='https://zenodo.org/records/7573133',
                    creators=['Megan C. Long', 'Matthew Hartley', 'Richard J. Morris', 'James K. M. Brown'],
                    license='CC BY 4.0', license_url='https://creativecommons.org/licenses/by/4.0/',
                    changes='EXIF orientation applied; converted to RGB JPEG, max edge 640 px; metadata removed; labels unchanged.',
                    source_md5=checksum.hexdigest(), seed=20261125, rows=rows,
                    counts=dict(Counter(r['label'] for r in rows)),
                    split_counts={s:dict(Counter(r['label'] for r in rows if r['split']==s))
                                  for s in ('train','validation','test','quarantine')},
                    limitations=['Single collection; no independent Italian farm validation.',
                                 'Five labels only, all wheat. No barley or maize recognition is supported.',
                                 'Group split uses exact pixels and 64-bit dHash distance <=4; specimen/site IDs are unavailable.',
                                 'Near-duplicate grouping reduces but cannot prove absence of leakage.',
                                 'A healthy label is not proof of absence of unrepresented disease.'])
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    (destination / 'ATTRIBUTION.txt').write_text(
        'Long, M. C.; Hartley, M.; Morris, R. J.; Brown, J. K. M. (2023). Wheat disease images (small dataset). '
        'Zenodo. https://doi.org/10.5281/zenodo.7573133\nCC BY 4.0: https://creativecommons.org/licenses/by/4.0/\n'
        + manifest['changes'] + '\nThe authors do not endorse AgroPlan.\n')
    # Five independently labelled columns, with both disease and healthy controls.
    canvas = Image.new('RGB', (1100, 880), 'white')
    draw = ImageDraw.Draw(canvas)
    for column, label in enumerate(CLASSES.values()):
        draw.text((column*220+8, 10), LABELS[label], fill='black')
        examples = [r for r in rows if r['label']==label and r['split']!='quarantine'][:4]
        for index, row in enumerate(examples):
            with Image.open(destination/row['path']) as picture:
                thumb = ImageOps.contain(picture, (206, 175))
                x, y = column*220+7, 40+index*205
                canvas.paste(thumb,(x,y))
                draw.text((x,y+177),row['id'],fill='black')
    draw.text((8, 864), 'Long et al. 2023 / Zenodo 7573133 / CC BY 4.0. Reference examples, not diagnoses.', fill='black')
    canvas.save(destination/'confronto-categorie.jpg',quality=90)
    print(json.dumps({k:manifest[k] for k in ('counts','split_counts')},ensure_ascii=False))
    print('Dataset preparato:',destination)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();prepare(args.archive,args.output)
