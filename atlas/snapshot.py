"""Portable, checksummed research outputs; only atlas-owned paths are restored.

python -m atlas.snapshot restore
python -m atlas.snapshot build   # maintainers, after estimation and reporting
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent
DEST=BASE/'snapshot'
RAW_KEEP={'cwy_mirror.xlsx','bolhuis_current.xlsx','bolhuis_11172025.xlsx',
    'jk_ecb_monthly.csv','ea_mpd_latest.xlsx','ea_mpd_current_other.xlsx',
    'usmpd_latest.xlsx','usmpd_surprises.zip','ukmpd_latest.xlsx',
    'jk_main.m','jk_mypc.m','jk_signrestr_median.m','jk_d2m2q.m'}


def digest(data):return hashlib.sha256(data).hexdigest()


def selected_files():
    for directory in ['data','results','figures']:
        for path in sorted((BASE/directory).rglob('*')):
            if not path.is_file() or path.name=='specifications.jsonl.gz':continue
            if path.name=='coefficients.csv.gz':
                # Permanent compact records also contain every coefficient.
                # Keep current aggregate tables once, rather than duplicates.
                aggregate=path.parent==BASE/'results'/'baseline' or path.parent.parent.name=='chunks'
                if not aggregate:continue
            if 'baseline_archive' in path.parts and path.name!='attempt_records.jsonl.gz':continue
            yield path
    for name in sorted(RAW_KEEP):
        path=BASE/'raw'/name
        if path.exists():yield path


def build(part_bytes=4*1024*1024):
    DEST.mkdir(exist_ok=True)
    stream=io.BytesIO();members=[]
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in selected_files():
            rel=path.relative_to(ROOT).as_posix();body=path.read_bytes()
            info=zipfile.ZipInfo(rel,date_time=(2026,11,22,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,body)
            members.append(dict(path=rel,bytes=len(body),sha256=digest(body)))
    payload=stream.getvalue();parts=[]
    for i,start in enumerate(range(0,len(payload),part_bytes)):
        data=payload[start:start+part_bytes];name=f'research_snapshot.zip.part{i:03d}'
        (DEST/name).write_bytes(data)
        parts.append(dict(file=name,bytes=len(data),sha256=digest(data)))
    manifest=dict(format='concatenated_zip_v1',created_date='2026-11-22',
        archive_sha256=digest(payload),archive_bytes=len(payload),parts=parts,members=members,
        excluded='regenerable internal LP score arrays/repeated sample-key lists and duplicated coefficient tables; permanent attempt records retain all economic estimates/covariances/diagnostics')
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(snapshot_bytes=len(payload),parts=len(parts),members=len(members))))
    return manifest


def restore(root=ROOT,replace=False):
    manifest=json.loads((DEST/'manifest.json').read_text());chunks=[]
    for part in manifest['parts']:
        data=(DEST/part['file']).read_bytes()
        if len(data)!=part['bytes'] or digest(data)!=part['sha256']:
            raise ValueError('Snapshot part checksum mismatch: '+part['file'])
        chunks.append(data)
    payload=b''.join(chunks)
    if digest(payload)!=manifest['archive_sha256']:raise ValueError('Archive checksum mismatch')
    expected={m['path']:m for m in manifest['members']}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if set(archive.namelist())!=set(expected):raise ValueError('Unexpected archive member')
        for name in archive.namelist():
            rel=Path(name)
            if rel.is_absolute() or '..'in rel.parts or rel.parts[:2] not in [
                ('atlas','data'),('atlas','results'),('atlas','figures'),('atlas','raw')]:
                raise ValueError('Refusing path outside atlas artifacts: '+name)
            data=archive.read(name);meta=expected[name]
            if len(data)!=meta['bytes'] or digest(data)!=meta['sha256']:raise ValueError(name)
            destination=root/rel
            if destination.exists() and destination.read_bytes()!=data and not replace:
                raise ValueError('Existing different atlas artifact; use --replace after review: '+name)
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(data)
    print(json.dumps(dict(restored_members=len(expected),archive_sha256=manifest['archive_sha256'])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['build','restore'])
    parser.add_argument('--replace',action='store_true')
    args=parser.parse_args()
    build() if args.action=='build' else restore(replace=args.replace)
