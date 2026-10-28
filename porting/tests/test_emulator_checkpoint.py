"""Host filesystem transaction tests; these do not prove Azahar restore support."""
import ctypes as C
import hashlib,json,shutil,sys,tempfile,unittest,uuid
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P/'tools'))
import emulator_checkpoint as ck

class Function:
    def __init__(self,fn):self.fn=fn
    def __call__(self,*args):return self.fn(*args)

class Core:
    def __init__(self):
        self.memory=b'original emulator memory';self.accept=True;self.loads=0;self.on_load=None
        self.retro_serialize_size=Function(lambda:len(self.memory))
        self.retro_serialize=Function(self.save)
        self.retro_unserialize=Function(self.load)
    def save(self,p,n):C.memmove(p,self.memory,n);return True
    def load(self,p,n):
        self.loads+=1
        if not self.accept:return False
        if self.on_load:self.on_load()
        self.memory=C.string_at(p,n);return True

class Checkpoint(unittest.TestCase):
    def setUp(self):
        ck.PRIVATE.mkdir(parents=True,exist_ok=True)
        self.work=ck.inside(Path(tempfile.mkdtemp(dir=ck.PRIVATE)),ck.PRIVATE)
        self.card=ck.inside(P/'analysis/azahar-smoke'/('checkpoint-selftest-'+uuid.uuid4().hex),P/'analysis/azahar-smoke')
        self.card.mkdir();self.slot=self.work/'slot';self.core=Core();self.profile={'cpu_percent':400}
        self.app=self.work/'app.cxi';self.app.write_bytes(b'local test app')
        self.dll=self.work/'core.dll';self.dll.write_bytes(b'local test emulator')
        self.write('test-output/save-bridge/var/settings.sb',b'saved settings')
        self.write('test-output/texture-pages/page-00000001.bin',b'saved texture')
        self.write('assets/original.bin',b'untouched original fixture')
        self.write('engine-azahar-log.txt',b'Frame 1 returned\n')
        self.saved=ck.save(self.core,self.slot,self.card,self.profile,self.app,self.dll)
    def tearDown(self):
        shutil.rmtree(ck.inside(self.work,ck.PRIVATE))
        shutil.rmtree(ck.inside(self.card,P/'analysis/azahar-smoke'))
    def write(self,name,data):
        p=self.card/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    def load(self):return ck.load(self.core,self.slot,self.card,self.profile,self.app,self.dll)
    def future(self):
        self.write('test-output/save-bridge/var/settings.sb',b'future settings')
        self.write('test-output/save-bridge/var/new-save.sb',b'future new file')
        self.write('engine-azahar-log.txt',b'future journal')
    def test_restore_memory_sd_and_journal_keeps_pre_restore_backup(self):
        self.future();self.core.memory=b'future RAM'
        def reopen_write_handles():
            self.write('engine-azahar-log.txt',b'');self.write('test-output/texture-pages/page-00000001.bin',b'')
        self.core.on_load=reopen_write_handles;r=self.load()
        self.assertEqual(self.core.memory,b'original emulator memory')
        self.assertEqual((self.card/'test-output/save-bridge/var/settings.sb').read_bytes(),b'saved settings')
        self.assertFalse((self.card/'test-output/save-bridge/var/new-save.sb').exists())
        self.assertEqual((self.card/'engine-azahar-log.txt').read_bytes(),b'Frame 1 returned\n')
        self.assertEqual((self.card/'test-output/texture-pages/page-00000001.bin').read_bytes(),b'saved texture')
        self.assertEqual((P/r['backup']/'test-output/save-bridge/var/new-save.sb').read_bytes(),b'future new file')
        self.assertEqual((self.card/'assets/original.bin').read_bytes(),b'untouched original fixture')
    def test_wrong_cxi_is_refused_before_sd_mutation(self):
        self.future();self.app.write_bytes(b'different app')
        with self.assertRaisesRegex(AssertionError,'CXI differs'):self.load()
        self.assertEqual((self.card/'engine-azahar-log.txt').read_bytes(),b'future journal');self.assertEqual(self.core.loads,0)
    def test_corrupt_state_is_refused_before_sd_mutation(self):
        self.future();p=self.slot/self.saved['generation']/'emulator.state';p.write_bytes(b'x'*p.stat().st_size)
        with self.assertRaises(AssertionError):self.load()
        self.assertEqual((self.card/'engine-azahar-log.txt').read_bytes(),b'future journal');self.assertEqual(self.core.loads,0)
    def test_backend_refusal_rolls_back_every_private_file(self):
        self.future();self.core.accept=False
        with self.assertRaisesRegex(RuntimeError,'restore failed'):self.load()
        self.assertEqual((self.card/'test-output/save-bridge/var/settings.sb').read_bytes(),b'future settings')
        self.assertEqual((self.card/'test-output/save-bridge/var/new-save.sb').read_bytes(),b'future new file')
        self.assertEqual((self.card/'engine-azahar-log.txt').read_bytes(),b'future journal')
    def test_profile_and_path_escape_are_refused(self):
        self.profile['cpu_percent']=100
        with self.assertRaisesRegex(AssertionError,'profile differs'):self.load()
        self.profile['cpu_percent']=400
        p=self.slot/self.saved['generation']/'manifest.json';m=json.loads(p.read_text());m['files']['../../outside']={'bytes':1,'sha256':'bad'};p.write_text(json.dumps(m))
        with self.assertRaises(ValueError):self.load()
        self.assertEqual(self.core.loads,0)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checkpoint))
    (P/'analysis/emulator-checkpoint-host-tests.json').write_text(json.dumps({'host_tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),
        'azahar_restore_verified':False,'helper_sha256':hashlib.sha256((P/'tools/emulator_checkpoint.py').read_bytes()).hexdigest()},indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
