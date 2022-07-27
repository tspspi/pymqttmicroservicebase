from context import mqttservice
from mqttservice.mqttbaseservice import MQTTBaseService

class EchoService(MQTTBaseService):
	def __init__(self):
		super().__init__(
			applicationName = "MQTTEchoService",

			topicHandlers = [
				{ 'topic' : 'echoservice/echo',            'handler' : [ self._handleEchoRequestMessage  ] },
				{ 'topic' : 'echoservice/version/request', 'handler' : [ self._handleEchoVersionRequest  ] },
				{ 'topic' : 'echoservice/echo/#',          'handler' : [ self._handleEchoRequestMessageN ] }
			]
		)

	def _handleEchoRequestMessage(self, topic, msg):
		print(f"Received echo request with payload {msg.payload}")
		self.mqttPublish('echoservice/reply', { 'reply' : True, 'payload' : msg.payload })

	def _handleEchoVersionRequest(self, topic, msg):
		print("Received version query request")
		self.mqttPublish('echoservice/version', { 'version' : '0.0.1' })

	def _handleEchoRequestMessageN(self, topic, msg):
		topic = topic.split("/")
		try:
			N = int(topic[2])
			print(f"Received echo request for {N} responses")

			for i in range(N):
				self.mqttPublish('echoservice/reply', { 'reply' : True, 'payload' : msg.payload, 'n' : i })
		except:
			pass

	def __enter__(self):
		return self

	def __exit__(self, type, value, tb):
		pass

if __name__ == "__main__":
	with EchoService() as service:
		service.main()
