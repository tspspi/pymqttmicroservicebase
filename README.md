# Python MQTT based microservice base

Since this is a recurring task this project contains a base implementation for
a simple MQTT based service that offers just some base features required for
about every of those services:

* Daemonizing
* Initial connecting to an MQTT service using the Paho MQTT client
* Handling signals like SIGHUP and SIGTERM
* Processing JSON configuration files to gather MQTT configuration

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
