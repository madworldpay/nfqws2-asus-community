import os
from pathlib import Path
import shutil
import subprocess
import unittest


class CustomPickerUiTests(unittest.TestCase):
    def test_custom_picker_measurements_and_interactive_workflows(self):
        node=os.environ.get('NODE_BINARY')or shutil.which('node')
        if not node:self.skipTest('Node is required for actual picker module checks')
        script=Path(__file__).with_name('test_strategy_picker_custom_ui.mjs')
        result=subprocess.run([node,'--test',str(script)],capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
