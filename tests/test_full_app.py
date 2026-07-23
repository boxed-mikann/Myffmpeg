import os
import sys
import time
import tempfile
import unittest
from PySide6.QtWidgets import QApplication

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ui.main_window import MainWindow
from tests.generate_dummy import generate_dummy_video

class TestFullAppIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

        cls.dummy_video = os.path.join(PROJECT_ROOT, "tests", "integration_dummy.mp4")
        generate_dummy_video(cls.dummy_video, duration_sec=5, width=640, height=360, fps=30)

    @classmethod
    def tearDownClass(cls):
        if os.path.isfile(cls.dummy_video):
            try:
                os.remove(cls.dummy_video)
            except OSError:
                pass

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def test_window_components_and_file_addition(self):
        self.assertIsNotNone(self.window.input_pane)
        self.assertIsNotNone(self.window.settings_pane)
        self.assertIsNotNone(self.window.output_pane)

        # Add dummy video to input pane
        self.window.input_pane.add_files([self.dummy_video])
        
        # Process events while background probing completes
        start_time = time.time()
        while len(self.window.input_pane.get_selected_files()) == 0 and (time.time() - start_time < 5):
            self.app.processEvents()
            time.sleep(0.05)

        files = self.window.input_pane.get_all_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["width"], 640)
        self.assertEqual(files[0]["height"], 360)

    def test_tab_a_audio_extraction_flow(self):
        self.window.input_pane.add_files([self.dummy_video])
        start_time = time.time()
        while len(self.window.input_pane.get_selected_files()) == 0 and (time.time() - start_time < 5):
            self.app.processEvents()
            time.sleep(0.05)

        # Select Tab 0 (Audio Removal)
        self.window.settings_pane.tab_widget.setCurrentIndex(0)
        self.app.processEvents()

        # Expected output path
        expected_out = os.path.join(PROJECT_ROOT, "tests", "integration_dummy_novideo.mp3")
        if os.path.exists(expected_out):
            os.remove(expected_out)

        # Trigger batch processing with auto_overwrite=True
        self.window._start_batch_processing(auto_overwrite=True)

        # Wait for batch processing to finish
        start_time = time.time()
        while self.window.is_batch_running and (time.time() - start_time < 15):
            self.app.processEvents()
            time.sleep(0.05)

        self.app.processEvents()

        self.assertEqual(self.window.success_count, 1)
        self.assertTrue(os.path.isfile(expected_out))

        # Cleanup
        if os.path.exists(expected_out):
            os.remove(expected_out)

    def test_tab_b_quality_compression_flow(self):
        self.window.input_pane.add_files([self.dummy_video])
        start_time = time.time()
        while len(self.window.input_pane.get_selected_files()) == 0 and (time.time() - start_time < 5):
            self.app.processEvents()
            time.sleep(0.05)

        # Select Tab 1 (Quality Compress)
        self.window.settings_pane.tab_widget.setCurrentIndex(1)
        self.window.settings_pane.cmb_b_res.setCurrentText("640x360")
        self.window.settings_pane.spn_b_crf.setValue(28)
        self.app.processEvents()

        expected_out = os.path.join(PROJECT_ROOT, "tests", "integration_dummy_compressed.mp4")
        if os.path.exists(expected_out):
            os.remove(expected_out)

        self.window._start_batch_processing(auto_overwrite=True)

        start_time = time.time()
        while self.window.is_batch_running and (time.time() - start_time < 15):
            self.app.processEvents()
            time.sleep(0.05)

        self.app.processEvents()

        self.assertEqual(self.window.success_count, 1)
        self.assertTrue(os.path.isfile(expected_out))

        if os.path.exists(expected_out):
            os.remove(expected_out)

    def test_tab_c_size_compression_flow(self):
        self.window.input_pane.add_files([self.dummy_video])
        start_time = time.time()
        while len(self.window.input_pane.get_selected_files()) == 0 and (time.time() - start_time < 5):
            self.app.processEvents()
            time.sleep(0.05)

        # Select Tab 2 (Target Size 2-Pass Compress)
        self.window.settings_pane.tab_widget.setCurrentIndex(2)
        self.window.settings_pane.spn_c_target_mb.setValue(1.0)
        self.app.processEvents()

        expected_out = os.path.join(PROJECT_ROOT, "tests", "integration_dummy_targetsize.mp4")
        if os.path.exists(expected_out):
            os.remove(expected_out)

        self.window._start_batch_processing(auto_overwrite=True)

        start_time = time.time()
        while self.window.is_batch_running and (time.time() - start_time < 20):
            self.app.processEvents()
            time.sleep(0.05)

        self.app.processEvents()

        self.assertEqual(self.window.success_count, 1)
        self.assertTrue(os.path.isfile(expected_out))

        if os.path.exists(expected_out):
            os.remove(expected_out)

if __name__ == "__main__":
    unittest.main()
