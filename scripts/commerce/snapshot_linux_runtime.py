"""Create a fresh, public runtime snapshot on Linux native storage.

Model configuration, credentials, private state, virtualenvs and Git metadata
are excluded. Dependencies are supplied by the existing acceptance virtualenv.
"""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path

ROOTS=('src','scripts','wordpress','frontend/dist')
EXTENSIONS={'.py','.php','.json','.html','.css','.js','.mjs','.svg','.png','.jpg','.jpeg','.webp','.ico','.txt','.md','.sh','.ps1'}


def validate_native_destination(destination:Path,boundary:Path=Path('/opt/muse-acceptance'))->Path:
    absolute=Path(destination).absolute()
    for parent in (absolute,*absolute.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError('Runtime destination link is not allowed')
    resolved=absolute.resolve()
    root=Path(boundary).resolve()
    if resolved==root or not resolved.is_relative_to(root):
        raise ValueError('Runtime destination escaped acceptance boundary')
    return resolved


def snapshot_runtime(source:Path,destination:Path)->dict:
    source=Path(source).resolve()
    destination=Path(destination).absolute()
    if destination.exists():
        raise FileExistsError('A fresh runtime destination is required')
    if destination.resolve().is_relative_to(source) or source.is_relative_to(destination.resolve()):
        raise ValueError('Runtime source and destination must be separate')
    files=[]
    for name in ROOTS:
        root=source/name
        if any(path.is_symlink() or path.is_junction() for path in (root,*root.parents) if path!=source and path.is_relative_to(source)):
            raise ValueError('Runtime link is not allowed')
        if not root.is_dir():
            raise ValueError('Required runtime directory is missing')
        for directory,dirs,names in os.walk(root,followlinks=False):
            dirs[:]=sorted(name for name in dirs if not name.startswith('.') and name!='__pycache__')
            for name in [*dirs,*sorted(names)]:
                if name.startswith('.'):
                    continue
                path=Path(directory)/name
                if path.is_symlink() or path.is_junction():
                    raise ValueError('Runtime link is not allowed')
                # All traversed parents are checked above; resolving each file
                # would repeatedly stat every ancestor on the Windows mount.
                if name in names and path.suffix.lower() in EXTENSIONS and path.is_file():
                    files.append(path)
    metadata=source/'pyproject.toml'
    if metadata.is_symlink() or metadata.is_junction():
        raise ValueError('Runtime metadata link is not allowed')
    if metadata.is_file():
        files.append(metadata)
    destination.mkdir(parents=True,mode=0o700)
    manifest={'schema_version':1,'dependency_runtime':'existing acceptance virtualenv','files':{}}
    for path in files:
        relative=path.relative_to(source)
        content=path.read_bytes()
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
        sha=hashlib.sha256(content).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest()!=sha:
            raise ValueError('Runtime copy differs')
        manifest['files'][relative.as_posix()]={'sha256':sha,'bytes':len(content)}
    (destination/'runtime-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    if platform.system()!='Linux':
        raise SystemExit('A native private Linux acceptance destination is required')
    destination=validate_native_destination(args.destination)
    manifest=snapshot_runtime(args.source,destination)
    print(json.dumps({'copied_files':len(manifest['files']),'manifest':'runtime-manifest.json'}))
