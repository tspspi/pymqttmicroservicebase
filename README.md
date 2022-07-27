# Python MQTT based microservice base daemon

Since this is a recurring task this project contains a base implementation for
a simple MQTT based service that offers just some basic features required for
simple MQTT based microservices:

* Daemonizing
    * PID file handling
    * Log file handling
* Handling signals like SIGHUP and SIGTERM
* Connecting to an MQTT service using the Paho MQTT client, keeping the
  connection active
* Processing JSON configuration files to gather MQTT configuration and reloading
  of that configuration
* Allowing to specify topics relative to a base topic

Services are able to simply subclass and implement their own message processing
functions. This makes life a little bit easier. This repository also implements
some client utilities that wrap the Paho MQTT library that implement a similar
pattern.

Note that this library does not work when subscribing to a huge number of topics
with different handlers since it uses an own callback registration mechanism that
all messages go through. It also does not work well when one wants to dynamically
register or unregister from topics. Also in it's current implementation it linearly
iterates over all registered handlers for each message and does not use any kind
of trie.

## Usage

The most simple usage possible just registers topic handlers and reacts to the
received messages.

```
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
```
