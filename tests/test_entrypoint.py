import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('entrypoint',Path(__file__).resolve().parents[1]/'docker/entrypoint.py');entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

class Entrypoint(unittest.TestCase):
    def test_no_empty_replica_implicit_initialization(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)/'pb_data';data.mkdir()
            with patch.object(entry,'run_command') as run,patch.object(entry,'verify',side_effect=entry.StartupError('missing database')):
                with self.assertRaises(entry.StartupError):entry.restore_database(data)
            args=run.call_args.args[0]
            self.assertNotIn('-if-replica-exists',args)
            self.assertFalse((data/'data.db').exists())
    def test_partial_state_blocks_automatic_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);(data/'identity-recovery.pending').write_text('pending')
            with patch.object(entry,'run_command') as run,self.assertRaises(entry.StartupError):entry.restore_database(data)
            run.assert_not_called()
    def test_init_refuses_an_existing_replica(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)/'pb_data';data.mkdir()
            def restore(args):Path(args[args.index('-o')+1]).write_bytes(b'synthetic')
            with patch.object(entry,'run_command',side_effect=restore),self.assertRaises(entry.StartupError):entry.restore_database(data,initialize=True)
            self.assertFalse((data/'data.db').exists())
    def test_recovery_marker_precedes_restored_database_adoption(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)/'pb_data';data.mkdir()
            def restore(args):Path(args[args.index('-o')+1]).write_bytes(b'synthetic')
            with patch.object(entry,'run_command',side_effect=restore),patch.object(entry,'verify'):
                self.assertTrue(entry.restore_database(data))
            self.assertTrue((data/'identity-recovery.pending').is_file())
            self.assertEqual((data/'data.db').read_bytes(),b'synthetic')

if __name__=='__main__':unittest.main()
