import argparse
import sys
import logging
import time
import threading
import json

import signal, lockfile, grp, os

from pwd import getpwnam
from daemonize import Daemonize

import paho.mqtt.client as mqtt

from mqttservice.mqttpatternmatcher import MQTTPatternMatcher

class MQTTBaseService:
	def __init__(
		self,

		applicationName      = 'MQTTBaseService',
		applicationNameFile  = "mqttbaseservice",

		topicHandlers        = [ ],
		topicSubscribe       = None
	):
		"""Initialize the base MQTT service

			:param string applicationName: Visible process name of the service
			:param string applicationNameFile: The filename version of the service name (no spaces, no uppercase, etc.)

			:param list topicHandlers: List of all topic handlers that are registered. Each handler consists of a dictionary that describes the topic and the callable handler(s)
			:param list topicSubscribe: If not specified the base service will just subscribe all topics listed in the topicHandlers. If specified only the topics specified in this list
		"""
		self._appName = applicationName
		self._applicationNameFile = applicationNameFile
		self._topicHandlers = topicHandlers
		self._topicSubscribe = topicSubscribe

		self._rereadConfig = True
		self._terminate = False
		self._terminated = False

		self._configuration = None
		self._mqtt = None
		self._mqttCurrentConfig = None

		self._mqttPatternMatcher = MQTTPatternMatcher()

		# Register handlers as specified in topicHandlers
		for topicHand in topicHandlers:
			self._mqttPatternMatcher.registerHandler(topicHand['topic'], topicHand['handler'])

	# Overriden methods ...

	def _validateConfiguration(self, newConfiguration):
		return True

	def _configurationReloaded_Prepare(self, newConfiguration):
		pass

	def _configurationReloaded(self):
		pass

	def _mqttConnected(self):
		pass

	def _mqttDisconnected(self):
		pass

	def _serviceShutdown(self):
		pass

	# Utility methods

	def mqttPublish(self, topic, payload = None, qos = 0, retain = False, prependBaseTopic = True):
		if self._mqtt:
			if prependBaseTopic:
				topic = self._configuration['mqtt']['basetopic'] + topic
			if payload is not None:
				if isinstance(payload, dict):
					payload = json.dumps(payload)
			try:
				if payload is not None:
					self._mqtt.publish(topic, payload = payload, qos = qos, retain = retain)
				else:
					self._mqtt.publish(topic, qos = qos, retain = retain)
				self._logger.debug(f"Published to {topic} (QOS {qos}, Retained: {retain})")
			except Exception as e:
				self._logger.error(f"Failed to publish to {topic} ({e})")

	# Internal methods

	def __validateConfiguration(self, newConfiguration):
		# Check for MQTT configuration

		if 'mqtt' not in newConfiguration:
			self._logger.error("Configuration is missing mqtt section")
			return False
		if 'broker' not in newConfiguration['mqtt']:
			self._logger.error("Configuration missing broker in mqtt section")
			return False
		if 'port' not in newConfiguration['mqtt']:
			self._logger.warning("Configuration missing broker port in mqtt section, setting to 1883")
			newConfiguration['mqtt']['port'] = 1883
		else:
			try:
				newConfiguration['mqtt']['port'] = int(newConfiguration['mqtt']['port'])
			except ValueError:
				self._logger.error("Invalid port supplied for MQTT")
				return False
			if (newConfiguration['mqtt']['port'] < 1) or (newConfiguration['mqtt']['port'] > 65535):
				self._logger.error("Invalid port supplied for MQTT")
				return False
		if 'user' not in newConfiguration['mqtt']:
			self._logger.error("MQTT Configuration missing user credentials (username)")
			newConfiguration['mqtt']['user'] = None
		if 'password' not in newConfiguration['mqtt']:
			self._logger.error("MQTT Configuration missing user credentials (password)")
			newConfiguration['mqtt']['password'] = None
		if 'basetopic' not in newConfiguration['mqtt']:
			self._logger.warning("MQTT base topic not set. Using empty")
			newConfiguration['mqtt']['basetopic'] = ""
		elif len(newConfiguration['mqtt']['basetopic']) < 1:
			self._logger.warning("MQTT base topic not set. Using empty")
			newConfiguration['mqtt']['basetopic'] = ""
		elif newConfiguration['mqtt']['basetopic'][-1] != '/':
			self._logger.warning("MQTT base topic not ending in trailing slash. Appending")
			newConfiguration['mqtt']['basetopic'] = newConfiguration['mqtt']['basetopic'] + "/"

		# Call implementations check routine ...
		return self._validateConfiguration(newConfiguration)

	def run(self):
		signal.signal(signal.SIGHUP, self._signalSigHup)
		signal.signal(signal.SIGTERM, self._signalTerm)
		signal.signal(signal.SIGINT, self._signalTerm)

		self._logger.info("Service running")

		while True:
			if self._rereadConfig:
				self._logger.info("Reloading configuration")
				self._rereadConfig = False

				try:
					with open(self._args.config, 'r') as cfgFile:
						newConfiguration = json.load(cfgFile)
				except json.decoder.JSONDecodeError as e:
					self._logger.error(f"Failed to parse configuration: {e}")
					continue
				except FileNotFoundError:
					self._logger.error(f"Failed to open configuration file {self._args.config}")
					continue

				# validate configuration
				if not self.__validateConfiguration(newConfiguration):
					self._logger.error("New configuration invalid. Keeping previous one")
					continue

				# Our configuration has changed - we might have to reconnect to MQTT; the implementation
				# might also be required to take some steps ...

				self._configurationReloaded_Prepare(newConfiguration)

				# Check if MQTT changed. If, drop existing MQTT object (LOCK!) and
				# then supply new one ...

				self._configuration = newConfiguration

				if ((self._mqtt is None)
					or ((self._configuration['mqtt']['broker'] != self._mqttCurrentConfig['broker'])
					or (self._configuration['mqtt']['port'] != self._mqttCurrentConfig['port'])
					or (self._configuration['mqtt']['user'] != self._mqttCurrentConfig['user'])
					or (self._configuration['mqtt']['password'] != self._mqttCurrentConfig['password'])
					or (self._configuration['mqtt']['basetopic'] != self._mqttCurrentConfig['basetopic']))
				):
					# We have to reconnect MQTT
					if self._mqtt is not None:
						self._mqtt.disconnect()
						self._mqtt = None

					self._mqtt = mqtt.Client()
					self._mqtt.on_connect = self._mqtt_on_connect
					self._mqtt.on_message = self._mqtt_on_message
					self._mqtt.on_disconnect = self._mqtt_on_disconnect
					if (self._configuration['mqtt']['user'] is not None) and (self._configuration['mqtt']['password'] is not None):
						self._mqtt.username_pw_set(self._configuration['mqtt']['user'], self._configuration['mqtt']['password'])
					self._mqtt.connect(self._configuration['mqtt']['broker'], self._configuration['mqtt']['port'])
					self._mqtt.loop_start()

				self._configurationReloaded()

			if self._terminate:
				self._logger.info("Terminating on user request")
				break

			# Currently this is a busy waiting loop
			time.sleep(0.5)

		if self._mqtt:
			self._logger.debug("Disconnecting from MQTT")
			self._mqtt.disconnect()
			while not self._terminated:
				time.sleep(1)
			self._mqtt.loop_stop()

		self._serviceShutdown()
		self._logger.info("Shut down service")

	def _mqtt_on_disconnect(self, client, userdata, rc):
		self._mqttDisconnected()
		if self._terminate:
			self._terminated = True

	def _mqtt_on_connect(self, client, userdata, flags, rc):
		if rc == 0:
			self._logger.warning(f"Connected to {self._configuration['mqtt']['broker']}:{self._configuration['mqtt']['port']} as {self._configuration['mqtt']['user']}")

			# Run subscriptions
			if self._topicSubscribe:
				for top in self._topicSubscribe:
					client.subscribe(self._configuration['mqtt']['basetopic'] + top)
			else:
				for topHan in self._topicHandlers:
					client.subscribe(self._configuration['mqtt']['basetopic'] + topHan['topic'])

			self._mqttConnected()
		else:
			self._logger.warning(f"Failed to connect to {self._configuration['mqtt']['broker']}:{self._configuration['mqtt']['port']} as {self._configuration['mqtt']['user']} (code {rc})")

	def _mqtt_on_message(self, client, userdata, msg):
		self._logger.debug(f"Received message on {msg.topic}")
		try:
			msg.payload = json.loads(str(msg.payload.decode('utf-8', 'ignore')))
		except Exception as e:
			# Ignore if we don't have a JSON payload
			pass

		if self._mqttPatternMatcher is None:
			self._logger.warning(f"Dropping message to {msg.topic} since no handlers are registered")
			return

		self._mqttPatternMatcher.callHandlers(msg.topic, msg, self._configuration['mqtt']['basetopic'])

	def _signalSigHup(self, *args):
		self._rereadConfig = True

	def _signalTerm(self, *args):
		self._terminate = True

	def mainDaemon(self):
		parg = self.parseArguments()
		self._args = parg['args']
		self._logger = parg['logger']

		self._logger.debug("Daemon starting ...")
		self.run()

	def parseArguments(self):
		ap = argparse.ArgumentParser(description = 'Example daemon')
		ap.add_argument('-f', '--foreground', action='store_true', help="Do not daemonize - stay in foreground and dump debug information to the terminal")

		ap.add_argument('--uid', type=str, required=False, default=None, help="User ID to impersonate when launching as root")
		ap.add_argument('--gid', type=str, required=False, default=None, help="Group ID to impersonate when launching as root")
		ap.add_argument('--chroot', type=str, required=False, default=None, help="Chroot directory that should be switched into")
		ap.add_argument('--pidfile', type=str, required=False, default=f"/var/run/{self._applicationNameFile}.pid", help=f"PID file to keep only one daemon instance running (default: /var/run/{self._applicationNameFile}.pid)")
		ap.add_argument('--loglevel', type=str, required=False, default="error", help="Loglevel to use (debug, info, warning, error, critical). Default: error")
		ap.add_argument('--logfile', type=str, required=False, default=f"/var/log/{self._applicationNameFile}.log", help=f"Logfile that should be used as target for log messages (default /var/log/{self._applicationNameFile}.log)")

		ap.add_argument('--config', type=str, required=False, default=f"/etc/{self._applicationNameFile}.conf", help=f"Configuration file for MQTT bridge (default /etc/{self._applicationNameFile}.conf)")

		args = ap.parse_args()
		loglvls = {
			"DEBUG"     : logging.DEBUG,
			"INFO"      : logging.INFO,
			"WARNING"   : logging.WARNING,
			"ERROR"     : logging.ERROR,
			"CRITICAL"  : logging.CRITICAL
		}
		if not args.loglevel.upper() in loglvls:
			print("Unknown log level {}".format(args.loglevel.upper()))
			sys.exit(1)

		logger = logging.getLogger()
		logger.setLevel(loglvls[args.loglevel.upper()])
		if args.logfile:
			fileHandleLog = logging.FileHandler(args.logfile)
			logger.addHandler(fileHandleLog)
		if args.foreground:
			streamHandleLog = logging.StreamHandler()
			logger.addHandler(streamHandleLog)

		return { 'args' : args, 'logger' : logger }

	def main(self):
		parg = self.parseArguments()
		args = parg['args']
		logger = parg['logger']

		daemonPidfile = args.pidfile
		daemonUid = None
		daemonGid = None
		daemonChroot = "/"

		if args.uid:
			try:
				args.uid = int(args.uid)
			except ValueError:
				try:
					args.uid = getpwnam(args.uid).pw_uid
				except KeyError:
					logger.critical("Unknown user {}".format(args.uid))
					print("Unknown user {}".format(args.uid))
					sys.exit(1)
			daemonUid = args.uid
		if args.gid:
			try:
				args.gid = int(args.gid)
			except ValueError:
				try:
					args.gid = grp.getgrnam(args.gid)[2]
				except KeyError:
					logger.critical("Unknown group {}".format(args.gid))
					print("Unknown group {}".format(args.gid))
					sys.exit(1)

			daemonGid = args.gid

		if args.chroot:
			if not os.path.isdir(args.chroot):
				logger.critical("Non existing chroot directors {}".format(args.chroot))
				print("Non existing chroot directors {}".format(args.chroot))
				sys.exit(1)
			daemonChroot = args.chroot

		if args.foreground:
			logger.debug("Launching in foreground")
			self._args = args
			self._logger = logger
			self.run()
		else:
			logger.debug("Daemonizing ...")
			self._logger = logger
			self._args = args
			daemon = Daemonize(
				app=self._appName,
				action=self.mainDaemon,
				pid=daemonPidfile,
				user=daemonUid,
				group=daemonGid,
				chdir=daemonChroot
			)
			daemon.start()
