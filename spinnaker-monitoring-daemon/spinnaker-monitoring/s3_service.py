"""Implements metric service for interacting with S3."""


import logging
import os
import re
import socket
import traceback
import boto3
import spectator_client
import time
import uuid


class S3MetricsService(object):
  """A metrics service for interacting with S3."""

  MAX_BATCH = 40

  def __init__(self, s3_bucket, metric_prefix, prefined_tags):
    """Constructs the object."""
    self.metric_prefix = metric_prefix
    self.s3_client = boto3.client('s3')
    self.s3_bucket = s3_bucket
    self.prefined_tags = prefined_tags

  
  def send_metrics(self, metrics):
    metrics_str = ''.join(metrics)
    key_name = str(uuid.uuid4()) + "-" + str(time.time())
    # TODO: Make ACL configurable... Ideal set in the client initialization
    # TODO: Make s3_client into separate class to allow other customers implement their cloud provider version
    self.s3_client.put_object(Body=metrics_str, Bucket=self.s3_bucket, Key=key_name, ACL="bucket-owner-full-control")  
    # TODO: remove print statement
    print metrics_str

  def __append_timeseries_point(
      self, service, name,
      instance, metric_metadata, service_metadata, result):
    """Creates a post payload for a s3 object

    Args:
      service: [string] The name of the service that the metric is from.
      name: [string] The name of the metric coming from the service.
      instance: [dict] The spectator entry for a specific metric value
         for a specific tag binding instance that we're going to append.
      metric_metadata: [dict] The spectator JSON object for the metric
         is used to get the kind and possibly other metadata.
      result: [list] The result list to append all the time series messages to.
    """
    # In practice this converts a Spinnaker Timer into either
    # <name>__count or <name>__totalTime and removes the "statistic" tag.
    name, tags = spectator_client.normalize_name_and_tags(
        name, instance, metric_metadata)
    if tags is None:
      return  # ignore metrics that had no tags because these are bogus.
    for elem in instance['values']:
      metric_name = '{prefix}.{service}.{name}'.format(prefix=self.metric_prefix,service=service, name=name)
      metric_value = elem['v']
      timestamp = elem['t'] / 1000
      source = service_metadata['__host']
      predefined_metric_tags = ' ' + ' '.join("%s=%s" % (k, v) for (k, v) in self.prefined_tags.iteritems()) if self.prefined_tags else ''  
      spinnaker_tags = ' ' + ' '.join("%s=%s" % (tag['key'], tag['value']) for tag in tags)
      all_tags = predefined_metric_tags + spinnaker_tags
      metric = "%s %d %d source=%s%s\n" % (metric_name, metric_value, timestamp, source, all_tags)  
      result.append(metric)

  def publish_metrics(self, service_metrics):
    """Writes time series data to S3 bucket for a metric snapshot."""
    points = []
    spectator_client.foreach_metric_in_service_map(
        service_metrics, self.__append_timeseries_point, points)
    offset = 0
    while offset < len(points):
      last = min(offset + self.MAX_BATCH, len(points))
      chunk = points[offset:last]
      try:
        self.send_metrics(chunk)
        # S3 stuff
      except Exception as ioerr:
        logging.error('Error sending to s3: %s', ioerr)
      offset = last
    return len(points)

def make_s3_service(options):
  # TODO: Add option to specify controller AWS Credential
  s3_bucket = os.environ.get('S3_BUCKET', options.get('s3',{}).get('bucket',''))
  prefined_tags = options.get("tags",[])
  # TODO: Add metric_prefix to other services
  metric_prefix = options.get("metric_prefix",'')
  if s3_bucket is None:
    raise ValueError('s3_bucket is not defined')

  return S3MetricsService(s3_bucket=s3_bucket, metric_prefix=metric_prefix, prefined_tags=prefined_tags)

class S3ServiceFactory(object):
  """For plugging S3 into the monitoring server."""
  def enabled(self, options):
    """Implements server_handlers.MonitorCommandHandler interface."""
    return 's3' in options.get('monitor', {}).get('metric_store', [])

  def add_argparser(self, parser):
    """Implements server_handlers.MonitorCommandHandler interface."""
    parser.add_argument('--s3', default=False, action='store_true',
                        dest='monitor_s3',
                        help='Publish metrics to S3.')
    parser.add_argument('--bucket', default="",
                        dest='bucket',
                        help='S3 bucket to push metrics too.')

  def __call__(self, options, command_handlers):
    """Create a s3 service instance for interacting with S3."""
    return make_s3_service(options)
