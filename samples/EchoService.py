#!/usr/bin/env python

from mqttservice import mqttbaseservice

class EchoService(mqttbaseservice.MQTTBaseService):
	def __init__(self):
		super().__init__(
			applicationName = "MQTTEchoService",

			topicHandlers = [
				{ 'topic' : 'echoservice/echo', 'handler' : [ self._handleEchoRequestMessage ] }
			]
		)

	def _handleEchoRequestMessage(self, topic, msg):
        self._logger.debug("Received echo request")
		self.mqttPublish('echoservice/reply', { 'some' : "payload", 'will' : "be serialized", 'to' : "JSON from dict" })

	def __enter__(self):
		return self

	def __exit__(self, type, value, tb):
		pass

if __name__ == "__main__":
	with EchoService() as service:
		service.main()

