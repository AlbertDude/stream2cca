stream2cca
===========================

Python 3.6+ script for playing audio to Google Chromecast Audio devices.

Uses `pychromecast <https://github.com/home-assistant-libs/pychromecast>`_

For automatic playing of next track when current track ends, uses the

.. code:: python

    self.cc.media_controller.register_status_listener(self) 
    ...
    def new_media_status(self, status):
        ...


mechanism described at `Playing a Playlist <https://github.com/home-assistant-libs/pychromecast/issues/330>`_

Dependencies
------------

- pychromecast
    - pip install PyChromecast
- mutagen
    - pip install mutagen


How to use
----------

- run http server from same folder as the main stream2cca script

.. code:: bash

   python3 -m http.server

- run the stream2cca script

.. code:: bash

   python3 stream2cca.py playfolder folder_path -d "CCA name"

