"""Console input, JSON fidelity, and localhost HTTP contract checks."""
import http.client
import json
import math
import tempfile
import threading
from pathlib import Path
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from experiments.console import validate_request, strict_numbers
from scripts.serve_console import Handler


class ConsoleInputTests(unittest.TestCase):
    def test_unknown_fields_and_invalid_numbers_rejected(self):
        for request in ({'script':'anything'}, {'hours':0}, {'dt_s':float('nan')},
                        {'hours':True}, {'rx_aperture_m':-1}, {'scenario':'unknown'}):
            with self.subTest(request=request),self.assertRaises(ValueError):
                validate_request(request)

    def test_parameters_are_preserved_and_time_is_utc(self):
        values=validate_request(dict(start_time='2025-11-09T13:00:00+01:00',rf_power_dbm=35,
                                     background_hz=0,rx_aperture_m=1.5))
        self.assertEqual(values['start_time'],'2025-11-09T12:00:00Z')
        self.assertEqual(values['rf_power_dbm'],35)
        self.assertEqual(values['background_hz'],0)
        self.assertEqual(values['rx_aperture_m'],1.5)

    def test_infinity_is_unknown_with_location_and_zero_is_preserved(self):
        paths=[]
        value=strict_numbers(dict(loss_db=float('inf'),keys=0,qber=0.5,blocked_reason='cloud_blocked'),paths)
        self.assertIsNone(value['loss_db'])
        self.assertEqual(value['keys'],0)
        self.assertEqual(paths,['.loss_db'])
        self.assertEqual(value['blocked_reason'],'cloud_blocked')
        json.dumps(value,allow_nan=False)


class ConsoleHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self,path,method='GET',body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        connection.request(method,path,body=body,headers=headers or {})
        response=connection.getresponse()
        result=(response.status,response.getheader('Content-Type'),response.read())
        connection.close()
        return result

    def test_assets_and_api_are_available(self):
        self.assertEqual(self.request('/')[0],200)
        status,content_type,_=self.request('/console/core.mjs')
        self.assertEqual(status,200)
        self.assertEqual(content_type,'text/javascript')
        status,_,body=self.request('/api/config')
        self.assertEqual(status,200)
        self.assertIn('scenarios',json.loads(body))

    def test_workspace_and_arbitrary_paths_are_not_served(self):
        for path in ('/.env','/.git/config','/console/../../config/__init__.py','/api/runs/../../README.md'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0],404)

    def test_cross_origin_post_is_rejected(self):
        status,_,_=self.request('/api/run','POST','{}',{'Content-Type':'application/json','Origin':'https://unrelated.example'})
        self.assertEqual(status,403)

    def test_invalid_request_does_not_spawn_a_worker(self):
        with patch('scripts.serve_console.subprocess.Popen') as process:
            status,_,_=self.request('/api/run','POST','{"hours":-1}',{'Content-Type':'application/json'})
            self.assertEqual(status,400)
            process.assert_not_called()


if __name__=='__main__':
    unittest.main()
