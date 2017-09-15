"""Implements metric service for interacting with Wavefront."""


import logging
import os
import re
import socket
import traceback

import spectator_client


import time
import pdb





import spectator_client


class WavefrontMetricsService(object):
  """A metrics service for interacting with Datadog."""

  # 20170218(ewiseblatt)
  # I dont know the actual limit.
  # This is a guess while I wait to hear back from datadog support.
  # Large deployments for clouddriver are seeing 413, but nothing else.
  # I've sent batches larger than this that have been fine.
  MAX_BATCH = 2000

  def __init__(self, proxy_host, proxy_port):
    """Constructs the object."""
    self.__host = proxy_host
    self.__port = int(proxy_port)

  def send_metric(self, proxy_socket, metric_name, metric_value, timestamp, source, point_tags=None):  
        timestamp = timestamp or int(time.time())  
        tags = ' ' + ' '.join("%s=\"%s\"" % (k, v) for (k, v) in point_tags.iteritems()) if point_tags else ''  
        proxy_socket.send("%s %d %d source=%s%s\n" % (metric_name, metric_value, timestamp, source, tags))  
  
  def send_metrics(self, metrics, proxy_host, proxy_port):
    s = socket.socket()  
    # s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # pdb.set_trace()
    s.connect((proxy_host, proxy_port))  
    for metric in metrics:
      for point in metric["points"]:
        timestamp = point[0]
        value = point[1]
        self.send_metric(s, metric["metric"], value, timestamp, metric["host"], point_tags={"app": "qbo", "bu":"sbg", "location":metric["host"], "env": "pprd"})  
    s.close()

  def __append_timeseries_point(
      self, service, name,
      instance, metric_metadata, service_metadata, result):
    """Creates a post payload for a DataDog time series data point.

       See http://docs.datadoghq.com/api/?lang=python#metrics-post.

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

    result.append({
        'metric': '{service}.{name}'.format(service=service, name=name),
        'host': service_metadata['__host'],
        'points': [(elem['t'] / 1000, elem['v'])
                   for elem in instance['values']],
        'tags': ['{0}:{1}'.format(tag['key'], tag['value']) for tag in tags]
    })

  def publish_metrics(self, service_metrics):
    """Writes time series data to Datadog for a metric snapshot."""
    # pdb.set_trace()
    points = []
    spectator_client.foreach_metric_in_service_map(
        service_metrics, self.__append_timeseries_point, points)
    # pdb.set_trace()
    offset = 0
    while offset < len(points):
      last = min(offset + self.MAX_BATCH, len(points))
      chunk = points[offset:last]
      try:
        self.send_metrics(chunk,self.__host,self.__port)
      except IOError as ioerr:
        logging.error('Error sending to wavefront: %s', ioerr)
      offset = last
    return len(points)


def make_wavefront_service(options):
  def read_param(param_name, config_text):
    """Read configuration parameter from Wavefront config_text."""
    match = re.search('^{0}:(.*)$'.format(param_name),
                      config_text, re.MULTILINE)
    if not match:
      return None
    return match.group(1).strip()


  wavefront_options = options.get('wavefront', {})
  proxy_host = os.environ.get('WAVEFRONT_PROXY_HOSTNAME', wavefront_options.get('proxy_hostname'))
  proxy_port = os.environ.get('WAVEFRONT_PROXY_PORT', wavefront_options.get('proxy_port'))
  if not proxy_port or not proxy_host:
    config_path = options['wavefront_config']
    try:
      with open(config_path, 'r') as stream:
        logging.info('Reading Wavefront config from %s', config_path)
        text = stream.read()
        proxy_host = proxy_host or read_param('proxy_hostname', text)
        proxy_port = proxy_port or read_param('proxy_port', text)
    except IOError:
      logging.warning('Could not read config from wavefront "%s": %s',
                      config_path, traceback.format_exc())


  if proxy_host is None:
    raise ValueError('PROXY_HOST is not defined')
  if proxy_port is None:
    raise ValueError('PROXY_PORT is not defined')

  return WavefrontMetricsService(proxy_host=proxy_host, proxy_port=proxy_port)



class WavefrontServiceFactory(object):
  """For plugging Wavefront into the monitoring server."""
  def enabled(self, options):
    """Implements server_handlers.MonitorCommandHandler interface."""
    return 'wavefront' in options.get('monitor', {}).get('metric_store', [])

  def add_argparser(self, parser):
    """Implements server_handlers.MonitorCommandHandler interface."""
    parser.add_argument('--wavefront', default=False, action='store_true',
                        dest='monitor_wavefront',
                        help='Publish metrics to Wavefront.')

    parser.add_argument(
      '--wavefront_config', default='/etc/wavefront.conf',
      help='Path to wavefronta config file (to read keys from).')

  def __call__(self, options, command_handlers):
    """Create a wavefront service instance for interacting with Wavefront."""
    return make_wavefront_service(options)
