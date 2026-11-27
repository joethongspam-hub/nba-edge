import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from nhl_goalie_backtest import retry_delay,error_label

class DownloadTests(unittest.TestCase):
    def test_retry(self):
        err=HTTPError("https://example.com",429,"limited",{"Retry-After":"30"},None)
        self.assertEqual(retry_delay(err,0),30)
        self.assertEqual(error_label(err),"HTTP_429")
        self.assertIsNone(retry_delay(HTTPError("https://example.com",404,"missing",{},None),0))
        self.assertIsNone(retry_delay(HTTPError("https://example.com",403,"forbidden",{},None),0))
    def test_backoff(self):
        err=HTTPError("https://example.com",503,"temporary",{},None)
        self.assertEqual([retry_delay(err,n) for n in range(3)],[5,10,20])
