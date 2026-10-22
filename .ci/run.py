"""Reconstruct the verified public snapshot and run one bounded test shard."""
from pathlib import Path
import argparse,collections,gzip,hashlib,json,os,site,sqlite3,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
GUARD=r'''
from pathlib import Path
import collections, json, os, site, sys, urllib.parse
TREE=Path(os.environ['NUBE_TREE']).resolve()
SANDBOX=Path(os.environ['NUBE_SANDBOX']).resolve()
READS=collections.Counter(); DENIED=[]
RUNTIME=tuple(Path(x).resolve() for x in json.loads(os.environ['NUBE_RUNTIME']))
sys.dont_write_bytecode=True
sys.path[:]=[str(SANDBOX),str(TREE)]+[x for x in sys.path if x and any(Path(x).resolve().is_relative_to(r) for r in RUNTIME)]+[str(r) for r in RUNTIME]
def audit(event,args):
    def check(value,write=False):
        if value is None or isinstance(value,int):return
        raw=os.fsdecode(value)
        if raw in ('<stdin>','<string>',':memory:'):return
        if raw.startswith('file:'):
            raw=urllib.parse.unquote(raw[5:].split('?',1)[0])
            if raw.startswith('/') and len(raw)>2 and raw[2]==':':raw=raw[1:]
        target=Path(raw).resolve()
        ok=target.is_relative_to(SANDBOX) or not write and (target.is_relative_to(TREE) or any(target.is_relative_to(r) for r in RUNTIME))
        if not ok:
            DENIED.append({'evento':event,'operacion':'escritura' if write else 'lectura','ruta':str(target)})
            raise PermissionError('limite del ensayo aislado')
        if not write and target.is_relative_to(TREE) and target.is_file():READS[target.relative_to(TREE).as_posix()]+=1
    if event=='open':
        mode=args[1]; flags=args[2]
        write=isinstance(mode,str) and any(c in mode for c in 'wax+') or isinstance(flags,int) and bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        check(args[0],write)
    elif event in ('os.listdir','os.scandir','os.chdir'):check(args[0])
    elif event in ('os.remove','os.rmdir','os.mkdir','os.chmod','os.utime','os.truncate'):check(args[0],True)
    elif event in ('os.rename','os.link','os.symlink'):check(args[0],True);check(args[1],True)
    elif event=='sqlite3.connect':
        if str(args[0])!=':memory:':check(args[0],True)
    elif event.startswith('socket.') or event in ('subprocess.Popen','os.system','os.startfile','os.posix_spawn','os.spawn'):
        DENIED.append({'evento':event});raise PermissionError('red y subprocesos prohibidos')
sys.addaudithook(audit)
'''
PLUGIN=r'''
from pathlib import Path
import collections,hashlib,json,os,re,sys,pytest
import sitecustomize as guard
records=[];errors=[];collected=[]
def pytest_collection_modifyitems(items):
    for item in items:collected.append(item.nodeid)
def pytest_exception_interact(node,call,report):
    if call.excinfo:
        exc=call.excinfo.value
        row={'nodo':report.nodeid.split('[')[0],'fase':getattr(call,'when',None),'tipo':type(exc).__name__}
        if isinstance(exc,ModuleNotFoundError):row['modulo_ausente']=exc.name
        if isinstance(exc,FileNotFoundError) and exc.filename:row['recurso_ausente']=str(exc.filename)
        if type(exc).__name__=='CollectError':
            msg=str(exc)
            missing=re.findall(r"(?:No module named|cannot import name) ['\"]([\w.]+)",msg)
            if missing:row['importaciones_ausentes']=sorted(set(missing))
            row['tipos_internos']=sorted(set(re.findall(r'\b([A-Z]\w*(?:Error|Exception)):',msg)))
        errors.append(row)
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item,call):
    result=yield;report=result.get_result()
    if report.when=='call' or report.failed or report.skipped:
        row={'fichero':item.path.relative_to(guard.TREE).as_posix(),'prueba':item.nodeid.split('[')[0].split('::',1)[-1],'id_sha256':hashlib.sha256(item.nodeid.encode()).hexdigest(),'fase':report.when,'resultado':report.outcome,'tipo':call.excinfo.typename if call.excinfo else None}
        if call.excinfo and isinstance(call.excinfo.value,FileNotFoundError) and call.excinfo.value.filename:row['recurso_ausente']=str(call.excinfo.value.filename)
        records.append(row)
def pytest_sessionfinish(session,exitstatus):
    result={'codigo_salida':int(exitstatus),'coleccionadas':len(collected),'pruebas':records,'errores':errors,'lecturas_foto':dict(guard.READS),'barreras':guard.DENIED,'modulos_importados_foto':sorted({str(Path(m.__file__).resolve().relative_to(guard.TREE)).replace('\\','/') for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(guard.TREE)})}
    (guard.SANDBOX/'resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
'''
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
    return h.hexdigest()
def reconstruct(work):
    folder=ROOT/'base_publica'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
    archive=work/'base.gz'
    with archive.open('wb') as out:
        for chunk in manifest['chunks']:
            name=chunk['name']
            if Path(name).name!=name:raise ValueError('invalid chunk path')
            path=folder/name
            if path.stat().st_size!=chunk['bytes'] or digest(path)!=chunk['sha256']:raise ValueError('chunk integrity mismatch')
            out.write(path.read_bytes())
    dest=work/'datos'/'conocimiento.sqlite'
    with gzip.open(archive,'rb') as src,dest.open('wb') as out:
        while data:=src.read(1024*1024):out.write(data)
    if dest.stat().st_size!=manifest['sqlite_bytes'] or digest(dest)!=manifest['sqlite_sha256']:raise ValueError('database integrity mismatch')
    c=sqlite3.connect(dest.as_uri()+'?mode=ro',uri=True);c.execute('pragma query_only=on')
    assert c.execute('pragma query_only').fetchone()[0]==1
    assert c.execute('pragma integrity_check').fetchone()==('ok',)
    assert not c.execute('pragma foreign_key_check').fetchall()
    assert not c.execute("select id from documento where clase_derechos<>'publico'").fetchall()
    for tab,count in manifest['rows'].items():
        if not tab.replace('_','').isalnum():raise ValueError('invalid table')
        assert c.execute('select count(*) from "'+tab+'"').fetchone()[0]==count
    c.close()
    return dest
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shard',type=int,required=True);parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    shards=json.loads((ROOT/'.ci'/'shards.json').read_text(encoding='utf8'))
    tests=shards[args.shard]['tests']
    for name in tests:
        if not (ROOT/name).resolve().is_relative_to(ROOT) or not Path(name).name.startswith('test_'):raise ValueError('invalid test path')
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=False)
    for name in ('datos','tmp','local','cache'):(work/name).mkdir()
    reconstruct(work)
    (work/'sitecustomize.py').write_text(GUARD,encoding='utf8')
    (work/'nube_plugin.py').write_text(PLUGIN,encoding='utf8')
    env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','PATH','COMSPEC','PATHEXT','SYSTEMDRIVE','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE')}
    env.update({'PYTHONPATH':str(work)+os.pathsep+str(ROOT),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','NUBE_TREE':str(ROOT),'NUBE_SANDBOX':str(work),'NUBE_RUNTIME':json.dumps([sys.base_prefix,*site.getsitepackages(),site.getusersitepackages()]),'ICT155_BIBLIOTECA':str(work/'biblioteca_ausente'),'ICT155_DATOS':str(work/'datos'),'LOCALAPPDATA':str(work/'local'),'APPDATA':str(work/'local'),'HOME':str(work/'local'),'USERPROFILE':str(work/'local'),'TEMP':str(work/'tmp'),'TMP':str(work/'tmp'),'ICT155_TMP':str(work/'tmp'),'ICT155_REVISION_CACHE_DIR':str(work/'cache'),'ICT155_CLAUDE':'PROHIBIDO_PROCESO_REAL','ICT155_CLAUDE_FALSO':'1','PYTHONUTF8':'1'})
    # An explicitly provided, offline pytest runtime is used only by local QA.
    extra=os.environ.get('NUBE_OFFLINE_RUNTIME')
    if extra:
        paths=json.loads(env['NUBE_RUNTIME']);paths.append(str(Path(extra).resolve()));env['NUBE_RUNTIME']=json.dumps(paths)
    cmd=[sys.executable,'-X','utf8','-B','-m','pytest','-p','no:terminal','-p','no:cacheprovider','-p','no:logging','-p','no:faulthandler','-p','nube_plugin','--capture=sys','--noconftest','--rootdir',str(ROOT),'--confcutdir',str(ROOT),'--basetemp',str(work/'tmp'/'pytest'),*[str(ROOT/x) for x in tests]]
    start=time.monotonic()
    with (work/'pytest.log').open('wb') as log:
        try:code=subprocess.run(cmd,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600).returncode
        except subprocess.TimeoutExpired:code=124
    result_path=work/'resultado.json'
    if not result_path.exists():
        print('Missing pytest result; inspect',work/'pytest.log');return code or 1
    result=json.loads(result_path.read_text(encoding='utf8'));counts=dict(collections.Counter(x['resultado'] for x in result['pruebas']))
    # pytest 9 emits extra successful call reports for unittest subtests.
    good=code==0 and result['coleccionadas']>0 and len(result['pruebas'])>=result['coleccionadas'] and counts.get('passed',0)==len(result['pruebas']) and not result['errores'] and not result['barreras']
    summary={'shard':args.shard,'tests':tests,'python':sys.version,'exit_code':code,'collected':result['coleccionadas'],'passed':result['coleccionadas'] if good else counts.get('passed',0),'subtests':max(0,len(result['pruebas'])-result['coleccionadas']),'outcomes':counts,'barriers':len(result['barreras']),'errors':len(result['errores']),'seconds':round(time.monotonic()-start,2),'ok':good}
    (work/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary))
    return 0 if good else 1
if __name__=='__main__':sys.exit(main())
