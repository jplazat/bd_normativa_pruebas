"""Reconstruct the verified public snapshot and run one bounded test shard."""
from pathlib import Path
import argparse,collections,gzip,hashlib,json,os,site,sqlite3,subprocess,sys,time,shutil
ROOT=Path(__file__).resolve().parents[1]
GUARD=r'''
from pathlib import Path
import collections, json, os, site, sys, urllib.parse, shlex
TREE=Path(os.environ['NUBE_TREE']).resolve()
SANDBOX=Path(os.environ['NUBE_SANDBOX']).resolve()
LIBRARY=Path(os.environ['NUBE_LIBRARY']).resolve()
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
        ok=target.is_relative_to(SANDBOX) or not write and (target.is_relative_to(TREE) or target.is_relative_to(LIBRARY) or any(target.is_relative_to(r) for r in RUNTIME))
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
    elif event=='subprocess.Popen':
        executable, argv, cwd, childenv=args
        inherited=childenv if childenv is not None else os.environ
        command=list(argv) if isinstance(argv,(tuple,list)) else [x.strip('"') for x in shlex.split(argv,posix=False)] if isinstance(argv,str) else []
        executable=executable or (command[0] if command else '')
        exe=Path(os.fsdecode(executable)).resolve()
        python=exe==Path(sys.executable).resolve() and command and not any(x in command for x in ('-I','-S','-E'))
        intact=all(inherited.get(k)==os.environ.get(k) for k in ('NUBE_TREE','NUBE_SANDBOX','NUBE_RUNTIME','PYTHONPATH'))
        git=Path(os.fsdecode(executable)).name.lower() in ('git','git.exe') and command[1:3]==['-C',str(TREE)] and command[3:] in (['rev-parse','--short','HEAD'],['rev-parse','HEAD'])
        pdf=Path(os.fsdecode(executable)).name.lower() in ('pdftotext','pdftotext.exe') and command and command[-1]=='-' and any(str(x).lower().endswith('.pdf') for x in command)
        if pdf:
            for x in command[1:]:
                if str(x).lower().endswith('.pdf'):check(x)
        if not ((python and intact) or git or pdf):
            DENIED.append({'evento':event,'tipo':'proceso_no_permitido'});raise PermissionError('solo Python local con barreras heredadas o metadatos Git locales')
        if cwd is not None:check(cwd)
    elif event.startswith('socket.') or event in ('os.system','os.startfile','os.posix_spawn','os.spawn'):
        DENIED.append({'evento':event});raise PermissionError('red y procesos no permitidos')
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
        row={'fixture':getattr(exc,'argname',None),'traza':[{'file':str(e.path),'line':e.lineno+1,'function':e.name} for e in list(call.excinfo.traceback)[-6:]],'nodo':report.nodeid.split('[')[0],'fase':getattr(call,'when',None),'tipo':type(exc).__name__}
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
        
        if report.skipped and isinstance(report.longrepr,tuple):row['omitida_en']={'file':str(report.longrepr[0]),'line':report.longrepr[1]}
        records.append(row)
def pytest_sessionfinish(session,exitstatus):
    result={'codigo_salida':int(exitstatus),'coleccionadas':len(collected),'pruebas':records,'errores':errors,'lecturas_foto':dict(guard.READS),'barreras':guard.DENIED,'modulos_importados_foto':source_modules()}
    (guard.SANDBOX/'resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')

def source_modules():
    import types
    found=set()
    for module in list(sys.modules.values()):
        if not isinstance(module,types.ModuleType):continue
        filename=vars(module).get('__file__')
        if not isinstance(filename,(str,bytes,os.PathLike)):continue
        path=Path(os.path.abspath(os.fsdecode(filename)))
        if not path.is_relative_to(guard.TREE):continue
        path=path.resolve()
        if path.is_relative_to(guard.TREE):found.add(path.relative_to(guard.TREE).as_posix())
    return sorted(found)

_RESUMEN = {}
@pytest.fixture(scope='session')
def base_temporal(tmp_path_factory):
    from ict155 import config, ingesta
    if not config.BIBLIOTECA.exists():pytest.skip('biblioteca no disponible')
    path=tmp_path_factory.mktemp('base')/'sesion.sqlite'
    _RESUMEN.update(ingesta.reconstruir(path))
    return path
@pytest.fixture(scope='session')
def resumen_base(base_temporal):return dict(_RESUMEN)
@pytest.fixture(scope='module')
def con(request):
    import sqlite3
    if os.environ.get('NUBE_CON_SNAPSHOT')=='1':
        from ict155 import config
        path=config.BD
    else:path=request.getfixturevalue('base_temporal')
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    connection.execute('pragma query_only=on')
    assert connection.execute('pragma query_only').fetchone()[0]==1
    yield connection
    connection.close()
@pytest.fixture(scope='session',autouse=True)
def _revision_independiente_sin_modelo_real(tmp_path_factory):
    fake=guard.TREE/'pruebas/fixtures/revision_independiente_r23/claude_falso.py'
    folder=tmp_path_factory.mktemp('claude_falso')
    (folder/'guion.json').write_text(json.dumps([{'result':'{"objeciones": []}'}]),encoding='utf8')
    values={'ICT155_CLAUDE':json.dumps([sys.executable,str(fake)]),'ICT155_CLAUDE_FALSO':str(folder),'ICT155_REVISION_CACHE_DIR':str(tmp_path_factory.mktemp('revision_cache'))}
    before={k:os.environ.get(k) for k in values};os.environ.update(values)
    yield
    for k,v in before.items():
        if v is None:os.environ.pop(k,None)
        else:os.environ[k]=v
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
def run_module(rel, work, base, *, diagnostic=False, timeout=None, library=None):
    work.mkdir(parents=True,exist_ok=False)
    tree=work/'tree'
    shutil.copytree(ROOT,tree,ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache','base_publica','biblioteca_publica'),copy_function=shutil.copyfile)
    for name in ('datos','tmp','local','cache'):(work/name).mkdir()
    shutil.copyfile(base,work/'datos/conocimiento.sqlite')
    (work/'sitecustomize.py').write_text(GUARD,encoding='utf8')
    (work/'nube_plugin.py').write_text(PLUGIN,encoding='utf8')
    env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH','COMSPEC','PATHEXT','SYSTEMDRIVE','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE') if k in os.environ}
    env.update({'PYTHONPATH':str(work)+os.pathsep+str(tree),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','NUBE_TREE':str(tree),'NUBE_SANDBOX':str(work),'NUBE_RUNTIME':json.dumps([sys.base_prefix,*site.getsitepackages(),site.getusersitepackages()]),'ICT155_BIBLIOTECA':str(tree/'biblioteca_publica'),'ICT155_DATOS':str(work/'datos'),'LOCALAPPDATA':str(work/'local'),'APPDATA':str(work/'local'),'HOME':str(work/'local'),'USERPROFILE':str(work/'local'),'TEMP':str(work/'tmp'),'TMP':str(work/'tmp'),'ICT155_TMP':str(work/'tmp'),'ICT155_REVISION_CACHE_DIR':str(work/'cache'),'ICT155_CLAUDE':'PROHIBIDO_PROCESO_REAL','ICT155_CLAUDE_FALSO':'1','PYTHONUTF8':'1','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':str(work/'gitconfig_vacio'),'GIT_CEILING_DIRECTORIES':str(work)})
    extra=os.environ.get('NUBE_OFFLINE_RUNTIME')
    env['NUBE_LIBRARY']=str(library or ROOT/'biblioteca_publica')
    env['ICT155_BIBLIOTECA']=env['NUBE_LIBRARY']
    env['NUBE_CON_SNAPSHOT']='1'
    pdf=shutil.which('pdftotext')
    if not pdf and os.name=='nt':
        for sub in ('mingw64','ucrt64'):
            candidate=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git'/sub/'bin'/'pdftotext.exe'
            if candidate.is_file():pdf=str(candidate);break
    if pdf:env['ICT155_PDFTOTEXT']=pdf
    if extra:
        paths=json.loads(env['NUBE_RUNTIME']);paths.append(str(Path(extra).resolve()));env['NUBE_RUNTIME']=json.dumps(paths)
    cmd=[sys.executable,'-X','utf8','-B','-m','pytest','-p','no:terminal','-p','no:cacheprovider','-p','no:logging','-p','no:faulthandler','-p','nube_plugin','--capture=sys','--noconftest','--rootdir',str(tree),'--confcutdir',str(tree),'--basetemp',str(work/'tmp/pytest'),str(tree/rel)]
    if diagnostic:cmd.insert(6,'--maxfail=1')
    start=time.monotonic()
    with (work/'pytest.log').open('wb') as log:
        try:code=subprocess.run(cmd,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout or (2400 if rel.endswith('test_reconstruccion.py') else 600 if not diagnostic else 120),creationflags=getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0)).returncode
        except subprocess.TimeoutExpired:code=124
    result_path=work/'resultado.json'
    result=json.loads(result_path.read_text(encoding='utf8')) if result_path.exists() else {}
    counts=dict(collections.Counter(x['resultado'] for x in result.get('pruebas',[])))
    good=code==0 and result.get('coleccionadas',0)>0 and len(result.get('pruebas',[]))>=result['coleccionadas'] and counts.get('passed',0)==len(result['pruebas']) and not result.get('errores') and not result.get('barreras')
    summary={'file':rel,'exit_code':code,'collected':result.get('coleccionadas',0),'passed':result.get('coleccionadas',0) if good else counts.get('passed',0),'subtests':max(0,len(result.get('pruebas',[]))-result.get('coleccionadas',0)),'outcomes':counts,'barriers':len(result.get('barreras',[])),'errors':len(result.get('errores',[])),'seconds':round(time.monotonic()-start,2),'ok':good}
    (work/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return summary

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shard',type=int,required=True);parser.add_argument('--work',type=Path,required=True);args=parser.parse_args()
    shards=json.loads((ROOT/'.ci/shards.json').read_text(encoding='utf8'));tests=shards[args.shard]['tests']
    for name in tests:
        if not (ROOT/name).resolve().is_relative_to(ROOT) or not Path(name).name.startswith('test_'):raise ValueError('invalid test path')
    work=args.work.resolve()
    if work.is_relative_to(ROOT):raise ValueError('work must be outside the publication tree')
    work.mkdir(parents=True,exist_ok=False);(work/'datos').mkdir();base=reconstruct(work)
    start=time.monotonic();rows=[]
    for i,rel in enumerate(tests):
        row=run_module(rel,work/f'module_{i:03}',base);rows.append(row);print(json.dumps(row),flush=True)
        if row['exit_code']!=0 or row['passed']!=row['collected']:
            # Only test names, phases and exception types: never captured output (it could quote licensed text).
            try:recs=json.loads((work/f'module_{i:03}'/'resultado.json').read_text(encoding='utf8')).get('pruebas',[])
            except (OSError,ValueError):recs=[]
            bad=[f"{x.get('prueba')}[{x.get('fase')}:{x.get('resultado')}:{x.get('tipo')}]{'(falta '+x['recurso_ausente']+')' if x.get('recurso_ausente') else ''}" for x in recs if x.get('resultado')!='passed'][:6]
            print(f"::error title={rel}::exit={row['exit_code']} collected={row['collected']} passed={row['passed']} outcomes={row['outcomes']} | "+' ; '.join(bad),flush=True)
    summary={'shard':args.shard,'tests':tests,'python':sys.version,'collected':sum(x['collected'] for x in rows),'passed':sum(x['passed'] for x in rows),'subtests':sum(x['subtests'] for x in rows),'barriers':sum(x['barriers'] for x in rows),'errors':sum(x['errors'] for x in rows),'seconds':round(time.monotonic()-start,2),'ok':all(x['ok'] for x in rows),'modules':rows}
    (work/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary),flush=True)
    return 0 if summary['ok'] else 1
if __name__=='__main__':sys.exit(main())
