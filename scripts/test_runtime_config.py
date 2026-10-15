"""Configuration regression checks: python -m unittest scripts.test_runtime_config."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import discover_jvm, get_simulation_config, project_directory, validate_runtime_config


class RuntimeConfigurationTests(unittest.TestCase):
    def test_project_paths_do_not_depend_on_working_directory(self):
        with patch.dict(os.environ, {"PROJECT_DIR": ".", "OREKIT_DATA_PATH": "orekit-data/orekit-data-main"}):
            config = get_simulation_config()
            self.assertEqual(Path(config['orekit_data_path']), project_directory() / 'orekit-data/orekit-data-main')

    def test_explicit_java_8_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            library = home / 'bin/server/jvm.dll'
            library.parent.mkdir(parents=True)
            library.touch()
            (home / 'release').write_text('JAVA_VERSION="1.8.0_451"')
            with self.assertRaisesRegex(ValueError, 'Java 9'):
                discover_jvm(str(library))

    def test_explicit_modern_java_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            library = home / 'bin/server/jvm.dll'
            library.parent.mkdir(parents=True)
            library.touch()
            (home / 'release').write_text('JAVA_VERSION="25"')
            self.assertEqual(discover_jvm(str(library)), str(library.resolve()))

    def test_invalid_numbers_have_setting_names(self):
        for value in ('bad', 'nan', 'inf'):
            with self.subTest(value=value), patch.dict(os.environ, {'SIM_TIME_STEP': value}):
                with self.assertRaisesRegex(ValueError, 'SIM_TIME_STEP'):
                    get_simulation_config()

    def test_missing_data_has_actionable_error(self):
        config = get_simulation_config()
        config['orekit_data_path'] = str(project_directory() / 'missing-runtime-test-data')
        with self.assertRaisesRegex(ValueError, 'OREKIT_DATA_PATH'):
            validate_runtime_config(config)


if __name__ == '__main__':
    unittest.main()
