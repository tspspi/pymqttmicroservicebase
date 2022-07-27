from context import mqttservice
from mqttservice.mqttbaseservice import MQTTBaseService

class EchoService(MQTTBaseService):
	def __init__(self):
		super().__init__(
			applicationName = "MQTTEchoService",

			topicHandlers = [
				{ 'topic' : '/echoservice/echo',    'handler' : [ self._handleEchoRequestMessage ] },
				{ 'topic' : '/echoservice/version', 'handler' : [ self._handleEchoVersionRequest ] },
				{ 'topic' : '/echoservice/echon/#', 'handler' : [ self._handleEchoVersionRequest ] }
			]
		)

	def _handleEchoRequestMessage(self, topic, msg):
		print(f"Received echo request with payload {msg.payload}")

	def _handleEchoVersionRequest(self, topic, msg):
		print("Received version query request")

	def __enter__(self):
		return self

	def __exit__(self, type, value, tb):
		pass

if __name__ == "__main__":
	with EchoService() as service:
		service.main()
