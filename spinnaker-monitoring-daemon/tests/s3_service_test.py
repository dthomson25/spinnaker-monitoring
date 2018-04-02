import os

import mock
import unittest
import tempfile
from mock import patch
from StringIO import StringIO

import unittest
import s3_service

class S3ServiceTest(unittest.TestCase):
  @staticmethod
  def setUpClass():
    key = 'S3_BUCKET'
    if key in os.environ:
        del os.environ[key]

  def test_initialize_from_options(self):
    test_bucket = "test"
    options = { "bucket" : test_bucket}
    service = s3_service.make_s3_service(options)

    self.assertIsNotNone(service)
    self.assertIsNotNone(service.s3_client)

  @patch('s3_service.spectator_client.foreach_metric_in_service_map')
  def test_publish_metrics_with(self, mock_xform):
    test_bucket = "test"
    options = { "bucket" : test_bucket}
    service = s3_service.make_s3_service(options)
    bogus_data = [i for i in range(0, service.MAX_BATCH * 2)]
    for test_case in [
            (service.MAX_BATCH - 1, [bogus_data[0:service.MAX_BATCH-1]]),
            (service.MAX_BATCH, [bogus_data[0:service.MAX_BATCH]]),
            (service.MAX_BATCH + 1,
               [bogus_data[0:service.MAX_BATCH],
                bogus_data[service.MAX_BATCH:service.MAX_BATCH + 1]])]:
      mock_xform.side_effect = (lambda ignore_metrics, ignore_fn, result:
                                  result.extend(bogus_data[0:test_case[0]]))
      with patch('s3_service.S3MetricsService.send_metrics') as mock_send: 
        self.assertEquals(
            test_case[0], service.publish_metrics(service_metrics={}))
        self.assertEquals(mock_send.call_args_list,
                        [mock.call(batch) for batch in test_case[1]])

  


if __name__ == '__main__':
  unittest.main()
