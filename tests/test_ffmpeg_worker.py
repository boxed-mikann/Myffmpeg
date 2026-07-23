import os
import sys
import time
import unittest
from PySide6.QtWidgets import QApplication

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.ffmpeg_worker import FFmpegWorker
from tests.generate_dummy import generate_dummy_video

class TestFFmpegWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # QApplication needed for Qt Signals & Threads
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

        cls.dummy_in = os.path.join(PROJECT_ROOT, "tests", "worker_input.mp4")
        generate_dummy_video(cls.dummy_in, duration_sec=5)

    @classmethod
    def tearDownClass(cls):
        if os.path.isfile(cls.dummy_in):
            try:
                os.remove(cls.dummy_in)
            except OSError:
                pass

    def test_single_pass_execution(self):
        output_file = os.path.join(PROJECT_ROOT, "tests", "worker_out_novideo.mp3")
        if os.path.exists(output_file):
            os.remove(output_file)

        cmd = ["-y", "-i", self.dummy_in, "-vn", "-acodec", "libmp3lame", output_file]

        progress_values = []
        logs = []
        finished_result = [None, None]

        worker = FFmpegWorker(cmd, output_file, total_duration_sec=5.0)
        worker.progress_updated.connect(lambda p: progress_values.append(p))
        worker.log_received.connect(lambda l: logs.append(l))
        def on_finished(success, msg):
            finished_result[0] = success
            finished_result[1] = msg

        worker.job_finished.connect(on_finished)

        worker.start()
        start_time = time.time()
        while worker.isRunning() and (time.time() - start_time < 15):
            self.app.processEvents()
            time.sleep(0.05)

        worker.wait(5000)
        self.app.processEvents()

        self.assertIsNotNone(finished_result[0], "job_finished signal was not emitted")
        self.assertTrue(finished_result[0], f"Worker job failed: {finished_result[1]}")
        self.assertTrue(os.path.exists(output_file))
        self.assertGreater(len(logs), 0)

        # Cleanup
        if os.path.exists(output_file):
            os.remove(output_file)

    def test_worker_cancellation(self):
        output_file = os.path.join(PROJECT_ROOT, "tests", "worker_cancel_out.mp4")
        if os.path.exists(output_file):
            os.remove(output_file)

        # Encode slow preset to allow time for cancellation
        cmd = ["-y", "-i", self.dummy_in, "-c:v", "libx264", "-preset", "veryslow", "-crf", "10", output_file]
        finished_result = [None, None]

        def on_finished(success, msg):
            finished_result[0] = success
            finished_result[1] = msg

        worker = FFmpegWorker(cmd, output_file, total_duration_sec=5.0)
        worker.job_finished.connect(on_finished)

        worker.start()
        time.sleep(0.2)
        self.app.processEvents()
        
        # Trigger cancel
        worker.cancel()

        start_time = time.time()
        while worker.isRunning() and (time.time() - start_time < 5):
            self.app.processEvents()
            time.sleep(0.05)

        worker.wait(2000)
        self.app.processEvents()

        self.assertIsNotNone(finished_result[0], "job_finished signal was not emitted on cancellation")
        self.assertFalse(os.path.exists(output_file), "Partial output file should be deleted on cancellation!")

if __name__ == "__main__":
    unittest.main()
